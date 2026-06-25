# WikiArena Protocol v0

Last updated: 2026-03-22

This doc now describes the protocol as it is currently implemented in `src/wikiarena`, not the larger set of ideas we originally sketched.

## Goals

- Use one domain model for offline eval, backend orchestration, and replay/frontend consumers.
- Make runs reproducible and comparable across machines.
- Keep solver support optional.
- Avoid contract drift by separating immutable specs, benchmark rules, streaming events, and persisted results.

## Canonical Terms

- Task: a single navigation objective (`start_page_title` -> `target_page_title`)
- Participant: an actor that can execute runs (`llm`, `human`, `scripted`)
- Run: one participant attempting one task
- Race: a set of runs on the same task
- Benchmark: a collection of races over a task pack and participant set
- Step attempt: every participant action, valid or invalid
- Move: a committed navigation step

## Current Design Principles

1. Specs are immutable input contracts.
2. Benchmark rules are explicit and hashable.
3. Event ordering is explicit through per-run sequence numbers.
4. Final artifacts are append-only and self-contained enough for offline analysis.
5. Solver annotations are optional and always mode-labeled.

## Implemented Model Layers

### Specs And Rules

- `TaskSpec`
- `ParticipantSpec`
- `RunSpec`
- `RaceSpec`
- `BenchmarkSpec`
- `SolverShortestPath`
- `NavigationRules`
- `HarnessConfig`
- `ExecutionPolicy`
- `ScoringRules`
- `BenchmarkRules`

### Events

- `EventEnvelope`

### Results

- `StepAttemptRecord`
- `MoveRecord`
- `RunResult`
- `RaceResult`
- `BenchmarkResult`

## What Is Not A Protocol Model Right Now

Some things that appeared in the older draft are not protocol models in the current code:

- `RunState`
- `RaceState`
- `BenchmarkState`
- protocol-level `PageRef`
- protocol-level `PageSnapshot`

Those runtime-only concepts currently live in `wikiarena.core` and adapter interfaces instead.

## Specs

### `TaskSpec`

- canonical fields: `language`, `start_page_title`, `target_page_title`
- auto-validates and fills canonical `task_id`
- can optionally carry `shortest_path_length` and one `solver_shortest_path`

### `ParticipantSpec`

- canonical participant identity lives here
- provider/model/settings live inside `driver_config`
- provider is not a top-level protocol entity

### `RunSpec`

- immutable run input contract
- includes `run_id`, `benchmark_id`, `race_id`, `task_id`, `participant_id`, and `navigation_rules`
- exposes derived `max_step_attempts`

### `BenchmarkSpec`

- top-level input object for benchmark execution
- includes participants, tasks, benchmark rules, and `taskset_id`
- validates unique participant ids and task ids

## IDs And Reproducibility Hashes

Stable ids:

- `benchmark_id`
- `race_id`
- `run_id`
- `task_id`
- `participant_id`
- `taskset_id`

Reproducibility hashes:

- `ruleset_hash`: protocol version + navigation rules + harness config + scoring rules
- `taskset_hash`: exact ordered task ids
- `participant_hash`: provider/model/settings with secret-looking fields stripped

If `ruleset_hash` differs, results are different benchmark tracks.

## Events

The current event stream is intentionally small:

- `run_started`
- `step_attempt_recorded`
- `move_committed`
- `run_terminated`

`step_attempt_recorded` is the canonical step-level event. `move_committed` is a convenience event derived from successful step attempts.

## Results

### `StepAttemptRecord`

This is the canonical run history. It preserves invalid attempts.

Current implemented fields include:

- `step_index`
- `move_index` for committed moves only
- `from_page_title`
- `selected_link_text`
- `requested_to_page_title`
- `resolved_to_page_title`
- `was_redirect`
- `outcome`
- `rejection_reason_code`
- `consumed_invalid_budget`
- `consumed_step_budget`
- `duration_ms`
- `model_metrics`
- `solver_metrics`
- `error`
- `occurred_at`

### `MoveRecord`

- convenience projection of committed moves
- can be provided directly or derived from committed step attempts

### `RunResult`

Current run results include:

- identity fields (`run_id`, `race_id`, `benchmark_id`, `task_id`, `participant_id`)
- terminal fields (`status`, `terminal_outcome`, `termination_reason`)
- ordered step attempts and committed moves
- derived totals for attempts, committed moves, and invalid attempts
- ranking eligibility fields
- protocol/reproducibility fields
- timing fields (`started_at`, `ended_at`, `duration_ms`)

`RunResult` derives counters, derives committed moves when missing, validates contiguous step and move indexes, and computes default ranking eligibility.

## Error Model

`ErrorRecord` is the shared error shape.

Current scopes are:

- `step`
- `run`
- `race`
- `benchmark`
- `setup`

Errors can be attached to step attempts, run results, race results, benchmark results, and event envelopes.

## Navigation And Harness Rules

### `NavigationRules`

Implemented fields:

- `max_moves`
- `max_invalid_attempts_per_run`
- `max_invalid_attempts_per_step_context`
- `invalid_attempt_consumes_step_budget`
- `terminate_on_invalid_budget_exhaustion`
- `link_policy`
- `redirect_policy`

Current defaults:

- `max_moves = 50`
- `max_invalid_attempts_per_run = 15`
- `max_invalid_attempts_per_step_context = 2`
- `invalid_attempt_consumes_step_budget = false`
- `terminate_on_invalid_budget_exhaustion = true`
- `link_policy = raw_ordered`
- `redirect_policy = resolve_after_selection`

### `HarnessConfig`

Implemented fields:

- `harness_id`
- `response_contract`
- `tool_name`

Supported response contracts:

- `tool_call_only`
- `structured_output_only`

### `ScoringRules`

Implemented fields:

- `exclude_system_failures_from_ranking`
- `tie_breaker`

Current default ranking behavior is:

- include `success`
- include `model_failure`
- exclude `system_failure` unless scoring rules say otherwise
- exclude `cancelled`

## Step Attempt Semantics

- Each participant gets one run per task within a race.
- Retries are represented as additional step attempts in the same run.
- Invalid participant-visible actions are protocol-visible and stored.
- Provider transport retries are execution behavior and should not become extra step attempts unless they change participant-visible output.

## Solver-Related Protocol Status

- `TaskSpec` supports optional `shortest_path_length` and `solver_shortest_path`.
- `RunResult` includes `navigation_backend`, `solver_backend`, `navigation_snapshot_id`, and `solver_snapshot_id`.
- `RunResult` can also carry a minimal `task_execution_annotation` with solver-derived task facts for that execution context.
- `StepAttemptRecord` has optional `solver_metrics`; local solver runs now populate `distance_before` and `distance_after` for committed moves.
- The current run/eval flow attaches one task-level solver shortest path for graph-backed solver runtimes and for injected shortest-path oracles.

Current implemented solver/path enums use the navigation/solver split:

- `SolverBackend`: `none`, `local`, `remote`
- `PathSource`: `local_graph`, `remote_solver`, `live_solver`, `run_trace`

## Minimal Implemented v1 Surface

If we treat only the actually useful current surface as "v1", the important locked pieces are:

1. `TaskSpec`
2. `ParticipantSpec`
3. `RunSpec`
4. `NavigationRules`
5. `HarnessConfig`
6. `StepAttemptRecord`
7. `RunResult`
8. `EventEnvelope`
9. reproducibility hashes

## Open Cleanup Items

1. Make the binary solver oracle a first-class part of CLI/eval workflows.
2. Decide whether replay/product work actually needs formal protocol state objects.
3. Decide how much solver analysis should live in race-level versus run-level artifacts.
