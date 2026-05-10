# WikiArena

<p align="center">
  <img src="docs/assets/wikiarena-home-preview.gif" alt="Two model runners racing through Wikipedia links toward a target page" width="720">
</p>

WikiArena is an open benchmark for testing how well language models can navigate Wikipedia.

Each task starts on one article and asks a model to reach a target article using only links visible on the current page. That simple game produces a surprisingly rich eval: long-horizon planning, tool use, context management, recovery from bad moves, and strategy under a clean success condition.

The core benchmark runs locally from the CLI. Install an official Wikipedia graph snapshot once, run models against deterministic offline tasks, and keep JSONL artifacts that can be summarized, audited, and replayed later.

## Why It Matters

Wikipedia racing is easy to understand, but hard to fake. A model has to choose a path through a real, messy information graph, not just answer a question from memory.

WikiArena is built around:

- **Reproducible worlds:** official dated graph snapshots make offline runs deterministic.
- **Exact shortest paths:** the local solver can label task difficulty and measure regret against optimal play.
- **Inspectable artifacts:** every run is emitted as JSONL with rules, task, backend, provider, and snapshot metadata.
- **Live and offline modes:** use live Wikipedia when you want current page behavior, or graph mode when you want repeatable benchmark runs.
- **One protocol:** CLI runs, solver APIs, benchmark summaries, and replay UI all consume the same core result shape.

## Quickstart

Prerequisites:

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/)
- A model provider credential, such as `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`

```bash
git clone https://github.com/wikiarena/wikiarena.git
cd wikiarena
uv sync --dev
```

Set the provider credential for the model you want to run:

```bash
export OPENAI_API_KEY=...
# or
export ANTHROPIC_API_KEY=...
```

Install the latest official graph release:

```bash
uv run wikiarena graph install
```

On macOS, the graph is installed under:

```text
~/Library/Application Support/wikiarena/graphs/
```

Check what WikiArena will use:

```bash
uv run wikiarena graph info
```

Run a model on a random offline task:

```bash
uv run wikiarena run \
  --model gpt-5.2 \
  --provider openai \
  --trace
```

With an installed graph, `wikiarena run` defaults to graph navigation plus the local shortest-path solver. If you omit `--start` and `--target`, WikiArena samples a random task from the selected graph and prints the chosen pair before the run starts.

## What You Get

A traced run shows the model's page, target, visible links, tool calls, invalid attempts, and final result. If a local graph solver is enabled, artifacts also record shortest-path facts that are not shown to the participant.

```text
model chooses a link
        |
        v
WikiArena validates that link on the current page
        |
        v
the run records a step event, move count, timing, and solver facts
        |
        v
results can be summarized, audited, or replayed
```

## Common Workflows

### Run A Specific Task

```bash
uv run wikiarena run \
  --model claude-sonnet-4-6 \
  --provider anthropic \
  --start Apple \
  --target Banana \
  --trace
```

For OpenAI-compatible providers, `wikiarena run` defaults reasoning effort to `high` unless you pass `--reasoning-effort`.

For `--provider openai`, WikiArena uses the OpenAI Responses API by default. Reasoning summaries are opt-in with `--openai-reasoning-summary`.

For `--provider anthropic`, thinking is opt-in with `--thinking-effort` or `--thinking-budget-tokens`.

### Force Live Wikipedia

```bash
uv run wikiarena run \
  --model gpt-5.2 \
  --provider openai \
  --start Apple \
  --target Banana \
  --navigation-backend live
```

Live mode fetches current page state from Wikipedia. It is useful for smoke tests and live-behavior checks, but it is not as reproducible as graph mode.

### Pin A Graph Explicitly

```bash
uv run wikiarena run \
  --model claude-sonnet-4-6 \
  --provider anthropic \
  --start Apple \
  --target Banana \
  --navigation-graph-path /path/to/wikiarena_graph_enwiki_20260401.bin
```

Passing `--navigation-graph-path` selects graph navigation automatically unless you explicitly ask for live navigation. If no snapshot id is provided, WikiArena infers one from a dated graph filename such as `wikiarena_graph_enwiki_20260401.bin`.

### Use Live Navigation With A Local Solver

```bash
uv run wikiarena run \
  --model claude-sonnet-4-6 \
  --provider anthropic \
  --start Apple \
  --target Banana \
  --navigation-backend live \
  --solver-backend local
```

Navigation and solver configuration are intentionally separate. Navigation controls the world the model plays in. Solver facts are benchmark annotations for analysis.

### Run A Benchmark Config

```bash
uv run wikiarena eval run \
  --config examples/eval.toml \
  --output results.jsonl
```

Summarize the output:

