# WikiArena

WikiArena is an open evaluation framework for testing language models on Wikipedia navigation tasks.

Each run asks a model to move from a start page to a target page using only the links visible on the current page. The project is designed for reproducible research runs, comparable benchmark artifacts, and offline evaluation from a local Wikipedia graph snapshot.

## Why WikiArena

- realistic navigation tasks instead of toy search problems
- protocol-native run artifacts for analysis, replay, and benchmarking
- reproducible benchmark workflows built around configs, tasksets, and stable hashes
- support for both live Wikipedia and offline graph-backed runs

## Current Status

- the primary supported workflow is the CLI in `src/wikiarena`
- live runs are supported through the Wikipedia API
- offline runs are supported through a local dated graph snapshot such as `wikiarena_graph_enwiki_20260301.bin`
- a first-time `wikiarena graph install` flow is planned, but not implemented yet

## Installation

WikiArena uses `uv` for local development and CLI usage.

Prerequisites:

- Python 3.11+
- `uv`

```bash
git clone https://github.com/wikiarena/wikiarena.git
cd wikiarena
uv sync --dev
uv run wikiarena --help
```

## Provider Credentials

Set the provider credential your chosen model requires before running the CLI.

Examples:

```bash
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
```

## Quickstart

### Run a single live task

```bash
uv run wikiarena run \
  --model gpt-4.1-nano-2025-04-14 \
  --provider openai \
  --start Apple \
  --target Banana
```

### Run a single offline task

Graph mode requires a local dated graph file such as `wikiarena_graph_enwiki_20260301.bin`. Until `wikiarena graph install` exists, point WikiArena at the file directly or via `WIKIARENA_GRAPH_PATH`.

If no explicit graph path is provided, WikiArena uses the newest dated graph file installed in `~/.wikiarena/`.

If no explicit snapshot id is provided, WikiArena infers it from the selected graph filename.

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
  --graph-path ~/.wikiarena/wikiarena_graph_enwiki_20260301.bin
```

### Run a benchmark from config

```bash
uv run wikiarena eval run \
  --config examples/eval.toml \
  --output results.jsonl
```

### Summarize benchmark results

```bash
uv run wikiarena eval summarize --input results.jsonl
uv run wikiarena eval summarize --input results.jsonl --format json
```

## Live vs Graph Wiki Modes

WikiArena supports two intentionally different wiki backends:

- `live`: fetches current page state from the live Wikipedia API
- `graph`: reads from a local dated graph snapshot for deterministic offline evaluation

Graph mode is not a byte-for-byte reproduction of live Wikipedia. Today it differs in a few important ways:

- redirects are resolved during graph construction
- visible titles are canonical graph titles, not redirect or alias link text
- links are deterministic and sorted from the graph snapshot
- duplicate links are removed during graph construction
- results are fixed to the installed snapshot instead of current live Wikipedia state

See [`docs/WIKI_MODES.md`](docs/WIKI_MODES.md) for the detailed behavior differences and configuration shape.

## CLI Overview

Main commands:

- `wikiarena run` for one model on one task
- `wikiarena eval run` for benchmark configs and tasksets
- `wikiarena eval summarize` for JSONL result summaries

For a practical command guide with examples and option explanations, see [`docs/CLI.md`](docs/CLI.md).

## Output Artifacts

WikiArena writes run results as JSONL artifacts so runs can be inspected, appended, summarized, and replayed later.

- `wikiarena run --output ...` writes a run artifact
- `wikiarena eval run --output ...` writes one JSONL line per run
- `--append` and `--overwrite` control how existing files are handled
- append safety checks prevent mixing incompatible rulesets, and also prevent mixing wiki backends or snapshot ids when those are pinned

## Example Files

- benchmark config: [`examples/eval.toml`](examples/eval.toml)
- taskset: [`examples/taskset.jsonl`](examples/taskset.jsonl)

## Documentation

User-facing docs:

- [`docs/CLI.md`](docs/CLI.md)
- [`docs/SOLVER_API.md`](docs/SOLVER_API.md)
- [`docs/WIKI_MODES.md`](docs/WIKI_MODES.md)

Project and implementation docs:

- [`docs/PROJECT_GOALS.md`](docs/PROJECT_GOALS.md)
- [`docs/DECISIONS.md`](docs/DECISIONS.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/PROTOCOL_V1_DRAFT.md`](docs/PROTOCOL_V1_DRAFT.md)
- [`docs/SOLVER_BACKENDS.md`](docs/SOLVER_BACKENDS.md)
- [`docs/GRAPH_PIPELINE_V1.md`](docs/GRAPH_PIPELINE_V1.md)

## Development

Run the test suite:

```bash
uv run pytest
```

Run the solver API locally:

```bash
WIKIARENA_GRAPH_PATH=/path/to/wikiarena_graph.bin \
WIKIARENA_GRAPH_METADATA_PATH=/path/to/wikiarena_graph.metadata.json \
uv run uvicorn wikiarena.server.app:app --reload
```

Package the production API bundle locally:

```bash
bash scripts/package_api_bundle.sh dist local-dev
```

Production infrastructure and deploy auth are documented in the sibling infra repo at `/Users/hupaulson/projects/wikiarena/infra/README.md`.

The active implementation lives under `src/wikiarena`. Older namespaces such as `src/wiki_arena` remain in the repository as legacy/reference code and are not the place for new work.

## Inspiration

WikiArena is inspired by the Wikipedia racing game: start on one article, reach another article, and do it in as few moves as possible.
