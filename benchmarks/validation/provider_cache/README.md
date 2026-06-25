# Provider cache validation

This directory contains a small tracked benchmark for validating provider transport and token-cache accounting against real APIs. It is not part of the official v0 taskset; keep public benchmark definitions under `benchmarks/wikiarena/v0/`.

## Files

- `eval.toml` - eval config used for provider cache validation.
- `taskset.jsonl` - short validation tasks on `enwiki-20260401`.

## Task choice

The first task is `OpenAI` to `Claude Shannon`. The local solver validates it as distance 2 on `enwiki-20260401` with 99 shortest paths, making it short enough to stay cheap and forgiving enough to avoid model flakiness. The reverse direction, `Claude Shannon` to `OpenAI`, is also distance 2 but has 9 shortest paths.

The second task is `Deep learning` to `Singularity`, from the frontend home-preview display set. The local solver validates it as distance 3 on `enwiki-20260401` with 42 shortest paths. This gives provider-cache validation at least one longer successful run, which makes repeated continuation and cache-read behavior easier to observe than a single distance-2 case.

## Expected evidence

A successful provider cache validation run should solve both tasks. The distance-2 task should require at least two model calls, and the distance-3 task should require at least three model calls. For providers that report cache reads, at least one follow-up call should show positive `cache_read_input_tokens`; if the longer task reports zero cache reads on every follow-up call, treat that as evidence to investigate provider continuation or cache routing.

The Codex participant in `eval.toml` uses `provider_settings.codex_transport = "websocket_only"` intentionally. Official benchmark configs should normally use `websocket`, which matches the upstream Codex preference while preserving HTTP fallback. This validation config disables fallback so WebSocket protocol regressions fail loudly.