```bash
uv run wikiarena eval summarize --input results.jsonl
uv run wikiarena eval summarize --input results.jsonl --format markdown
uv run wikiarena eval summarize --input results.jsonl --format json
```

## CLI Map

| Command | Purpose |
| --- | --- |
| `wikiarena graph install` | Download, verify, decompress, and install an official graph release. |
| `wikiarena graph info` | Inspect the active graph selection, snapshot id, metadata, and checksums. |
| `wikiarena run` | Run one participant on one task. |
| `wikiarena eval run` | Run one or more participants against a taskset from config. |
| `wikiarena eval summarize` | Summarize JSONL run artifacts as a table, Markdown, or JSON. |

Use `uv run wikiarena --help` or `uv run wikiarena <command> --help` for the full option list. The practical command guide lives in [`docs/CLI.md`](docs/CLI.md).

## Live vs Graph Mode

WikiArena supports two wiki backends:

- `live`: fetch current page state from the live Wikipedia API
- `graph`: read page links from a local dated graph snapshot

Graph mode is intentionally not a byte-for-byte copy of live Wikipedia. Redirects are resolved during graph construction, visible titles are canonical graph titles, duplicate links are removed, links are sorted deterministically, and results are fixed to the installed snapshot.

That makes graph mode the right default for reproducible evaluation. See [`docs/WIKI_MODES.md`](docs/WIKI_MODES.md) for the exact behavior differences.

## Output Artifacts

WikiArena writes JSONL so runs can be appended, inspected, summarized, and replayed.

- `wikiarena run --output results.jsonl` writes one run result
- `wikiarena eval run --output results.jsonl` writes one line per participant/task run
- `--append` and `--overwrite` control how existing files are handled
- append safety checks prevent mixing incompatible rulesets, navigation backends, solver backends, or pinned snapshot ids

Every result is designed to carry enough context to support later analysis: task metadata, ruleset hash, participant/provider settings, navigation backend, solver backend, snapshot ids, moves, attempts, timing, and outcome.

## Repository Guide

The active implementation lives under [`src/wikiarena`](src/wikiarena).

Important entry points:

- [`src/wikiarena/cli.py`](src/wikiarena/cli.py): user-facing CLI
- [`src/wikiarena/graph/`](src/wikiarena/graph): graph install, metadata, naming, and release helpers
- [`src/wikiarena/solver/`](src/wikiarena/solver): binary graph solver
- [`src/wikiarena/eval/`](src/wikiarena/eval): benchmark run service
- [`src/wikiarena/protocol/`](src/wikiarena/protocol): shared result and event models
- [`frontend/`](frontend): public static solver/replay-facing site work

## Examples And Docs

Start with:

- [`examples/eval.toml`](examples/eval.toml): benchmark config
- [`examples/taskset.jsonl`](examples/taskset.jsonl): the default example taskset, using the same tasks shown in the homepage animation
- [`docs/CLI.md`](docs/CLI.md): command guide
- [`docs/WIKI_MODES.md`](docs/WIKI_MODES.md): live vs graph behavior
- [`docs/SOLVER_API.md`](docs/SOLVER_API.md): solver service API
- [`docs/SOLVER_BACKENDS.md`](docs/SOLVER_BACKENDS.md): solver backend notes
- [`docs/GRAPH_PIPELINE_V1.md`](docs/GRAPH_PIPELINE_V1.md): graph build pipeline
- [`docs/PROTOCOL_V0.md`](docs/PROTOCOL_V0.md): artifact protocol
- [`docs/PROJECT_GOALS.md`](docs/PROJECT_GOALS.md): project direction

## Development

Run tests:

```bash
uv run pytest
```

Run targeted CLI and graph tests while changing onboarding paths:

```bash
uv run pytest \
  tests/wikiarena/test_cli.py \
  tests/wikiarena/graph/test_install.py \
  tests/wikiarena/graph/test_info.py \
  tests/wikiarena/test_wiki_runtime.py
```

Run the solver API locally:

```bash
uv run uvicorn wikiarena.server.app:app --reload
```

If you have already run `uv run wikiarena graph install`, the server uses the installed default graph automatically. Set `WIKIARENA_GRAPH_PATH` and `WIKIARENA_GRAPH_METADATA_PATH` only when you want to pin a specific graph artifact.

Run the frontend:

```bash
cd frontend
bun run dev
```

Build the frontend:

```bash
cd frontend
bun run type-check
bun run build
```

Package the production API bundle locally:

```bash
bash scripts/package_api_bundle.sh dist local-dev
```

## Inspiration

WikiArena is inspired by the Wikipedia racing game: start on one article, reach another article, and do it in as few moves as possible. The benchmark version keeps that intuitive game loop, then adds the reproducibility and instrumentation needed to compare frontier models.
