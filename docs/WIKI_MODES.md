# Wiki Modes

Last updated: 2026-03-24

WikiArena now has two intentionally different wiki backends.

For command examples and option-level guidance, see [`CLI.md`](CLI.md).

## Modes

### `live`

- reads page state from the live Wikipedia API at runtime
- requires network access
- reflects the current state of Wikipedia, including recent edits and page moves
- preserves the live API's link ordering for a page

### `graph`

- reads page state from a local dated graph snapshot such as `wikiarena_graph_enwiki_20260301.bin`
- requires no network access after the graph is installed
- reflects a fixed Wikimedia dump snapshot
- returns canonical article titles from the binary graph
- returns links in the graph's deterministic sorted order

## Important Behavioral Differences

`graph` mode is not intended to be byte-for-byte equivalent to `live` mode.

The main differences today are:

- redirects are resolved during graph construction, so redirect pages are not runtime nodes
- clickable link text is canonicalized to target article titles in the graph
- link order is deterministic graph order, not live page order
- duplicate links are removed during graph construction
- graph mode is fixed to the installed snapshot; live mode changes as Wikipedia changes
- graph mode can only navigate pages present in the installed snapshot
- graph mode avoids network failures and API variability; live mode can fail due to connectivity or upstream issues

## What Is Still Shared

- both modes operate on article-namespace navigation for the main CLI/eval flow
- both modes produce the same run protocol artifacts
- both modes still use the same harness, navigation rules, and participant drivers

## CLI Shape

Single-run and benchmark commands can select the wiki backend explicitly:

```bash
wikiarena run --navigation-backend live ...
wikiarena run --offline --navigation-graph-path /path/to/wikiarena_graph_enwiki_20260301.bin ...

wikiarena eval run --config benchmark.toml --navigation-backend live
wikiarena eval run --config benchmark.toml --offline
```

`--offline` is an alias for `--navigation-backend graph`.

`--navigation-graph-path` requires graph navigation mode.

Solver shortest-path data is configured separately. For example:

```bash
wikiarena run --solver-backend local --solver-graph-path /path/to/wikiarena_graph_enwiki_20260301.bin ...
```

That keeps navigation live unless you also select graph navigation.

If `graph` mode is selected, WikiArena resolves the graph path in this order:

1. `--navigation-graph-path`
2. `WIKIARENA_GRAPH_PATH`
3. the newest dated graph file in the default per-user application data graph directory, for example on macOS `~/Library/Application Support/wikiarena/graphs/wikiarena_graph_enwiki_20260301.bin`

If `navigation_snapshot_id` is omitted in graph mode, WikiArena infers it from the selected dated graph filename. For example, `wikiarena_graph_enwiki_20260301.bin` maps to `enwiki-20260301`.

## Config Shape

Benchmark configs can also pin the wiki backend:

```toml
[run_options.navigation_runtime]
backend = "graph"
graph_path = "/path/to/wikiarena_graph_enwiki_20260301.bin"

[run_options.solver_runtime]
backend = "local"
```

`navigation_snapshot_id` and `solver_snapshot_id` are optional but recommended for reproducibility and result interpretation.

When a snapshot id is omitted for a graph-backed runtime, WikiArena infers it from the selected dated graph filename.
