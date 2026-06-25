# WikiArena Source Strategy

- Prefer protocol-first design: shared models/events/results power CLI, backend, and frontend.
- Optimize for reproducible research runs first; product/UI integrations should consume the same core artifacts.
- Keep solver facts as async enrichment: run execution owns moves/termination, solver returns graph facts for page-target pairs, and UI/live/replay consume protocol events rather than frontend-specific truth.
- CLI defaults should prefer installed graph snapshots for navigation plus local solver; official eval configs pin runtime `snapshot_id` values, and pins must select or validate that installed graph instead of falling back to latest.
- Tool-call gameplay is single-click: multiple tool calls in one model response are a malformed step, no navigation commits, and every returned tool call id must receive an error tool result before the next model turn.
- Live/replay UI should consume protocol-native race streams: one WebSocket per race, append-only `artifacts/races/<race_id>/events.jsonl`, and frontend state derived by reducers from `EventEnvelope` records rather than bespoke game events.
- Codex provider request shaping: the ChatGPT Codex backend is Responses-like but narrower than public OpenAI Responses. Keep a narrow allowlist; it rejects `max_tokens`/`max_output_tokens`, `temperature`, `top_p`, `prompt_cache_retention`, and priority/fast `service_tier`, while accepting `prompt_cache_key`, `reasoning.summary`, and `include: ["reasoning.encrypted_content"]`.
- Provider pricing is fail-closed: production calls must have built-in or explicit `input_cost_per_1m_tokens` and `output_cost_per_1m_tokens`; explicit base prices should not silently inherit built-in cache or long-context rates.
