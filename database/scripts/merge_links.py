#!/usr/bin/env python3
"""
Efficient version of merge_links.py using DuckDB.

Inputs:
  1. pages.txt.gz       → page_id, page_namespace, page_title
  2. linktarget.txt.gz  → lt_id,   lt_namespace,  lt_title
  3. links.txt.gz       → pl_from, pl_from_namespace, pl_target_id

Output:
  src_id<TAB>tgt_id
"""

import duckdb
import pandas as pd
import gzip
import sys
from pathlib import Path

def load_pages_to_duckdb(con, pages_path: Path):
    con.execute("CREATE TABLE pages (page_id TEXT, ns TEXT, title TEXT)")
    total_rows = 0
    with gzip.open(pages_path, "rt", encoding="utf-8") as f:
        reader = pd.read_csv(
            f, sep="\t",
            names=["page_id", "ns", "title"],
            usecols=[0, 1, 2],
            chunksize=100_000
        )
        for chunk in reader:
            con.append("pages", chunk)
            total_rows += len(chunk)
            if total_rows % 10_000_000 == 0:
                print(f"[INFO]   Loaded {total_rows:,} rows into 'pages'", file=sys.stderr)
    print(f"[INFO]   Finished loading 'pages' with {total_rows:,} rows", file=sys.stderr)
    con.execute("CREATE INDEX idx_pages_id ON pages(page_id)")
    con.execute("CREATE INDEX idx_pages_ns_title ON pages(ns, title)")
    print(f"[INFO]   Created indexes on 'pages'", file=sys.stderr)

def load_linktargets_to_duckdb(con, ltarget_path: Path):
    con.execute("CREATE TABLE linktargets (lt_id TEXT, ns TEXT, title TEXT)")
    total_rows = 0
    with gzip.open(ltarget_path, "rt", encoding="utf-8") as f:
        reader = pd.read_csv(
            f, sep="\t",
            names=["lt_id", "ns", "title"],
            usecols=[0, 1, 2],
            chunksize=100_000
        )
        for chunk in reader:
            con.append("linktargets", chunk)
            total_rows += len(chunk)
            if total_rows % 10_000_000 == 0:
                print(f"[INFO]   Loaded {total_rows:,} rows into 'linktargets'", file=sys.stderr)
    print(f"[INFO]   Finished loading 'linktargets' with {total_rows:,} rows", file=sys.stderr)
    con.execute("CREATE INDEX idx_linktargets_id ON linktargets(lt_id)")
    print(f"[INFO]   Created index on 'linktargets'", file=sys.stderr)

def stream_and_join_links(con, links_path: Path):
    with gzip.open(links_path, "rt", encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            parts = line.strip().split("\t")
            if len(parts) < 3:
                continue
            src_id, _, tgt_lt_id = parts

            try:
                # Check if src_id exists
                if not con.execute("SELECT 1 FROM pages WHERE page_id = ?", [src_id]).fetchone():
                    continue

                # Resolve linktarget → (ns, title)
                ns_title = con.execute(
                    "SELECT ns, title FROM linktargets WHERE lt_id = ?",
                    [tgt_lt_id]
                ).fetchone()
                if not ns_title:
                    continue

                # Resolve (ns, title) → tgt_id
                tgt_id = con.execute(
                    "SELECT page_id FROM pages WHERE ns = ? AND title = ?",
                    ns_title
                ).fetchone()
                if not tgt_id:
                    continue

                print(f"{src_id}\t{tgt_id[0]}")

                if i % 1_000_000 == 0:
                    print(f"[INFO] Processed {i:,} links", file=sys.stderr)
            except Exception:
                continue

def main():
    if len(sys.argv) != 4:
        sys.exit(f"Usage: {sys.argv[0]} pages.txt.gz linktarget.txt.gz links.txt.gz")

    pages_path = Path(sys.argv[1])
    linktarget_path = Path(sys.argv[2])
    links_path = Path(sys.argv[3])

    for f in (pages_path, linktarget_path, links_path):
        if not f.suffix == ".gz":
            sys.exit(f"[ERROR] Input file {f.name} must be .gz")

    print("[INFO] Connecting to DuckDB …", file=sys.stderr)
    con = duckdb.connect()

    print("[INFO] Loading pages …", file=sys.stderr)
    load_pages_to_duckdb(con, pages_path)

    print("[INFO] Loading linktargets …", file=sys.stderr)
    load_linktargets_to_duckdb(con, linktarget_path)

    print("[INFO] Streaming links and writing output …", file=sys.stderr)
    stream_and_join_links(con, links_path)

    print("[INFO] Done.", file=sys.stderr)

if __name__ == "__main__":
    main()