# WikiArena SQL Trimmer

This crate accelerates only the raw SQL trim stage of the graph build.

Design goals:

- keep the existing staged pipeline and intermediate file contracts
- replace the slow Python SQL parsing hot path with a specialized native parser
- keep the interface stream-oriented so the pipeline can continue to use gzip or pigz around the parser

Interface:

- input: SQL dump bytes on stdin
- output: trimmed tab-separated rows on stdout
- args:
  - `--kind <pages|links|redirects|targets>`
  - `--stats-path <path>`

The Python pipeline is responsible for:

- discovering the binary path
- handling gzip or pigz decompression and recompression
- logging stage progress and integrating the output into downstream stages

The Rust trimmer is responsible only for:

- parsing `INSERT INTO ... VALUES (...)` rows correctly
- unescaping quoted SQL title fields
- emitting the exact trimmed row shape expected by the rest of the pipeline
- reporting `processed_lines` and `written_rows`
