# WikiArena CLI Design v1

Last updated: 2026-03-22

This doc tracks the current CLI shape and a small amount of near-term planned UX.

## Design Philosophy

- Default to a task-oriented interface for humans.
- Keep the CLI centered on reproducible offline evaluation.
- Expose the important benchmark knobs, not the internal planner mechanics.
- Add new command groups only when they remove real setup friction.

## Current UX Model

Two layers still make sense:

1. Porcelain (human-friendly)
   - short commands
   - sensible defaults
   - readable summaries

2. Plumbing (protocol/research-friendly)
   - config files
   - JSON/JSONL artifacts
   - stable hashes for comparability

In practice, the current CLI mostly lives in the overlap: human-usable commands that still emit protocol-aligned artifacts.

## Implemented Command Tree

Current commands in `src/wikiarena/cli.py`:

- `wikiarena run`
  - run one participant on one task
- `wikiarena eval run`
  - run a benchmark from config + taskset
- `wikiarena eval summarize`
  - summarize JSONL run artifacts into table/json/markdown output

The graph command group now exists.

## Near-Term Command Tree

The first graph setup path is now implemented so users do not have to manually download and unpack solver artifacts.

Implemented first command:

- `wikiarena graph install`
  - download the official graph release
  - decompress it locally if needed
  - verify the artifact and metadata/checksum
  - install a dated graph binary like `wikiarena_graph_enwiki_20260301.bin` into a standard local location for WikiArena to use

Current behavior:

- downloads the latest published graph release by default
- optionally installs a specific published release tag via `--tag`
- verifies metadata and checksums before installing
- installs the dated binary into the per-user application data graph directory unless `--install-dir` is provided

## Current Command Behavior

### `wikiarena run`

Current exposed controls:

- `--model`
- `--start`
- `--target`
- `--provider`
- `--language`
- `--navigation-backend` / `--offline`
- `--navigation-graph-path`
- `--navigation-snapshot-id`
- `--solver-backend`
- `--solver-graph-path`
- `--solver-snapshot-id`
- `--response-contract`
- `--tool-name`
- generation settings such as `--temperature`, `--max-tokens`, `--reasoning-effort`
- Anthropic thinking controls
- `--base-url`
- `--output`, `--append`, `--overwrite`
- `--json`

Important current nuance:

- `--navigation-backend` controls whether navigation uses live Wikipedia or the local graph snapshot
- `--offline` is the human-friendly alias for `--navigation-backend graph`
- `--solver-backend` controls solver/reference-path provenance independently of navigation
- local graph navigation is intentionally different from live mode because it resolves redirects, canonicalizes titles, removes duplicate links, and uses deterministic graph ordering

### `wikiarena eval run`

Current inputs:

- `--config`
- `--output`
- `--append`
- `--overwrite`
- `--json`
- `--print-hashes`
- optional runtime overrides: navigation via `--navigation-backend`, `--offline`, `--navigation-graph-path`, `--navigation-snapshot-id`; solver via `--solver-backend`, `--solver-graph-path`, `--solver-snapshot-id`

Current behavior:

- loads benchmark config and taskset
- plans benchmark identity hashes
- runs all races/runs through `BenchmarkRunner`
- appends JSONL run artifacts
- refuses append when `ruleset_hash` does not match the existing file

### `wikiarena eval summarize`

Current inputs:

- `--input`
- `--format` (`table`, `json`, `markdown`)
- `--tie-breaker`

Current behavior:

- loads JSONL `RunResult` artifacts
- groups runs by race and participant
- computes pairwise outcomes and Elo-style ratings

## Official vs Extended Runs

Official comparability should lock:

- protocol version
- navigation rules
- harness config
- scoring rules

That combination maps to one `ruleset_hash`.

Different task packs are allowed, but they should produce different `taskset_hash` values.

## What The CLI Should Expose

Expose:

- provider/model selection
- generation behavior settings
- benchmark config and taskset paths
- output path handling
- summary format options
- graph installation/setup commands

Hide by default:

- raw id construction details
- raw hash construction internals
- lower-level planner mechanics

## Debug And Machine-Readable Output

Currently supported debug or machine-readable flags:

- `--json`
- `--print-hashes`

Older ideas like `--print-plan` are not implemented today and should not be documented as if they exist.

## Output Contract

`wikiarena run` and `wikiarena eval run` should produce artifacts aligned with the protocol models.

In practice, benchmark artifacts should carry at least:

- `ruleset_hash`
- `taskset_hash`
- `participant_hash`
- `protocol_version`
- `solver_backend`
- `navigation_snapshot_id` when known
- `solver_snapshot_id` when known

## Graph Command Design Notes

`wikiarena graph install` should optimize for:

- one obvious command for first-time setup
- no manual dump handling for normal users
- explicit verification of the installed artifact
- clear reporting of where the graph was installed
- compatibility with future local binary-solver wiring in the main eval flow
