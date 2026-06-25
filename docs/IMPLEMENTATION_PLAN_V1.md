# WikiArena v1 Implementation Notes

Last updated: 2026-03-22

This file records what v1 already has, what we intentionally stopped doing, and what remains.

## Goal

Keep building a protocol-first, reproducible evaluation stack that runs offline without a web UI, while leaving room for backend/frontend consumers later.

## What Is Already In Place

- `src/wikiarena/` is the active package namespace.
- The protocol package exists and is used by the runner, eval flow, CLI, and tests.
- `RunExecutor` is the core execution engine and emits `EventEnvelope` plus `RunResult` artifacts.
- `RunService` and `BenchmarkRunner` provide single-run and benchmark execution paths.
- Benchmark configs and tasksets load from JSON/TOML/JSONL.
- Run artifacts persist as append-only JSONL through `RunResultStore`.
- Summary generation and ranking-eligibility handling exist.
- Provider abstractions exist for `openai`, `anthropic`, and `openrouter`.
- Shared cached live-Wikipedia navigation exists for multi-run benchmark execution.
- The graph pipeline and official binary solver backend now exist under `src/wikiarena/graph/` and `src/wikiarena/solver/`.

## What Changed From The Original Plan

- The offline CLI path is no longer just a future phase; it is the main implemented path.
- The binary CSR solver is no longer an experiment; it is the intended backend going forward.
- The protocol has been simplified toward what is actually implemented instead of modeling large unbuilt layers first.

## What We Are Intentionally Not Doing

- Keeping multiple first-class local solver backends alive long-term.
- Expanding protocol surface area before a real caller needs it.

## Remaining v1 Work

1. Make the binary solver oracle a first-class option in the standard CLI/eval flow instead of only supporting injected reference oracles.
2. Decide how much solver analysis should live in persisted run artifacts versus task-level reference data.
3. Harden taskset, config, and result workflows for public benchmark publication.
4. Continue shrinking the amount of important knowledge that only lives in scratch docs.

## Backend And Frontend Status

- Backend/frontend work is downstream of the benchmark core, not the owner of benchmark state.
- Future backend/frontend work should consume `wikiarena` protocol artifacts rather than recreate separate game/run models.

## Implementation Guardrails

1. Build new features only in `src/wikiarena`.
2. Keep new integrations downstream of protocol artifacts rather than separate game/run models.
3. Prefer simplifying old plans over preserving them when the implementation has already moved on.
4. Keep result artifacts append-only unless a versioned protocol change requires otherwise.

## Current Next Steps

1. Wire the binary solver path into the normal eval workflow.
2. Clean up naming debt around local solver provenance.
3. Use the existing CLI/config/result pipeline to run and publish benchmark results.
