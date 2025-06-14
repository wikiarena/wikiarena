#!/usr/bin/env python3
"""
merge_links.py
==============

Usage (exactly the same bash line you already have):
  python merge_links.py pages.txt.gz linktarget.txt.gz links.txt.gz | pigz --fast > …

Outputs to *stdout*:
  src_id<TAB>tgt_id   (no header, uncompressed – the shell pipe compresses it)

DuckDB creates/uses an on-disk file `wiki.duckdb` the first time it runs so the
65-million-row `pages` table is only materialised once.
"""
from __future__ import annotations
import duckdb
import sys
import textwrap
import logging
import gzip

BUF = 4 * 1024 * 1024  # 4 MB CSV buffer
con = None             # Global connection for interrupt handling

# ───────────── Logging Setup ─────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def table_exists(con, name):
    return con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = ?",
        [name]
    ).fetchone() is not None

def count_lines_gz(path: str) -> int:
    """Efficiently count number of lines in a .gz file."""
    logging.info("Counting lines in %s …", path)
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        return sum(1 for _ in f)

def main() -> None:
    global con

    if len(sys.argv) != 4:
        sys.exit("Usage: merge_links.py pages.txt.gz linktarget.txt.gz links.txt.gz")

    pages_gz, linktarget_gz, links_gz = sys.argv[1:]
    logging.info("Opening DuckDB database…")
    con = duckdb.connect("wiki.duckdb")

    rebuild_pages = True

    # ───────────── Check if pages table matches file row count ─────────────
    if table_exists(con, "pages"):
        logging.info("`pages` table exists. Verifying row count…")
        db_count = con.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        file_count = count_lines_gz(pages_gz)

        logging.info("DB rows: %d, File rows: %d", db_count, file_count)

        if db_count == file_count:
            logging.info("Row count matches. Keeping existing `pages` table.")
            rebuild_pages = False
        else:
            logging.info("Mismatch detected. Rebuilding `pages` table.")
            con.execute("DROP TABLE pages")

    # ───────────── Create Pages Table ─────────────
    if rebuild_pages:
        logging.info("Creating `pages` table from %s …", pages_gz)
        con.execute(textwrap.dedent(f"""
            CREATE TABLE pages AS
            SELECT
                column0::UBIGINT  AS page_id,
                column1::INTEGER  AS ns,
                column2           AS title
            FROM read_csv_auto('{pages_gz}',
                               compression='gzip',
                               header=false,
                               delim='\\t',
                               buffer_size={BUF},
                               sample_size=-1);
            CREATE UNIQUE INDEX pages_pk        ON pages(page_id);
            CREATE         INDEX pages_ns_title ON pages(ns, title);
        """))
        logging.info("`pages` table created and indexed.")

    # ───────────── Perform Join and Stream Output ─────────────
        logging.info("Performing join to generate edge list…")
    con.execute(textwrap.dedent(f"""
        COPY (
            SELECT
                l.column0       AS src_id,     -- pl_from
                tgt.page_id     AS tgt_id      -- resolved target page_id
            FROM read_csv_auto('{links_gz}', compression='gzip', header=false,
                               delim='\\t', buffer_size={BUF}, sample_size=-1) AS l
            JOIN read_csv_auto('{linktarget_gz}', compression='gzip', header=false,
                               delim='\\t', buffer_size={BUF}, sample_size=-1) AS lt
              ON lt.column0 = l.column2        -- lt_id = pl_target_id
            JOIN pages AS tgt
              ON (tgt.ns, tgt.title) = (lt.column1, lt.column2)
        )
        TO '/dev/stdout'
        (DELIMITER '\t', HEADER false, COMPRESSION 'uncompressed');
    """))
    logging.info("Join complete. Output written to stdout.")
    
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.warning("Interrupted by user (CTRL+C). Exiting…")
        if con is not None:
            try:
                con.interrupt()
            except Exception:
                pass
        sys.exit(130)