# Graph Pipeline V1

Last updated: 2026-03-31

The official WikiArena graph artifact uses a dated file name such as `wikiarena_graph_enwiki_20260301.bin`.

## Goal

The pipeline converts one Wikimedia dump snapshot into an aggressively preprocessed
solver artifact that:

- fits in memory on normal developer and server machines
- supports exact shortest-path solving over canonical article pages
- keeps runtime lookup and BFS as simple as possible
- can be rebuilt reproducibly from dated public dump inputs

The runtime artifact design is described in `docs/BINARY_FORMAT_V1.md`.
The graph semantics decision to use article namespace only lives in
`docs/DECISIONS.md`.

## Active Path

- Runtime solver code lives in `src/wikiarena/solver/binary/`
- Graph build and release helpers live in `src/wikiarena/graph/`
- Low-level dump parsing and normalization logic lives in `src/wikiarena/graph/dump_processing.py`
- Human and CI entrypoints live in `scripts/`

Official entrypoints:

- `scripts/build_graph.py`
- `scripts/smoke_test_graph.py`
- `scripts/write_graph_metadata.py`

`scripts/build_graph.py` is the single maintainer entrypoint for the official
graph build. It can either:

- prepare inputs from raw Wikimedia dumps and build a dated graph binary such as `wikiarena_graph_enwiki_20260301.bin`
- build directly from existing grouped intermediates

For reproducibility, the active raw-dump path uses one supported merge toolchain:
GNU `sort` + GNU `join` (via `gsort`/`gjoin` on macOS, or GNU `sort`/`join` on Linux).

User-facing setup should stay different from maintainer graph builds:

- maintainers build graph releases from raw dumps and grouped intermediates
- normal users install released graph artifacts with `wikiarena graph install`
- `wikiarena graph install` downloads, decompresses, verifies, and places dated graph binaries locally without requiring dump-processing knowledge

## Runtime-Driven Build Invariants

The build exists to satisfy the runtime binary format, not as an end in itself.
That means the pipeline must guarantee:

- nodes are canonical article pages only (`namespace = 0`)
- redirect pages do not become runtime nodes
- edges point between canonical article nodes only
- duplicate edges are removed
- self-edges are removed
- final adjacency is grouped both by source and by target for fast binary construction

## Stage Breakdown

### 1. Resolve dump snapshot and fetch raw inputs

Inputs:

- dump date or latest dump discovery
- Wikimedia dump files for `page`, `redirect`, `pagelinks`, and `linktarget`

Why this stage exists:

- every released graph must be tied to one explicit snapshot date
- raw inputs must be public, reproducible, and checksum-verifiable
- downloads should be resumable because the raw dump files are large and CI/local builds can fail mid-transfer
- latest-dump discovery should come from Wikimedia metadata rather than hard-coded dates

### 2. Trim raw SQL dumps into narrow tab-separated streams

Inputs:

- `*.sql.gz` dump files

Outputs:

- `pages.txt.gz`
- `redirects.txt.gz`
- `links.txt.gz`
- `linktarget.txt.gz`

Why this stage exists:

- raw MediaWiki SQL rows contain many columns we do not need at runtime
- downstream stages should operate on a small, explicit contract instead of full SQL
- trimming is the parser boundary, so correctness here protects every later step
- the trim stage is the primary native-optimization seam, because we can replace the parser implementation without changing downstream stage contracts

### 3. Resolve redirects to canonical page ids

Inputs:

- `pages.txt.gz`
- `redirects.txt.gz`

Outputs:

- `redirects.resolved_ids.txt.gz`

Why this stage exists:

- runtime BFS should never chase redirect chains
- redirect handling belongs in the build so the final artifact stays small and deterministic

### 4. Prune pages to canonical article nodes

Inputs:

- `pages.txt.gz`
- `redirects.resolved_ids.txt.gz`

Outputs:

- `pages.pruned.txt.gz`

Why this stage exists:

- the benchmark world currently uses article namespace only
- broken redirects and off-namespace pages must not leak into runtime node ids

### 5. Resolve pagelinks to raw canonical page-id edges

Inputs:

- `pages.txt.gz`
- `linktarget.txt.gz`
- `links.txt.gz`

Outputs:

- `links.raw_ids.txt.gz`

Why this stage exists:

- `pagelinks` references `linktarget` ids, not final canonical page ids
- we need page-id edges before we can normalize redirects and prune invalid edges

### 6. Normalize raw edges against the canonical graph world

Inputs:

- `pages.pruned.txt.gz`
- `redirects.resolved_ids.txt.gz`
- `links.raw_ids.txt.gz`

Outputs:

- `links.normalized_ids.txt.gz`

Why this stage exists:

- redirect targets must be rewritten to canonical destinations
- redirect sources, missing pages, and self-edges must be removed
- this is the stage where raw dump edges become solver-valid graph edges

### 7. Sort, dedupe, and group edges for binary construction

Inputs:

- `links.normalized_ids.txt.gz`

Outputs:

- `links.sorted_by_source_id.txt.gz`
- `links.sorted_by_target_id.txt.gz`
- `links.grouped_by_source_id.txt.gz`
- `links.grouped_by_target_id.txt.gz`

Why this stage exists:

- the binary builder needs stable grouped adjacency, not arbitrary edge order
- both outgoing and incoming adjacency are required for bidirectional BFS
- deduping here keeps the final artifact smaller and the runtime search cleaner

### 8. Build the dated binary artifact

Inputs:

- `pages.pruned.txt.gz`
- `links.grouped_by_source_id.txt.gz`
- `links.grouped_by_target_id.txt.gz`

Outputs:

- `wikiarena_graph_<wiki>_<dump_date>.bin`

Why this stage exists:

- runtime graph ids are dense node ids, not Wikimedia `page_id`s
- the final binary packs title lookup plus forward and reverse adjacency into one file

### 9. Validate and publish release artifacts

Outputs:

- smoke-test results
- compressed binary
- checksums
- metadata JSON
- optional release upload targets

Why this stage exists:

- maintainers need confidence that a dated graph is internally consistent before publishing it

## Required Final Inputs

The binary builder consumes only:

- `dumps/pages.pruned.txt.gz`
- `dumps/links.grouped_by_source_id.txt.gz`
- `dumps/links.grouped_by_target_id.txt.gz`

Everything before that point is build-time machinery.

## Resumability Model

The pipeline is intentionally staged around materialized intermediates.

That gives us three benefits:

- local reruns can skip completed stages after a failure
- stage contracts are easy to test independently
- parser or normalization bugs can be debugged from small intermediate files instead of reprocessing the entire dump every time

This staged design is a deliberate advantage over a more opaque single-pass importer.

## Runtime Contract

The supported local solver runtime consumes the dated binary graph artifact through `BinarySolverBackend`. The graph build scripts are responsible for producing that binary and its metadata; benchmark execution should not depend on intermediate dump-processing files.
