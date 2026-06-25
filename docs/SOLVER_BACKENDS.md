# Solver Backend

Last updated: 2026-03-22

## Current Answer

- The official WikiArena solver backend is `BinarySolverBackend`.
- The official graph artifact uses a dated file name such as `wikiarena_graph_enwiki_20260301.bin`.
- The backend reads the binary graph through `MappedBinarySolverGraph`.
- Search is exact shortest-path search over the canonical article graph.
- The backend currently returns one deterministic shortest path.

## Why Keep A Backend Interface At All

WikiArena still benefits from a very small solver interface because it:

- keeps benchmark code independent from solver internals
- allows correctness/performance benchmarking across implementations
- leaves room for a future hosted solver without changing the core benchmark contracts

## Interface Shape

Two layers still exist:

1. `SolverBackend`
   - one-shot shortest path lookup
   - target-session creation
   - shutdown/cleanup

2. `SolverTargetSession`
   - repeated shortest path lookups for the same target
   - repeated distance lookups for the same target

The interface is intentionally a little broader than what the official backend uses today.

## What WikiArena Should Depend On

WikiArena should only depend on:

- shortest path lookup
- shortest path length
- optional target-session reuse when a backend supports it
- snapshot/provenance metadata

WikiArena should not depend on:

- CSR implementation details
- whether the graph is memory-mapped or fully loaded in RAM
- the exact BFS strategy used by a backend

## Official Backend Behavior Today

`BinarySolverBackend` is the production path going forward:

- it reads the binary graph artifact through `MappedBinarySolverGraph`
- the graph stores canonical article pages plus outgoing and incoming CSR adjacency
- search is exact shortest-path search over that canonical article graph
- the backend currently returns one deterministic shortest path
- `supports_target_sessions` is currently `False`

That last point matters: target sessions remain part of the interface, but they are not the center of the official backend design right now.

## Implications For Our Docs

- Describe the binary backend as the current supported local solver.
- Do not assume the official solver returns all shortest paths.
- Do not assume target-session reuse is a defining property of the official backend.
- Keep solver provenance in run artifacts through backend id, snapshot id, and graph metadata rather than through implementation-specific details.
