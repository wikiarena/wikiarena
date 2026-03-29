# Solver API

Last updated: 2026-03-29

This doc defines the initial public API for the solver experience on `wikiarena.org`.

## Scope

- JSON over HTTPS
- unauthenticated
- versioned under `/v1`
- intentionally small first public surface

Initial endpoints:

- `GET /health`
- `GET /v1/meta`
- `GET /v1/random-page-titles`
- `POST /v1/solve`

Production base URL is expected to be `https://api.wikiarena.org`.

## Design Rules

1. Keep the public product API thinner than the internal benchmark and protocol stack.
2. Expose the loaded Wikipedia snapshot clearly.
3. Return paths in a shape that can support one or many shortest paths.
4. Avoid request parameters we do not need yet.
5. Do not expose backend-specific implementation details in the primary public contract.

## Snapshot Semantics

- `snapshot_id` identifies the Wikipedia content snapshot, not the solver implementation.
- Initial format: `enwiki-YYYYMMDD`
- Example: `enwiki-20260301`

Solver or graph-format provenance can live in release metadata, deploy config, logs, or future optional fields. It is not part of the initial public contract.

## Common Response Semantics

- Response titles use canonical graph titles with spaces.
- `solve_ms` is server-side solve time in milliseconds, not browser round-trip time.
- `paths` is always a list.
- All returned paths, when present, have exactly `path_length` steps.
- Clients must not assume the service returns every possible shortest path.
- There is no `max_paths` request parameter in v1. The server decides how many shortest paths to return.

## Endpoints

### `GET /health`

Infra readiness only.

Return `200` when the service is ready to answer solve requests. Return `503` while the graph is still loading or if startup failed.

`status` is expected to be `ok`, `starting`, or `error`.

Healthy example:

```json
{
  "status": "ok"
}
```

Not ready example:

```json
{
  "status": "starting"
}
```

### `GET /v1/meta`

Frontend-visible runtime metadata for the currently loaded graph.

Response `200`:

```json
{
  "service_version": "0.1.0",
  "snapshot_id": "enwiki-20260301",
  "dump_date": "20260301",
  "node_count": 7146840,
  "edge_count": 695099364
}
```

Field meanings:

- `service_version`: deployed API version
- `snapshot_id`: Wikipedia snapshot identifier currently loaded by the service
- `dump_date`: Wikimedia dump date for display and debugging
- `node_count`: canonical article nodes in the loaded graph
- `edge_count`: directed canonical links in the loaded graph

### `GET /v1/random-page-titles`

Return a random batch of canonical article titles from the currently loaded graph snapshot.

Query parameters:

- `count`: optional integer, default `200`, minimum `1`, maximum `500`

Response `200`:

```json
{
  "snapshot_id": "enwiki-20260301",
  "titles": [
    "Apple",
    "Banana",
    "Jazz"
  ]
}
```

Response field meanings:

- `snapshot_id`: Wikipedia snapshot identifier used to source the titles
- `titles`: canonical graph titles sampled from the loaded snapshot

### `POST /v1/solve`

Solve one shortest-path query.

Request body:

```json
{
  "start_title": "Apple",
  "target_title": "Banana"
}
```

Request fields:

- `start_title`: required non-empty string
- `target_title`: required non-empty string

Success response `200`:

```json
{
  "snapshot_id": "enwiki-20260301",
  "start_title": "Apple",
  "target_title": "Banana",
  "path_length": 2,
  "paths": [
    ["Apple", "Fruit", "Banana"]
  ],
  "solve_ms": 8.7,
  "pages_visited": 42,
  "links_scanned": 128
}
```

Same-page response `200`:

```json
{
  "snapshot_id": "enwiki-20260301",
  "start_title": "Apple",
  "target_title": "Apple",
  "path_length": 0,
  "paths": [
    ["Apple"]
  ],
  "solve_ms": 0.1,
  "pages_visited": 1,
  "links_scanned": 0
}
```

No-path response `200`:

```json
{
  "snapshot_id": "enwiki-20260301",
  "start_title": "Page A",
  "target_title": "Page B",
  "path_length": null,
  "paths": [],
  "solve_ms": 4.1,
  "pages_visited": 2,
  "links_scanned": 0
}
```

Response field meanings:

- `snapshot_id`: Wikipedia snapshot identifier used for the solve
- `start_title`: canonicalized start title used by the service
- `target_title`: canonicalized target title used by the service
- `path_length`: number of steps in each returned shortest path, or `null` if no path was found
- `paths`: zero or more shortest paths
- `solve_ms`: server-side solve time in milliseconds
- `pages_visited`: number of unique graph pages discovered during the search
- `links_scanned`: number of graph links inspected during the search

## Errors

All non-2xx responses should use the same JSON shape:

```json
{
  "code": "start_title_not_found",
  "message": "Start title was not found in the loaded graph snapshot."
}
```

Initial error cases:

- `404 start_title_not_found`
- `404 target_title_not_found`
- `422 invalid_request`
- `503 graph_not_ready`
- `500 internal_error`

Notes:

- Use `404` only when the requested title is not present in the loaded graph snapshot.
- Use `200` with `paths: []` when both titles exist but no path is found.
- Use `422` for malformed JSON or missing required fields.

## Current Non-Goals

- authentication
- leaderboard writes
- batch solve
- streaming solve progress
- request parameters for path-count control
- exposing solver implementation flavor in the primary response body
