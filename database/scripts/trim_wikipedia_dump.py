#!/usr/bin/env python
"""
Memory-efficient trimming of Wikipedia SQL dumps

Tables supported
----------------
pages      → page_id, page_namespace, page_title, page_is_redirect
links      → pl_from,  pl_from_namespace, pl_target_id
redirects  → rd_from,  rd_namespace,      rd_title
targets    → lt_id,    lt_namespace,      lt_title     (linktarget table)
"""
import gzip
import os
import re
import sys


PATTERNS = {
    "pages": {
        "insert": re.compile(r"^INSERT INTO `page` VALUES (.+);$"),
        # page_id , page_namespace , 'title' , page_is_redirect
        "record": re.compile(r"(\d+),(\d+),'((?:[^'\\]|\\.)*)',([01]),")
    },
    "links": {
        "insert": re.compile(r"^INSERT INTO `pagelinks` VALUES (.+);$"),
        # pl_from , pl_from_namespace , pl_target_id
        "record": re.compile(r"(\d+),(\d+),(\d+)\)?$")
    },
    "redirects": {
        "insert": re.compile(r"^INSERT INTO `redirect` VALUES (.+);$"),
        # rd_from , rd_namespace , 'title'
        "record": re.compile(r"(\d+),(\d+),'((?:[^'\\]|\\.)*)',")
    },
    "targets": {
        "insert": re.compile(r"^INSERT INTO `linktarget` VALUES (.+);$"),
        # lt_id , lt_namespace , 'title'
        "record": re.compile(r"(\d+),(\d+),'((?:[^'\\]|\\.)*)'")
    },
}


def trim_file(input_file: str, output_file: str, kind: str) -> None:
    insert_re = PATTERNS[kind]["insert"]
    record_re = PATTERNS[kind]["record"]

    processed = written = 0
    with gzip.open(input_file, "rt", encoding="utf-8", errors="replace") as fin, \
         gzip.open(output_file, "wt", encoding="utf-8") as fout:

        for line in fin:
            processed += 1
            if processed % 1000 == 0:
                print(f"  Processed {processed:,} | Written {written:,}", file=sys.stderr, end="\r")

            m = insert_re.match(line.strip())
            if not m:
                continue

            # split the big INSERT payload into individual tuples
            tuples = re.split(r"\),\(", m.group(1))

            for tup in tuples:
                m2 = record_re.search(tup)
                if not m2:
                    continue

                if kind == "pages":
                    page_id, ns, title, is_redirect = m2.groups()
                    fout.write(f"{page_id}\t{ns}\t{title}\t{is_redirect}\n")

                elif kind == "links":
                    pl_from, pl_ns, pl_target_id = m2.groups()
                    fout.write(f"{pl_from}\t{pl_ns}\t{pl_target_id}\n")

                elif kind == "redirects":
                    rd_from, rd_ns, rd_title = m2.groups()
                    fout.write(f"{rd_from}\t{rd_ns}\t{rd_title}\n")

                elif kind == "targets":
                    lt_id, lt_ns, lt_title = m2.groups()
                    fout.write(f"{lt_id}\t{lt_ns}\t{lt_title}\n")

                written += 1

    print(f"\n  Finished: {processed:,} lines → {written:,} rows.")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: trim_wikipedia_dump.py <pages|links|redirects|targets> <input.gz> <output.gz>")
        sys.exit(1)

    kind, inp, outp = sys.argv[1:]
    if kind not in PATTERNS:
        sys.exit("Error: file_type must be pages, links, redirects, or targets")
    if not os.path.exists(inp):
        sys.exit("Error: input file not found")

    print(f"Trimming {kind}: {inp} → {outp}")
    trim_file(inp, outp, kind)