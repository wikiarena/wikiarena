# Frontend Replay v1

## Goal

Build a replay-first frontend for protocol-native benchmark artifacts.

The first version should make static benchmark results interactive without depending on the backend. It should load `RunResult` JSONL artifacts, group them into races, and let users step through model behavior side by side.

## Why Replay First

- It is immediately useful for benchmark analysis and publishing.
- It aligns the frontend with protocol-native benchmark artifacts.
- It creates reusable UI/state primitives for a later live race mode.
- It keeps the initial public benchmark launch interactive even on a static site.

## Strategy

- Keep replay state derived from protocol artifacts.
- Keep graph visualization optional until replay state is stable.
- Avoid creating frontend-only benchmark truth.

## v1 Architecture

- `frontend/replay.html`
  - new page shell for replay UI
- `frontend/replay/app.ts`
  - bootstrap + top-level orchestration
- `frontend/replay/protocol.ts`
  - protocol-native frontend types and JSONL parsing helpers
- `frontend/replay/store.ts`
  - small subscription-based replay store
- `frontend/replay/selectors.ts`
  - pure derived-state helpers for race summaries and replay stepping
- `frontend/replay/view.ts`
  - DOM rendering for controls, race list, summaries, and timeline panels
- `frontend/replay.css`
  - page-specific styling

## Initial Scope

1. Load a sample replay artifact and local JSONL files.
2. Group runs by `race_id`.
3. Select a race and scrub by committed move index.
4. Compare participants side by side.
5. Show invalid attempts, current page, token usage, duration, and outcome.

## Deferred

- Live WebSocket race mode
- Graph visualization integration with the existing D3 renderer
- Full static website navigation / marketing shell integration
- Result filtering, search, and deep linking beyond a basic race selector
