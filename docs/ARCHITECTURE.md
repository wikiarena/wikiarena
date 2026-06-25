# WikiArena Architecture

Last updated: 2026-03-22

This is the high-level map of the current `src/wikiarena` stack.

## Executive Summary

WikiArena is now organized around a protocol-first core runner that executes live Wikipedia navigation tasks, persists append-only run artifacts, and optionally enriches tasks with solver shortest-path evidence.

The main path today is:

- config or CLI input
- protocol specs and benchmark rules
- `RunService` or `BenchmarkRunner`
- `RunExecutor`
- participant adapter + wiki adapter
- `RunResult` and `EventEnvelope` artifacts
- JSONL persistence and offline summaries

## Design Priorities

1. Reproducible benchmark runs
2. Shared core logic across CLI, backend, and replay UI
3. Clear separation between protocol, runtime interfaces, and external adapters
4. Optional solver analysis that does not leak into participant-visible gameplay

## Package Layout

### `src/wikiarena/protocol`

The protocol package defines the shared contracts:

- immutable specs such as `TaskSpec`, `ParticipantSpec`, `RunSpec`, and `BenchmarkSpec`
- benchmark rules such as `NavigationRules`, `HarnessConfig`, `ExecutionPolicy`, and `ScoringRules`
- streaming events via `EventEnvelope`
- persisted results via `StepAttemptRecord`, `MoveRecord`, and `RunResult`
- stable hashing for comparability (`ruleset_hash`, `taskset_hash`, `participant_hash`)

This is the main language the rest of the new system speaks.

### `src/wikiarena/core`

The core package contains the runtime execution engine and runtime-only interfaces.

Important pieces:

- `RunExecutor`: the engine that executes one run
- `ParticipantDriver`: interface for participant adapters
- `WikiNavigator`: interface for page fetching and navigation resolution
- `PageSnapshot`, `ParticipantDecision`, `NavigationResolution`: runtime-only data shapes

The core does not know about provider SDKs or raw Wikipedia HTTP details. It only knows the interfaces it needs.

### `src/wikiarena/adapters`

Adapters connect the core to external systems.

Current examples:

- `adapters/participants/provider_participant.py`: wraps the provider abstraction as a `ParticipantDriver`
- `adapters/wiki/live_wikipedia.py`: wraps live Wikipedia as a `WikiNavigator`
- `adapters/wiki/cached_navigator.py`: adds concurrency-safe caching around a wiki navigator
- `adapters/solver/local_shortest_path_oracle.py`: turns a local solver backend into one task-level solver shortest path

This layer is where external behavior gets translated into the core contracts.

### `src/wikiarena/providers`

This layer normalizes model-provider APIs.

Current providers:

- OpenAI-compatible chat
- OpenRouter via the OpenAI-compatible client path
- Anthropic messages API

This layer is responsible for:

- formatting provider requests and responses
- tool-call translation
- usage and token accounting
- provider-specific behavior such as Anthropic prompt caching and thinking settings

### `src/wikiarena/eval`

This package owns the execution workflows above the single-run engine.

Important pieces:

- `RunService`: plans and executes one run
- `BenchmarkRunner`: executes many runs across tasks and participants with concurrency controls
- `config.py`: loads benchmark configs and tasksets
- `planner.py`: builds stable ids and reproducibility hashes
- `run_result_store.py`: appends `RunResult` artifacts to JSONL
- `summary.py`: loads JSONL results and computes pairwise and Elo summaries

This is the layer that turns the core engine into a practical offline benchmark workflow.

### `src/wikiarena/solver`

This package holds the local shortest-path machinery.

Current direction:

- `BinarySolverBackend` is the official backend going forward
- the production graph artifact uses a dated file name such as `wikiarena_graph_enwiki_20260301.bin`
- search uses a memory-mapped binary graph with outgoing and incoming CSR adjacency

### `src/wikiarena/graph`

