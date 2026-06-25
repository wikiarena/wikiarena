# WikiArena CLI Guide

This guide covers the user-facing CLI for running ad hoc tasks, benchmark configs, and result summaries.

For a deeper explanation of live vs offline wiki behavior, see [`WIKI_MODES.md`](WIKI_MODES.md).

## Installation

Prerequisites:

- Python 3.11+
- `uv`

```bash
git clone https://github.com/wikiarena/wikiarena.git
cd wikiarena
uv sync --dev
uv run wikiarena --help
```

Set the provider credential your chosen model requires:

```bash
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
```

## Command Overview

WikiArena currently exposes five primary commands:

```text
wikiarena graph install
wikiarena graph info
wikiarena run
wikiarena eval run
wikiarena eval summarize
```

Use `uv run wikiarena --help` or `uv run wikiarena <command> --help` to inspect the full option list.

## `wikiarena graph install`

Download, verify, decompress, and install an official published graph release for offline runs.

### Install the latest published graph

```bash
uv run wikiarena graph install
```

By default, WikiArena installs graphs into the per-user application data graph directory. On macOS, that default location is `~/Library/Application Support/wikiarena/graphs/`.

### Install a specific release tag

```bash
uv run wikiarena graph install --tag graph-enwiki-20260301
```

### Useful options

- `--tag`: install a specific published graph release tag instead of the latest matching release
- `--repo`: GitHub repository containing graph releases, default `wikiarena/wikiarena`
- `--install-dir`: override the destination directory for installed graph binaries
- `--force`: reinstall even if the matching graph is already installed and verified

## `wikiarena graph info`

Inspect the graph that WikiArena will use for offline runs, or inspect a specific local graph file.

### Show the active default graph

```bash
uv run wikiarena graph info
```

### Verify the installed graph against its metadata

```bash
uv run wikiarena graph info --verify
```

### Inspect a specific graph path as JSON

```bash
uv run wikiarena graph info \
  --graph-path /path/to/wikiarena_graph_enwiki_20260301.bin \
  --json
```

### Useful options

- `--graph-path`: inspect a specific local graph binary instead of the active default graph
- `--verify`: recompute checksums and verify counts against the metadata sidecar
- `--json`: print graph info as JSON

## `wikiarena run`

Run one model on one Wikipedia navigation task.

### Basic live run

```bash
uv run wikiarena run \
  --model gpt-4.1-nano-2025-04-14 \
  --provider openai \
  --start Apple \
  --target Banana
```

If you omit both `--start` and `--target`, WikiArena selects two random article titles automatically and prints the chosen task to stderr before running.

For OpenAI-compatible providers, `wikiarena run` defaults reasoning effort to `high` unless you explicitly pass `--reasoning-effort`.

### OpenAI Responses API trace

```bash
uv run wikiarena run \
  --model gpt-5.2 \
  --provider openai \
  --trace
```

For `--provider openai`, this uses the OpenAI Responses API by default. `--trace` prints the request/response transcript but does not change reasoning settings.

### OpenAI reasoning summaries

```bash
uv run wikiarena run \
  --model gpt-5.2 \
  --provider openai \
  --trace \
  --openai-reasoning-summary detailed
```

Reasoning summaries are opt-in. When a provider returns one, trace output prints it as the assistant thinking block.

### Anthropic thinking trace

```bash
uv run wikiarena run \
  --model claude-sonnet-4-6 \
  --provider anthropic \
  --trace \
  --thinking-effort high
```

Anthropic thinking is opt-in through `--thinking-effort` or `--thinking-budget-tokens`. `--trace` only controls transcript logging.

### OpenAI encrypted reasoning replay experiment

```bash
uv run wikiarena run \
  --model gpt-5.2 \
  --provider openai \
  --trace \
  --openai-include-encrypted-reasoning \
  --openai-no-previous-response-id
```

This keeps the visible message history and replays encrypted reasoning items from prior OpenAI responses instead of continuing with `previous_response_id`. It is useful as an ablation when you want to compare hidden reasoning carryover strategies.

### Offline graph run

```bash
uv run wikiarena run \
  --model claude-haiku-4-5-20251001 \
  --provider anthropic \
  --start Apple \
  --target Banana \
  --offline
```

If you want to pin a specific local graph explicitly:

```bash
uv run wikiarena run \
  --model claude-haiku-4-5-20251001 \
  --provider anthropic \
  --start Apple \
  --target Banana \
  --offline \
  --navigation-graph-path /path/to/wikiarena_graph_enwiki_20260301.bin
```

