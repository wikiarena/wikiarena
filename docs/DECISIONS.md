# WikiArena Decisions

Last updated: 2026-03-22

This file records benchmark and architecture decisions that should stay stable across refactors.

## Settled Decisions

### Source Of Truth

- Implementation work happens in `src/wikiarena`.

### Core Vocabulary

- `task`: start page -> target page
- `participant`: actor attempting tasks
- `run`: one participant attempting one task
- `race`: multiple runs on the same task
- `benchmark`: a set of races over a taskset and participant set
- `step attempt`: every participant action, valid or invalid
- `move`: a committed navigation step
- `game`: avoid in new code; prefer `run` or `race`

### Protocol Shape

- The implemented protocol centers on immutable specs, benchmark rules, event envelopes, and persisted results.
- Runtime-only concepts such as page snapshots, participant decisions, and wiki navigation interfaces live in `wikiarena.core`, not as first-class protocol models.
- Append-only JSONL run results are the current persistence unit; race and benchmark summaries are derived from run results.

### Benchmark Fairness

- Official comparisons are defined by `ruleset_hash`.
- `taskset_hash` identifies the exact ordered task set used for a run.
- `participant_hash` fingerprints provider/model/settings with secret-like fields removed.
- Result files may only be appended to when `ruleset_hash` matches.
- Harness configuration is benchmark-level and immutable within a benchmark run.

### Link Exposure

- The official benchmark exposes the full ordered set of visible links.
- We do not truncate links.
- We do not solver-filter or shortest-path-filter the links shown to the participant.
- Large pages are intentionally both strategically valuable and context-expensive.

### Harness Behavior

- Response contract is fixed at the benchmark level.
- Supported official response contracts are:
  - `tool_call_only`
  - `structured_output_only`
- Mixed response modes are not part of the official benchmark.

### Solver Role

- Solver data is analytical, not player-visible.
- Solver information must not change which links a participant sees.
- Solver remains optional for basic benchmark execution.
- The official local solver backend is `BinarySolverBackend` over a dated graph binary such as `wikiarena_graph_enwiki_20260301.bin`.

### Solver Graph Semantics

- The official solver graph should match the benchmark world.
- Live runs currently expose article-namespace links only, so official solver snapshots should also be article-namespace-only.
- Redirects should be resolved to canonical article pages during graph construction.
- Shortest path labels should be computed over the same graph the participant is allowed to navigate.
- We should not publish solver-backed claims from a broader graph that includes off-benchmark namespaces.

### Solver Interface Expectations

- Keep a small shared solver interface so benchmark code does not depend on backend internals.
- Target sessions remain part of the interface, but they are not required for the official backend.
- The current production binary backend returns one deterministic shortest path, not all shortest paths.

### Anthropic Defaults

- Prompt caching is enabled by default.
- Adaptive thinking is the preferred path for current Claude models.
- Manual thinking budgets remain supported when explicit control is needed.

## Current Implementation Notes

### Live Wikipedia World

- The live benchmark currently fetches article-namespace links only (`namespace = 0`).
- This is not just a draft rule; it is current implementation behavior.

## Open Decisions

### Official Taskset Construction

- Candidate tasks should be generated broadly, likely via random Wikipedia sampling plus filtering and solver scoring.
- The final official taskset will likely still be manually curated for quality and diversity.

### Solver Provenance Naming

- We still need to decide the final public-facing names for local binary solver provenance in protocol enums and artifacts.