This package builds and validates the binary graph artifact.

It handles:

- raw dump preparation
- redirect resolution
- page pruning to canonical article pages
- grouped link intermediates
- binary graph build
- smoke tests and release metadata

This is the build pipeline for the solver data, not the runtime benchmark loop.

CLI ergonomics now sit on top of this package via `wikiarena graph install`, which installs released graph artifacts for local solver use.

## End-To-End Flow

The current benchmark path looks like this:

```text
CLI/config
  -> protocol specs + benchmark rules
  -> RunService / BenchmarkRunner
  -> RunExecutor
  -> ParticipantDriver + WikiNavigator
  -> StepAttemptRecord / EventEnvelope / RunResult
  -> JSONL result store
  -> offline summaries
```

Single-run flow:

```text
wikiarena run
  -> RunRequest
  -> RunService.plan_run()
  -> RunService.execute_plan()
  -> RunExecutor.execute_run()
```

Benchmark flow:

```text
wikiarena eval run
  -> load config + taskset
  -> plan benchmark identity hashes
  -> BenchmarkRunner.run_benchmark()
  -> many RunExecutor-backed runs
  -> append JSONL results
```

## What `RunExecutor` Actually Owns

`RunExecutor` is the heart of the runtime system.

It owns:

- run start/termination lifecycle
- step-attempt recording
- invalid-attempt budgeting
- move budgeting
- harness enforcement
- event emission
- final `RunResult` construction

It does not own:

- raw provider API calls
- raw Wikipedia HTTP calls
- solver graph construction
- benchmark-level orchestration

## Solver Integration Today

The solver is optional and analytical.

Current behavior:

- runs do not require a solver to execute
- solver data should not change the participant-visible link list
- `TaskSpec.shortest_path_length` and `TaskSpec.solver_shortest_path` can carry solver/oracle facts
- the normal run flow only gets a solver shortest path if a `SolverShortestPathOracle` is injected into `RunService` and solver mode is enabled

Important current limitation:

- the binary solver is the intended backend, but the standard CLI/eval flow does not yet wire it in by default

## Reproducibility Model

Comparability is centered on stable hashes and persisted results.

Important pieces:

- `ruleset_hash`: protocol version + navigation rules + harness config + scoring rules
- `taskset_hash`: exact ordered task ids
- `participant_hash`: provider/model/settings with secret-like fields removed

Every run artifact can also carry:

- `protocol_version`
- `engine_commit`
- `navigation_backend`
- `solver_backend`
- `navigation_snapshot_id`
- `solver_snapshot_id`

This is why JSONL `RunResult` artifacts are treated as the main persistent truth.

## Current Intentional Simplifications

- no first-class protocol state objects like `RunState` or `BenchmarkState`
- no requirement that solver be present for the benchmark to run
- no product-specific game state model separate from the protocol/core stack
- no commitment to multiple co-equal local solver backends going forward

## Current Runtime Naming

The protocol now uses a navigation/solver split throughout the runtime surface:

- `NavigationBackend` describes the world the model actually navigates.
- `SolverBackend` describes the shortest-path oracle used for solver path evidence and solver analysis.
- `PathSource.LOCAL_GRAPH` identifies solver shortest paths computed from a local graph-backed solver.

## Recommended Reading Order

If you are new to the repo, read these in order:

1. `docs/PROJECT_GOALS.md`
2. `docs/DECISIONS.md`
3. `docs/ARCHITECTURE.md`
4. `docs/PROTOCOL_V0.md`
5. `docs/SOLVER_BACKENDS.md`
6. `docs/GRAPH_PIPELINE_V1.md`

Then jump into code here:

- `src/wikiarena/protocol/`
- `src/wikiarena/core/run_executor.py`
- `src/wikiarena/eval/run_service.py`
- `src/wikiarena/eval/benchmark_runner.py`
- `src/wikiarena/solver/backends/binary_backend.py`
