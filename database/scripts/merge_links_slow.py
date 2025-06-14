#!/usr/bin/env python
"""
Join links → linktarget → pages and emit src_id <TAB> tgt_id.

Input  (.gz, tab-separated, no header)
 1. pages.txt.gz       page_id, page_namespace, page_title, …
 2. linktarget.txt.gz  lt_id,   lt_namespace,  lt_title
 3. links.txt.gz       pl_from, pl_from_namespace, pl_target_id

Exact join logic
----------------
links.pl_from            = pages.page_id          (source exists)
links.pl_target_id       = linktarget.lt_id
linktarget.(ns,title)    = pages.(ns,title)       (target exists)

Output
------
src_id <TAB> tgt_id        (# rows identical to wide merge)
"""

import sys, gzip
from pathlib import Path
from typing import Dict, Tuple, Set


# ──────────────────────────────────────────────────────────
# Load helpers
# ──────────────────────────────────────────────────────────
def load_pages(path: Path) -> Tuple[Set[str], Dict[Tuple[str, str], str]]:
    """
    Returns
      • set(page_id)                       – for fast src lookup
      • dict[(namespace, title) → page_id] – for ns/title → id join
    """
    ids: Set[str] = set()
    nt_to_id: Dict[Tuple[str, str], str] = {}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for ln in fh:
            pid, ns, title, *_ = ln.rstrip("\n").split("\t")
            ids.add(pid)
            nt_to_id[(ns, title)] = pid
    return ids, nt_to_id


def load_linktargets(path: Path) -> Dict[str, Tuple[str, str]]:
    """lt_id → (namespace, title)"""
    m: Dict[str, Tuple[str, str]] = {}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for ln in fh:
            lt_id, ns, title, *_ = ln.rstrip("\n").split("\t")
            m[lt_id] = (ns, title)
    return m


# ──────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────
def main() -> None:
    if len(sys.argv) != 4:
        sys.exit(f"Usage: {sys.argv[0]} pages.txt.gz linktarget.txt.gz links.txt.gz")

    pages_gz, ltarget_gz, links_gz = map(Path, sys.argv[1:])
    for p in (pages_gz, ltarget_gz, links_gz):
        if p.suffix != ".gz":
            sys.exit("[ERROR] all inputs must be .gz files")

    # ── look-ups ─────────────────────────────────────────────
    print("[INFO] loading pages …", file=sys.stderr)
    page_ids, ns_title_to_pid = load_pages(pages_gz)
    print(f"[INFO]   {len(page_ids):,} page IDs", file=sys.stderr)

    print("[INFO] loading linktargets …", file=sys.stderr)
    lt_map = load_linktargets(ltarget_gz)
    print(f"[INFO]   {len(lt_map):,} linktargets", file=sys.stderr)

    # ── counters for skip reasons ───────────────────────────
    bad_line = 0
    missing_src = 0
    unknown_lt  = 0
    red_link    = 0

    processed = written = 0
    with gzip.open(links_gz, "rt", encoding="utf-8") as fh:
        for processed, ln in enumerate(fh, 1):
            parts = ln.rstrip("\n").split("\t")
            if len(parts) < 3:
                bad_line += 1
                continue

            src_id, _src_ns, tgt_lt_id = parts

            if src_id not in page_ids:
                missing_src += 1
                continue

            ns_title = lt_map.get(tgt_lt_id)
            if not ns_title:
                unknown_lt += 1
                continue

            tgt_id = ns_title_to_pid.get(ns_title)
            if not tgt_id:
                red_link += 1
                continue

            print(f"{src_id}\t{tgt_id}")
            written += 1

            if processed % 1_000_000 == 0:
                print(f"  processed {processed:,} — wrote {written:,}",
                      file=sys.stderr, end="\r")

    # ── final summary ───────────────────────────────────────
    print(f"\n[INFO] done: scanned {processed:,}; wrote {written:,} edges",
          file=sys.stderr)
    print(f"[STATS] skipped lines:",
          f"\n         malformed          : {bad_line:,}",
          f"\n         source page missing: {missing_src:,}",
          f"\n         unknown lt_id      : {unknown_lt:,}",
          f"\n         red / deleted link : {red_link:,}",
          sep="", file=sys.stderr)


if __name__ == "__main__":
    main()