# WikiArena v0 benchmark config

This directory contains the tracked configuration and taskset for the WikiArena v0 benchmark. It is intended to be the reproducible source of truth for public reruns; generated results and replay artifacts belong under `artifacts/` or release assets, not here.

## Files

- `eval.toml` - benchmark rules, runtime settings, participant specs, and concurrency limits.
- `taskset.jsonl` - exact 500-task taskset used for v0.
- `taskset_summary.json` - summary statistics for `taskset.jsonl`.

## Identity

- benchmark id: `wikiarena_v0`
- taskset id: `wikiarena_v0_500_seed20260419`
- protocol harness: `tool_strict_v1`
- navigation backend: `graph`
- solver backend: `local`
- taskset identity hash: `9e7c178197819d4b1d6ec529c0a964fecb371a8d0f8cc2b3a2dc36577e74ad7c`
- `taskset.jsonl` sha256: `3a5a0d692f4c629acb25634205baf2b16a6eea98d65e348bf2dec8f04035ce20`
- `taskset_summary.json` sha256: `4301c799d4434aed828d2eafcdbe099b1bc0a397f8b3e35510d0e2b48c7c903b`

## Provider notes

- The GPT runs in the original v0 publication used the `codex` provider with model `gpt-5.5`. Existing participants keep their original driver settings so resume can reuse migrated v0 artifacts. New Codex participants may set `provider_settings.codex_transport = "websocket"` explicitly; the provider default also uses the upstream Codex-style Responses WebSocket path with HTTP fallback. Use `websocket_only` only in validation configs where a transport fallback would hide a regression.
- The config intentionally does not enable `provider_settings.codex_websocket_prewarm`; prewarm sends an extra model API call and should not be used for publishable benchmark artifacts until API-call-level telemetry accounts for it.
- Anthropic participants use the `anthropic` provider. Provider credentials and endpoint routing are intentionally runtime-only and are not stored in the tracked benchmark config.
- Provider-level concurrency is capped at 3 for both `codex` and `anthropic` so adding participants does not silently double the concurrent load on either provider.

The config intentionally does not contain API keys, auth file paths, or local graph paths. Those are resolved from the local runtime environment when the benchmark is executed.