### Live navigation with a local graph solver

```bash
uv run wikiarena run \
  --model claude-haiku-4-5-20251001 \
  --provider anthropic \
  --start Apple \
  --target Banana \
  --solver-backend local \
  --solver-graph-path /path/to/wikiarena_graph_enwiki_20260301.bin
```

### Useful options

- `--model`: model identifier to evaluate
- `--provider`: provider name such as `openai` or `anthropic`
- `--start`: start page title; omit together with `--target` to auto-pick a random task
- `--target`: target page title; omit together with `--start` to auto-pick a random task
- `--language`: Wikipedia language edition, default `en`
- `--navigation-backend`: choose `live` or `graph` for the pages and links the run actually navigates against
- `--offline`: alias for `--navigation-backend graph`
- `--navigation-graph-path`: explicit path to the graph snapshot used for navigation; requires graph navigation backend
- `--navigation-snapshot-id`: optional navigation snapshot override; if omitted in graph mode, WikiArena infers it from the selected graph filename
- `--solver-backend`: choose `none`, `local`, or `remote` for solver shortest-path data
- `--solver-graph-path`: explicit path to the graph snapshot used by the local graph solver
- `--solver-snapshot-id`: optional solver snapshot override
- `--solver-endpoint`: remote solver endpoint when `--solver-backend remote` is selected
- `--response-contract`: benchmark interaction contract
- `--tool-name`: navigation tool name for tool-call mode
- `--temperature`, `--max-tokens`, `--reasoning-effort`: model generation controls
- `--thinking-effort` or `--thinking-budget-tokens`: provider-specific thinking controls
- `--openai-use-responses-api`: for `openai_compatible`, switch to the Responses API; `openai` already uses Responses by default
- `--openai-reasoning-summary`: request summarized OpenAI reasoning in Responses API output
- `--openai-include-encrypted-reasoning`: request encrypted OpenAI reasoning items in Responses API output
- `--openai-use-previous-response-id` / `--openai-no-previous-response-id`: choose OpenAI Responses continuation via `previous_response_id` or full-history replay
- `--base-url`: override provider base URL
- `--output`: optional JSONL output path
- `--append` or `--overwrite`: control behavior when `--output` already exists
- `--json`: print the full run result as JSON

`--thinking-effort` and `--thinking-budget-tokens` are mutually exclusive.

For OpenAI-compatible providers (`openai`, `openai_compatible`, and `openrouter`), `wikiarena run` now defaults `--reasoning-effort` to `high` when you do not pass an explicit value. Use `--reasoning-effort none` or another explicit level to override that default.

`--provider openai` now always uses the OpenAI Responses API. OpenAI Responses flags apply to `--provider openai` and `--provider openai_compatible`. When Responses mode is enabled, trace output also prints any token breakdown fields returned by the provider, such as cached prompt tokens and reasoning tokens. `--trace` does not request reasoning summaries or provider thinking by itself.

`--navigation-graph-path` and `--solver-graph-path` are intentionally separate.

- `--navigation-graph-path` changes the navigation backend and therefore the world the model actually plays in
- `--solver-graph-path` only changes the solver/reference snapshot

If you pass `--navigation-graph-path`, you must also select graph navigation via `--navigation-backend graph` or `--offline`.

Today, the shipped CLI supports `solver_backend=none` and `solver_backend=local`. `remote` is reserved for future integration work.

## `wikiarena eval run`

Run a benchmark config containing one or more participants against a taskset.

### Example

```bash
uv run wikiarena eval run \
  --config examples/eval.toml \
  --output results.jsonl
```

### Override the config to use offline graph mode

```bash
uv run wikiarena eval run \
  --config examples/eval.toml \
  --output results.jsonl \
  --offline \
  --navigation-graph-path /path/to/wikiarena_graph_enwiki_20260301.bin
```

### Keep live navigation but use a local graph solver

```bash
uv run wikiarena eval run \
  --config examples/eval.toml \
  --output results.jsonl \
  --solver-backend local \
  --solver-graph-path /path/to/wikiarena_graph_enwiki_20260301.bin
```

### Main options

- `--config`: required benchmark config path (`.toml` or `.json`)
- `--output`: JSONL output path
- `--append` or `--overwrite`: control reuse of an existing output file
- `--json`: print a benchmark completion summary as JSON
- `--print-hashes`: include ruleset/taskset hashes in the default text output
- navigation overrides: `--navigation-backend`, `--offline`, `--navigation-graph-path`, `--navigation-snapshot-id`
- solver overrides: `--solver-backend`, `--solver-graph-path`, `--solver-snapshot-id`, `--solver-endpoint`

