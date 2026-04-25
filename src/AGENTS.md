# WikiArena Source Strategy

- Build new features only in `src/wikiarena` (greenfield vNext).
- Treat `src/wiki_arena` as legacy reference code, not the place for new architecture work.
- Keep compatibility shims thin and temporary (imports/contracts only, not duplicated behavior).
- Prefer protocol-first design: shared models/events/results power CLI, backend, and frontend.
- Optimize for reproducible research runs first; product/UI integrations should consume the same core artifacts.
- Keep solver facts as async enrichment: run execution owns moves/termination, solver returns graph facts for page-target pairs, and UI/live/replay consume protocol events rather than frontend-specific truth.
- CLI defaults should prefer installed graph snapshots for navigation plus local solver; explicit `live` navigation or `none` solver modes are opt-outs for audit/debug runs.
- Tool-call gameplay is single-click: multiple tool calls in one model response are a malformed step, no navigation commits, and every returned tool call id must receive an error tool result before the next model turn.
