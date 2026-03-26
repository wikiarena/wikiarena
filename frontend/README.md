# WikiArena Frontend

Static frontend for the public WikiArena solver experience.

## Current Layout

- `src/` contains the active solver site
- `index.html` is the solver homepage
- `legacy/` preserves the older race-viewer frontend

## Development

```bash
bun run dev
```

The site expects the solver API at `http://localhost:8000` in local development unless `VITE_API_BASE_URL` is set.

## Legacy Viewer

```bash
bun run dev:legacy
```

## Checks

```bash
bun run type-check
bun run build
```