`--navigation-graph-path` requires graph navigation mode; `--solver-graph-path` requires `--solver-backend local`.

### Config shape

See [`examples/eval.toml`](../examples/eval.toml) for a working example. The relevant offline section looks like this:

```toml
[run_options.navigation_runtime]
backend = "graph"
graph_path = "/path/to/wikiarena_graph_enwiki_20260301.bin"

[run_options.solver_runtime]
backend = "local"
```

If you omit `[run_options.navigation_runtime]`, the config defaults to live navigation. If you omit `[run_options.solver_runtime]`, the config defaults to no solver.

If `navigation_snapshot_id` or `solver_snapshot_id` is omitted for a graph-backed runtime, WikiArena infers `enwiki-20260301` from `wikiarena_graph_enwiki_20260301.bin`.

## `wikiarena eval summarize`

Summarize JSONL run artifacts produced by `wikiarena run --output` or `wikiarena eval run`.

### Table output

```bash
uv run wikiarena eval summarize --input results.jsonl
```

### JSON output

```bash
uv run wikiarena eval summarize --input results.jsonl --format json
```

### Markdown output

```bash
uv run wikiarena eval summarize --input results.jsonl --format markdown
```

### Options

- `--input`: required JSONL results file
- `--format`: `table`, `json`, or `markdown`
- `--tie-breaker`: summary ranking tie-break policy

## Wiki Backend Selection

WikiArena supports two wiki backends:

- `live`: fetch current page state from the live Wikipedia API
- `graph`: read from a local dated graph snapshot

You can select the navigation backend in either of these ways:

```bash
wikiarena run --navigation-backend live ...
wikiarena run --offline ...
```

`--offline` is just a convenient alias for `--navigation-backend graph`.

Solver shortest-path data is configured separately:

```bash
wikiarena run --solver-backend none ...
wikiarena run --solver-backend local --solver-graph-path /path/to/wikiarena_graph_enwiki_20260301.bin ...
```

### Graph path resolution order

When graph navigation is selected, WikiArena resolves the navigation graph file in this order:

1. `--navigation-graph-path`
2. `WIKIARENA_GRAPH_PATH`
3. the newest dated graph file in the default per-user application data graph directory, for example on macOS `~/Library/Application Support/wikiarena/graphs/wikiarena_graph_enwiki_20260301.bin`

If no graph file is found, the command fails fast with a clear error message.

If `--navigation-snapshot-id` is omitted in graph mode, WikiArena infers it from the selected dated graph filename.

For example, `wikiarena_graph_enwiki_20260301.bin` maps to `enwiki-20260301`.

### Important note

Graph mode is intentionally different from live mode. It resolves redirects during graph construction, canonicalizes visible page titles, removes duplicate links, and uses deterministic graph ordering. It is the right mode for reproducible offline evaluation, not for exact live-page fidelity.

See [`WIKI_MODES.md`](WIKI_MODES.md) for the full behavior differences.

## Output Files and Append Safety

WikiArena uses JSONL output so each run is a durable artifact that can be inspected and summarized later.

- `wikiarena run --output results.jsonl` writes a run result line
- `wikiarena eval run --output results.jsonl` appends one line per run
- `--append` and `--overwrite` are mutually exclusive

When appending, WikiArena validates compatibility so you do not accidentally mix:

- different `ruleset_hash` values
- different navigation backends
- different navigation snapshot ids when a snapshot id is pinned
- different solver backends
- different solver snapshot ids when a snapshot id is pinned

## Troubleshooting

### Missing graph file

If `--offline` or `--navigation-backend graph` is set and no graph file can be found, either:

- run `wikiarena graph install`
- pass `--navigation-graph-path /path/to/wikiarena_graph_enwiki_20260301.bin`
- set `WIKIARENA_GRAPH_PATH`
- move the file into the default per-user application data graph directory using a dated name like `wikiarena_graph_enwiki_20260301.bin` so WikiArena can pick it as the newest installed graph

### Existing output path error

If the output file already exists, choose one of:

- `--append` to keep writing compatible results into the same file
- `--overwrite` to replace the file completely

### Provider auth or proxy setup

Use normal provider environment variables such as `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`. If you are targeting an OpenAI-compatible endpoint, use `--base-url` to point the CLI at that service.

## Related Docs

- [`../README.md`](../README.md)
- [`WIKI_MODES.md`](WIKI_MODES.md)
- [`../examples/eval.toml`](../examples/eval.toml)
