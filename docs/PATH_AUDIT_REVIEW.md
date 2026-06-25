# Path Audit Review

Last updated: 2026-03-23

This note records the live-Wikipedia path audit strategy and the API behavior that motivated it.

## Current Code Paths

### `src/wikiarena/solver/path_audit.py`

Current behavior:

- audits one concrete solver path at a time
- for each edge `A -> B`, checks direct edge membership with filtered `prop=links` / `pltitles`
- if `allow_redirects=True` and direct visibility fails, fetches all redirect aliases for `B`
- then checks whether `A` links to any alias of `B` with filtered `prop=links` / `pltitles`

Current tradeoffs:

- `PathAuditCache` caches redirect aliases and filtered source/candidate checks across calls
- taskset audits reuse one cache across all tasks
- edge checks are still issued per edge/candidate set, not as one fully batched path-level request

### `src/wikiarena/wikipedia/live_service.py`

Relevant methods:

- `get_page()`
  - uses `prop=info|links`
  - `pllimit=500`
  - paginates with `plcontinue`
  - returns the full article-namespace outgoing link list
- `has_any_link_to_titles()`
  - uses `prop=links` with `pltitles`
  - answers whether a source page links to any candidate title
- `get_matching_links_to_titles()`
  - uses `prop=links` with `pltitles`
  - returns which candidate titles are visible outgoing links
- `get_redirect_titles()`
  - uses `prop=redirects`
  - `rdlimit=500`
  - paginates with `rdcontinue`
  - returns all redirect aliases for the canonical target page

## Measured Behavior Of The Current Audit Building Blocks

These were measured against live English Wikipedia using the current `LiveWikiService` logic.

### Full outgoing-link fetch (`get_page()`)

- `Haiti national football team`
  - `681` outgoing article links
  - `2` HTTP requests
- `AT&T Stadium`
  - `1357+` outgoing article links
  - `3` HTTP requests
- `New Zealand`
  - `1144` outgoing article links
  - `3` HTTP requests
- `1973 oil crisis`
  - `1682` outgoing article links
  - `4` HTTP requests

This matches the current implementation shape: one request per `500` outgoing links page.

### Redirect lookup (`get_redirect_titles()`)

- `United Kingdom`
  - `103` redirect aliases
  - `1` HTTP request
- `Willie Nelson`
  - `13` redirect aliases
  - `1` HTTP request
- `Any Old Arms Won't Do`
  - `0` redirect aliases
  - `1` HTTP request

This matches the current implementation shape: one request per `500` redirect aliases.

### Older full-link audit behavior on one sample path

Path audited:

- `Haiti national football team -> AT&T Stadium -> NFL International Series`

Observed behavior before the filtered-link implementation:

- `2` calls to `get_page()`
- `0` calls to `get_redirect_titles()`
- `5` total HTTP requests

The reason it took `5` requests rather than `2` is that the old audit fetched the full outgoing adjacency of each source page, not a single edge membership check.

## Exact Request Counts For Full-Link Fetching

Let:

- `L(P)` = article-namespace outgoing link count of page `P`
- `R(P)` = redirect alias count of page `P`
- `steps(path)` = number of edges in the solver path

### `get_page(P)` cost

Because `pllimit=500`, the exact request count is:

```text
requests_get_page(P) = max(1, ceil(L(P) / 500))
```

### `get_redirect_titles(P)` cost

Because `rdlimit=500`, the exact request count is:

```text
requests_get_redirect_titles(P) = max(1, ceil(R(P) / 500))
```

### Full-link strict audit cost for one path

For a path `v0 -> v1 -> ... -> vk` with `k = steps(path)`:

```text
requests_strict(path)
  = sum_{i=0..k-1} max(1, ceil(L(vi) / 500))
```

This is because the current code fetches the full outgoing link list for every source node in the path.

### Current redirect-aware audit cost for one path

If `allow_redirects=True`, and redirect lookup is needed on edge targets where direct visibility fails:

```text
requests_redirect_aware(path)
  = sum_{i=0..k-1} max(1, ceil(L(vi) / 500))
  + sum_{j in direct_miss_targets(path)} max(1, ceil(R(vj) / 500))
```

