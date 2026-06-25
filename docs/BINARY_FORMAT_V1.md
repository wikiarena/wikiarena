# Binary Format V1

Last updated: 2026-03-22

The current production artifact uses a dated file name such as `wikiarena_graph_enwiki_20260301.bin`.

This doc describes the format that the implemented binary solver reads today.

## Goals

- exact shortest-path solving over canonical article nodes
- one deployable artifact with no graph/lookup mismatch risk
- enough structure for bidirectional BFS
- small hot-path memory footprint while still supporting title lookup

## Non-Goals

- exact offline reconstruction of clickable redirect titles
- pagerank or ranking metadata in the runtime graph
- storing raw Wikipedia `page_id` values in the hot path
- solver-side redirect resolution during BFS

## Runtime Model

At runtime the solver needs exactly two things:

- title lookup for `title <-> node_id`
- outgoing and incoming adjacency for graph search

So the graph ships as one file:

- `wikiarena_graph_enwiki_20260301.bin`

## Node IDs

- Wikipedia `page_id` values are build-time identifiers, not runtime graph ids.
- Runtime node ids are dense integers `0..N-1`.
- Node ids are assigned by lexicographic order of canonical article titles.
- The graph contains only canonical article pages as nodes.

This gives us:

- compact adjacency storage
- better cache locality
- simple CSR arrays
- binary-search title lookup because node ids follow title sort order

## Title Storage And Lookup

The file stores one canonical title table:

- `node_id -> title` via offset lookup into a byte blob
- `title -> node_id` via binary search over that same sorted title table

Important implementation detail:

- stored titles are the canonical dump titles, which are underscore-form titles
- `MappedBinarySolverGraph.find_node_id()` normalizes spaces to underscores for lookup
- `MappedBinarySolverGraph.title_for_node_id()` converts underscores back to spaces on output

So the public backend API behaves like normal page-title strings even though the underlying table is underscore-normalized.

## Redirect Handling

- Redirects are resolved during graph construction.
- Redirect pages do not become runtime nodes.
- Links are rewritten to canonical article targets before the binary is written.
- Duplicate edges introduced by redirect resolution are removed during the build.

Implications:

- runtime redirect tables are not part of the dated graph binary artifact
- the search engine operates on canonical article nodes only
- if live Wikipedia surfaces a redirect title, canonicalization happens at the boundary layer, not inside BFS

## Encodings

- all integers are little-endian
- offsets are `u32`
- neighbor node ids are packed as `u24`
- because neighbors use `u24`, `node_count` must be `<= 2^24 - 1`

```c
typedef struct {
  uint8_t b0;
  uint8_t b1;
  uint8_t b2;
} WaU24;
```

## File Header

The implemented header is 80 bytes and packed with this layout:

```c
typedef struct {
  uint8_t  magic[8];               // "WASOLV1\0"
  uint32_t version;                // 1
  uint32_t header_bytes;           // 80
  uint32_t node_count;             // N, must be <= 2^24 - 1
  uint32_t edge_count;             // L, total canonical directed edges
  uint64_t canonical_offsets_off;  // u32[N + 1]
  uint64_t canonical_bytes_off;    // utf-8 title bytes
  uint64_t out_offsets_off;        // u32[N + 1]
  uint64_t out_neighbors_off;      // WaU24[L]
  uint64_t in_offsets_off;         // u32[N + 1]
  uint64_t in_neighbors_off;       // WaU24[L]
  uint64_t file_bytes;             // total file size in bytes
} WaSolverHeaderV1;
```

## Section Layout

```c
uint32_t canonical_offsets[N + 1];
uint8_t  canonical_bytes[canonical_bytes_len];

uint32_t out_offsets[N + 1];
WaU24    out_neighbors[L];

uint32_t in_offsets[N + 1];
WaU24    in_neighbors[L];
```

## Why Each Section Exists

`canonical_offsets` + `canonical_bytes`

- `node_id -> title`
- `title -> node_id` binary search
- keeps title lookup in the same artifact as the graph

`out_offsets` + `out_neighbors`

- outgoing CSR adjacency
- used for forward expansion in bidirectional BFS

`in_offsets` + `in_neighbors`

- incoming CSR adjacency
- used for backward expansion in bidirectional BFS

Nothing else is required for the current exact shortest-path search implementation.

## Search Implications

The current binary search implementation:

- looks up start and target titles in the title table
- runs bidirectional BFS over outgoing and incoming CSR arrays
- reconstructs one deterministic shortest path

The format supports that directly because it contains both forward and reverse adjacency.

## Build Invariants

The builder and loader currently enforce these invariants:

- all nodes are article-namespace canonical pages
- canonical titles are unique
- canonical titles are lexicographically sorted
- redirect pages are excluded as runtime nodes
- self-edges are removed
- adjacency lists are deduped
- adjacency lists are strictly sorted by neighbor node id
- `out_offsets[0] == 0`
- `out_offsets[N] == L`
- `in_offsets[0] == 0`
- `in_offsets[N] == L`

## Build-Time Inputs Versus Runtime Artifact

Build-time inputs include things like:

- raw Wikimedia page, redirect, pagelinks, and linktarget dumps
- grouped source and target link intermediates
- temporary `page_id -> node_id` maps

The runtime artifact does not keep any of that extra build machinery. It keeps only the title table and the two CSR views needed for search.

## Current Naming Note

Older docs may still say `solver.bin`. The current project naming standard for the production artifact is `wikiarena_graph_<wiki>_<dump_date>.bin`.
