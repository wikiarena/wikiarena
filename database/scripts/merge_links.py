#!/usr/bin/env python3
"""
merge_links.py
==============

Usage:
  python merge_links.py pages.txt.gz linktarget.txt.gz links.txt.gz | pigz --fast > edges.tsv.gz

Output:
  TSV to stdout: src_id<TAB>tgt_id (no header, uncompressed – pipe to pigz for compression)

Creates and uses DuckDB on-disk cache `wiki.duckdb`.
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

def table_exists(con, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = ?",
        [name]
    ).fetchone() is not None

def count_lines_gz(path: str) -> int:
    """Efficiently count number of lines in a .gz file."""
    logging.info("Counting lines in %s …", path)
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        return sum(1 for _ in f)

def ensure_table_from_file(con, name: str, path: str, columns: str, indexes: list[str]):
    """Ensure a DuckDB table exists and matches the .gz line count. Recreate if needed."""
    recreate = True
    if table_exists(con, name):
        logging.info("`%s` table exists. Verifying row count…", name)
        db_count = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        file_count = count_lines_gz(path)
        logging.info("DB rows: %d, File rows: %d", db_count, file_count)
        if db_count == file_count:
            logging.info("Row count matches. Keeping existing `%s` table.", name)
            recreate = False
        else:
            logging.info("Mismatch detected. Rebuilding `%s` table.", name)
            con.execute(f"DROP TABLE {name}")

    if recreate:
        logging.info("Creating `%s` table from %s …", name, path)
        con.execute(textwrap.dedent(f"""
            CREATE TABLE {name} AS
            SELECT {columns}
            FROM read_csv_auto('{path}',
                               compression='gzip',
                               header=false,
                               delim='\\t',
                               buffer_size={BUF},
                               sample_size=-1);
        """))
        for index in indexes:
            # Clean up for valid index name
            index_cols = index.replace("(", "").replace(")", "")
            index_name = f"{name}_{'_'.join(index_cols.split(', '))}"
            con.execute(f"CREATE INDEX {index_name} ON {name} ({index_cols})")
        logging.info("`%s` table created and indexed.", name)

def main() -> None:
    global con

    if len(sys.argv) != 4:
        sys.exit("Usage: merge_links.py pages.txt.gz linktarget.txt.gz links.txt.gz")

    pages_gz, linktarget_gz, links_gz = sys.argv[1:]

    logging.info("Opening DuckDB database…")
    con = duckdb.connect("wiki.duckdb")

    # ───────────── Ensure `pages` and `linktargets` are loaded and indexed ─────────────
    ensure_table_from_file(
        con,
        name="pages",
        path=pages_gz,
        columns="column0::UBIGINT AS page_id, column1::INTEGER AS ns, column2 AS title",
        indexes=["page_id", "(ns, title)"]
    )

    ensure_table_from_file(
        con,
        name="linktargets",
        path=linktarget_gz,
        columns="column0::UBIGINT AS lt_id, column1::INTEGER AS ns, column2 AS title",
        indexes=["lt_id", "(ns, title)"]
    )

    # ───────────── Perform Streaming Join ─────────────
    logging.info("Performing join to generate edge list…")
    con.execute(textwrap.dedent(f"""
        COPY (
            SELECT
                l.column0       AS src_id,     -- pl_from
                tgt.page_id     AS tgt_id      -- resolved target page_id
            FROM read_csv_auto('{links_gz}', compression='gzip', header=false,
                               delim='\\t', buffer_size={BUF}, sample_size=-1) AS l
            JOIN linktargets AS lt ON lt.lt_id = l.column2
            JOIN pages AS tgt ON (tgt.ns, tgt.title) = (lt.ns, lt.title)
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