### Current per-task cost

For a task audited with one solver path, the per-task cost is just the per-path cost above.

If we later audit all shortest paths for the same `(start, target)` pair, the current code will refetch the same source pages and target redirect sets repeatedly unless we add caching around it.

## Why The Previous 500-Task Audit Was Slow

The selected `500`-task set had:

- `2763` total path edges
- `2406` unique source pages across those edges
- `2404` unique target pages across those edges

The slow script was over-fetching because it tried to prefetch large live adjacency sets for thousands of pages:

- full outgoing link sets for many source pages
- full incoming link sets for many target pages

That is much more expensive than "one API call per page" because both `links` and `linkshere/backlinks` are paginated, and high-degree pages can require several continuation requests.

## Current API: `prop=links` + `pltitles`

MediaWiki already has a direct edge-membership filter:

- module: `prop=links`
- parameter: `pltitles`

The docs explicitly say:

- `pltitles`: "Only list links to these titles. Useful for checking whether a certain page links to a certain title."

This is exactly what we want for path auditing.

### What we tested

#### Single-source filtered query

Query:

```text
action=query
prop=links
titles=New Zealand
pltitles=1973 oil crisis
plnamespace=0
pllimit=max
```

Observed result:

- returned `1973 oil crisis`
- no `continue`
- one request total, even though `New Zealand` has `1144` outgoing article links

#### Multi-source filtered query

Query:

```text
action=query
prop=links
titles=Haiti national football team|AT&T Stadium
pltitles=AT&T Stadium|NFL International Series
plnamespace=0
pllimit=max
```

Observed result:

- `Haiti national football team` returned `AT&T Stadium`
- `AT&T Stadium` returned `NFL International Series`
- one request total

This is the key finding: for audit, we do not need to fetch full link sets first.

## Exact Request Counts With The Current Filtered API

Let:

- `C(P)` = number of candidate titles we want to check against source page `P`
- for direct audit, `C(P)` is usually just `1`
- for redirect-aware audit, `C(P)` can be `1 + redirect_alias_count(target)`

Because `pltitles` allows up to `50` candidate titles per request, the exact filtered-link request count for one source page is:

```text
requests_filtered_source(P) = ceil(C(P) / 50)
```

### Strict direct-edge audit with filtered queries

For one edge `A -> B`:

```text
requests_edge_direct(A -> B) = 1
```

For one path of length `k`, if audited edge-by-edge without source batching:

```text
requests_path_direct = k
```

If multiple edges in the path share the same source page, caching can reduce that further.

### Redirect-aware filtered audit

For one edge `A -> B`:

1. fetch redirect aliases for `B`
2. check whether `A` links to `B` or any alias via `pltitles`

Exact request count:

```text
requests_edge_redirect_aware(A -> B)
  = max(1, ceil(R(B) / 500))
  + ceil((R(B) + 1) / 50)
```

In practice, most pages have far fewer than `50` redirect aliases, so this is usually:

```text
1 redirect request + 1 filtered links request = 2 requests
```

### Batched path audit with filtered queries

For a single path, if we batch up to `50` source pages together and up to `50` candidate target titles together, we can often audit the whole path in one filtered `links` request when the path is short.

For a typical solver path of length `<= 18`, a practical plan is:

- one batched redirect lookup for all path targets
- one or a few filtered `links` requests for all source pages against the union of target/alias titles

This is dramatically cheaper than fetching full outgoing and incoming adjacency.

## Answer To The Core Question

Yes: there is an API to check whether a specific link is on a page.

Use:

```text
action=query
prop=links
titles=<source page>
pltitles=<target page or alias list>
plnamespace=0
pllimit=max
formatversion=2
redirects=true
```

That is the right primitive for reusable path auditing.

## Current Recommendation

Keep `wikiarena.solver.path_audit` as the main reusable entry point. Its default audit strategy should remain:

- direct edge existence via filtered `links`
- redirect-aware edge existence via `redirect aliases + filtered links`

That matches the real question we need to answer, and it should be much faster than either full outgoing fetches or full outgoing/incoming intersection prefetches.
