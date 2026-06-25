# WikiArena Project Goals

Last updated: 2026-03-22

This is a directional scratch doc. The current source of truth for active architecture is the code under `src/wikiarena`.

## Vision

Build a credible, open, reproducible Wikipedia navigation benchmark for language models, then turn it into a polished public experience where people can watch and race models in real time.

## Current Shipping Priorities

1. Keep the offline CLI evaluation path as the primary way to run WikiArena.
2. Make benchmark runs reproducible through stable configs, tasksets, hashes, and JSONL result artifacts.
3. Publish meaningful benchmark results before investing heavily in product polish.
4. Keep backend and frontend work downstream of the shared core protocol and runner.

## Architecture Goals

1. Treat `src/wikiarena` as the only active implementation namespace.
2. Use `benchmark`, `race`, `run`, and `step attempt` as the canonical domain model.
3. Keep one shared protocol/core stack for CLI, backend orchestration, and replay UI.
4. Persist append-only run artifacts and derive summaries from those artifacts instead of maintaining separate result models per surface.

## Protocol and Fairness Goals

1. Standardize IDs and hierarchy around `benchmark_id`, `race_id`, `run_id`, and `step_index`.
2. Record both invalid and valid step attempts for transparent analysis.
3. Keep harness configuration benchmark-level and immutable within a benchmark run.
4. Track reproducibility metadata in every run result: protocol version, engine commit, ruleset hash, taskset hash, participant hash, solver mode, and wiki snapshot id.
5. Keep solver annotations explicit and non-player-visible.

## Benchmark Design Principles

1. Expose the full ordered set of visible article links on a page in the official benchmark.
2. Do not truncate links or solver-filter the participant view.
3. Treat large pages as strategically valuable but context-expensive; that tradeoff is part of the benchmark.
4. Prefer realistic Wikipedia navigation over artificially simplified search spaces.

## Solver and Data Goals

1. The official local solver backend is the binary CSR graph behind `BinarySolverBackend`.
2. Solver use stays optional for basic benchmark execution.
3. Official solver-backed claims should use a graph that matches the article-namespace world exposed by live runs.
4. Large graph artifacts stay outside git and ship as external data/release assets.

## Near-Term Technical Priorities

1. Make the binary solver oracle a first-class part of the standard eval flow.
2. Stabilize taskset/config/result workflows for public benchmark runs.
3. Keep shrinking the gap between scratch docs and the implemented `src/wikiarena` stack.

## Product Goals (After Initial Publish)

1. Build a much better replay/race viewing experience.
2. Expose an internet-facing experience for non-technical users.
3. Expand UX without creating a second source of benchmark logic.

## Decision Rules

When tradeoffs appear, prioritize in this order:

1. Reproducibility and fairness of benchmark outputs.
2. Shared core architecture that avoids logic drift.
3. Fast path to publish meaningful results.
4. Product polish and deployment breadth.

## Current Non-Goals

1. Keeping multiple first-class solver backends alive long-term.
2. Requiring remote infrastructure for basic benchmark execution.
3. Perfecting every UI workflow before publishing offline eval results.
