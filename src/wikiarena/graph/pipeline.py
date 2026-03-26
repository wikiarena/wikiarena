from __future__ import annotations

import gzip
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tempfile
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen

from wikiarena.graph.build import build_graph_binary
from wikiarena.graph.dump_processing import (
    DumpTrimKind,
    iter_normalized_link_rows,
    iter_pruned_page_rows,
    iter_resolved_redirect_rows,
    write_trimmed_dump,
)
from wikiarena.graph.progress import ProgressReporter


@dataclass(frozen=True)
class GraphBuildPaths:
    pages_file_path: Path
    grouped_links_by_source_file_path: Path
    grouped_links_by_target_file_path: Path
    output_file_path: Path
    node_count: int
    edge_count: int


@dataclass(frozen=True)
class GraphPreparationArtifacts:
    output_dir: Path
    dump_date: str
    pages_file_path: Path
    grouped_links_by_source_file_path: Path
    grouped_links_by_target_file_path: Path


def resolve_dump_date(
    *,
    wiki: str,
    requested_dump_date: str | None,
) -> str:
    if requested_dump_date is not None:
        _validate_dump_date(
            requested_dump_date,
        )
        return requested_dump_date

    with urlopen(
        "https://dumps.wikimedia.org/index.json",
    ) as response:
        dump_index = json.load(
            response,
        )
    dump_date = dump_index["wikis"][wiki]["jobs"]["pagelinkstable"]["updated"].split()[
        0
    ]
    _validate_dump_date(
        dump_date,
    )
    return dump_date


def prepare_graph_inputs(
    *,
    wiki: str,
    dump_date: str,
    output_dir: Path,
    merge_engine: str = "sortjoin",
    progress_reporter: ProgressReporter | None = None,
) -> GraphPreparationArtifacts:
    _validate_dump_date(
        dump_date,
    )
    output_dir_path = output_dir
    output_dir_path.mkdir(
        parents=True,
        exist_ok=True,
    )
    _log_progress(
        progress_reporter,
        f"prepare graph inputs in {output_dir_path}",
    )

    raw_files = _download_raw_dump_files(
        wiki=wiki,
        dump_date=dump_date,
        output_dir=output_dir_path,
        progress_reporter=progress_reporter,
    )

    redirects_trimmed_path = output_dir_path / "redirects.txt.gz"
    pages_trimmed_path = output_dir_path / "pages.txt.gz"
    links_trimmed_path = output_dir_path / "links.txt.gz"
    targets_trimmed_path = output_dir_path / "linktarget.txt.gz"
    _trim_dump_if_missing(
        kind=DumpTrimKind.REDIRECTS,
        input_file_path=raw_files["redirects"],
        output_file_path=redirects_trimmed_path,
        progress_reporter=progress_reporter,
    )
    _trim_dump_if_missing(
        kind=DumpTrimKind.PAGES,
        input_file_path=raw_files["pages"],
        output_file_path=pages_trimmed_path,
        progress_reporter=progress_reporter,
    )
    _trim_dump_if_missing(
        kind=DumpTrimKind.LINKS,
        input_file_path=raw_files["links"],
        output_file_path=links_trimmed_path,
        progress_reporter=progress_reporter,
    )
    _trim_dump_if_missing(
        kind=DumpTrimKind.TARGETS,
        input_file_path=raw_files["targets"],
        output_file_path=targets_trimmed_path,
        progress_reporter=progress_reporter,
    )

    resolved_redirects_path = output_dir_path / "redirects.resolved_ids.txt.gz"
    _write_gzip_rows_if_missing(
        output_file_path=resolved_redirects_path,
        rows=iter_resolved_redirect_rows(
            pages_file_path=pages_trimmed_path,
            redirects_file_path=redirects_trimmed_path,
        ),
        sort_numeric_by_first_column=True,
        progress_reporter=progress_reporter,
        progress_label="resolve redirects to canonical ids",
    )

    pruned_pages_path = output_dir_path / "pages.pruned.txt.gz"
    _write_gzip_rows_if_missing(
        output_file_path=pruned_pages_path,
        rows=iter_pruned_page_rows(
            pages_file_path=pages_trimmed_path,
            resolved_redirects_file_path=resolved_redirects_path,
        ),
        progress_reporter=progress_reporter,
        progress_label="prune article pages",
    )

    raw_edges_path = output_dir_path / "links.raw_ids.txt.gz"
    if not raw_edges_path.exists():
        if merge_engine == "duckdb":
            _merge_links_with_duckdb(
                pages_trimmed_path=pages_trimmed_path,
                linktarget_trimmed_path=targets_trimmed_path,
                links_trimmed_path=links_trimmed_path,
                output_file_path=raw_edges_path,
                temp_db_path=output_dir_path / "wikiarena_graph_build.duckdb",
                progress_reporter=progress_reporter,
            )
        elif merge_engine == "sortjoin":
            _merge_links_with_sort_join(
                pages_trimmed_path=pages_trimmed_path,
                linktarget_trimmed_path=targets_trimmed_path,
                links_trimmed_path=links_trimmed_path,
                output_file_path=raw_edges_path,
                progress_reporter=progress_reporter,
            )
        else:
            raise ValueError(
                f"unsupported merge engine: {merge_engine}",
            )
    else:
        _log_progress(
            progress_reporter,
            f"skip merge raw article edge ids (already exists: {raw_edges_path.name})",
        )

    normalized_links_path = output_dir_path / "links.normalized_ids.txt.gz"
    _write_gzip_rows_if_missing(
        output_file_path=normalized_links_path,
        rows=iter_normalized_link_rows(
            pages_file_path=pruned_pages_path,
            redirects_file_path=resolved_redirects_path,
            links_file_path=raw_edges_path,
        ),
        progress_reporter=progress_reporter,
        progress_label="normalize article links",
    )

    sorted_by_source_path = output_dir_path / "links.sorted_by_source_id.txt.gz"
    _sort_and_dedupe_links_if_missing(
        input_file_path=normalized_links_path,
        output_file_path=sorted_by_source_path,
        sort_column=1,
        progress_reporter=progress_reporter,
        progress_label="sort links by source id",
    )
    sorted_by_target_path = output_dir_path / "links.sorted_by_target_id.txt.gz"
    _sort_and_dedupe_links_if_missing(
        input_file_path=normalized_links_path,
        output_file_path=sorted_by_target_path,
        sort_column=2,
        progress_reporter=progress_reporter,
        progress_label="sort links by target id",
    )

    grouped_by_source_path = output_dir_path / "links.grouped_by_source_id.txt.gz"
    _group_sorted_links_if_missing(
        input_file_path=sorted_by_source_path,
        output_file_path=grouped_by_source_path,
        key_column=1,
        progress_reporter=progress_reporter,
        progress_label="group links by source id",
    )
    grouped_by_target_path = output_dir_path / "links.grouped_by_target_id.txt.gz"
    _group_sorted_links_if_missing(
        input_file_path=sorted_by_target_path,
        output_file_path=grouped_by_target_path,
        key_column=2,
        progress_reporter=progress_reporter,
        progress_label="group links by target id",
    )
    _log_progress(
        progress_reporter,
        "graph input artifacts are ready",
    )

    return GraphPreparationArtifacts(
        output_dir=output_dir_path,
        dump_date=dump_date,
        pages_file_path=pruned_pages_path,
        grouped_links_by_source_file_path=grouped_by_source_path,
        grouped_links_by_target_file_path=grouped_by_target_path,
    )


def build_graph_from_dump(
    *,
    wiki: str,
    dump_date: str,
    output_dir: Path,
    output_file_path: Path,
    merge_engine: str = "sortjoin",
    progress_reporter: ProgressReporter | None = None,
) -> GraphBuildPaths:
    preparation = prepare_graph_inputs(
        wiki=wiki,
        dump_date=dump_date,
        output_dir=output_dir,
        merge_engine=merge_engine,
        progress_reporter=progress_reporter,
    )
    if progress_reporter is None:
        build_result = build_graph_binary(
            pages_file_path=preparation.pages_file_path,
            grouped_links_by_source_file_path=preparation.grouped_links_by_source_file_path,
            grouped_links_by_target_file_path=preparation.grouped_links_by_target_file_path,
            output_file_path=output_file_path,
        )
    else:
        with progress_reporter.step(
            f"build {output_file_path.name}",
        ):
            build_result = build_graph_binary(
                pages_file_path=preparation.pages_file_path,
                grouped_links_by_source_file_path=preparation.grouped_links_by_source_file_path,
                grouped_links_by_target_file_path=preparation.grouped_links_by_target_file_path,
                output_file_path=output_file_path,
                progress_callback=progress_reporter.log,
            )
    return GraphBuildPaths(
        pages_file_path=preparation.pages_file_path,
        grouped_links_by_source_file_path=preparation.grouped_links_by_source_file_path,
        grouped_links_by_target_file_path=preparation.grouped_links_by_target_file_path,
        output_file_path=output_file_path,
        node_count=build_result.node_count,
        edge_count=build_result.edge_count,
    )


def _validate_dump_date(
    dump_date: str,
) -> None:
    if len(dump_date) != 8 or not dump_date.isdigit():
        raise ValueError(
            f"invalid dump date: {dump_date}",
        )


def _download_raw_dump_files(
    *,
    wiki: str,
    dump_date: str,
    output_dir: Path,
    progress_reporter: ProgressReporter | None,
) -> dict[str, Path]:
    download_url = f"https://dumps.wikimedia.org/{wiki}/{dump_date}"
    torrent_url = f"https://tools.wmflabs.org/dump-torrents/{wiki}/{dump_date}"
    sha1sums_path = output_dir / f"{wiki}-{dump_date}-sha1sums.txt"
    _download_file_if_missing(
        url=f"{download_url}/{sha1sums_path.name}",
        output_file_path=sha1sums_path,
        use_torrent=False,
        torrent_url=torrent_url,
        progress_reporter=progress_reporter,
    )

    file_map = {
        "redirects": output_dir / f"{wiki}-{dump_date}-redirect.sql.gz",
        "pages": output_dir / f"{wiki}-{dump_date}-page.sql.gz",
        "links": output_dir / f"{wiki}-{dump_date}-pagelinks.sql.gz",
        "targets": output_dir / f"{wiki}-{dump_date}-linktarget.sql.gz",
    }
    for file_path in file_map.values():
        _download_file_if_missing(
            url=f"{download_url}/{file_path.name}",
            output_file_path=file_path,
            use_torrent=True,
            torrent_url=torrent_url,
            progress_reporter=progress_reporter,
        )
        _verify_sha1(
            file_path=file_path,
            sha1sums_path=sha1sums_path,
            progress_reporter=progress_reporter,
        )
    return file_map


def _download_file_if_missing(
    *,
    url: str,
    output_file_path: Path,
    use_torrent: bool,
    torrent_url: str,
    progress_reporter: ProgressReporter | None,
) -> None:
    if output_file_path.exists():
        _log_progress(
            progress_reporter,
            f"skip download {output_file_path.name} (already exists)",
        )
        return

    aria2c_path = shutil.which(
        "aria2c",
    )
    if use_torrent and aria2c_path is not None:
        with _progress_step(
            progress_reporter,
            f"download {output_file_path.name} via torrent",
        ):
            subprocess.run(
                [
                    aria2c_path,
                    "--summary-interval=0",
                    "--console-log-level=warn",
                    "--seed-time=0",
                    f"{torrent_url}/{output_file_path.name}.torrent",
                ],
                check=True,
                cwd=output_file_path.parent,
            )
        return

    wget_path = shutil.which(
        "wget",
    )
    if wget_path is not None:
        with _progress_step(
            progress_reporter,
            f"download {output_file_path.name} via wget",
        ):
            subprocess.run(
                [
                    wget_path,
                    "--progress=dot:giga",
                    "-O",
                    str(output_file_path),
                    url,
                ],
                check=True,
            )
        return

    curl_path = shutil.which(
        "curl",
    )
    if curl_path is not None:
        with _progress_step(
            progress_reporter,
            f"download {output_file_path.name} via curl",
        ):
            subprocess.run(
                [
                    curl_path,
                    "--fail",
                    "--location",
                    "--progress-bar",
                    "-o",
                    str(output_file_path),
                    url,
                ],
                check=True,
            )
        return

    raise RuntimeError(
        "neither aria2c, wget, nor curl is available for downloads",
    )


def _verify_sha1(
    *,
    file_path: Path,
    sha1sums_path: Path,
    progress_reporter: ProgressReporter | None,
) -> None:
    expected_sha1 = None
    with sha1sums_path.open(
        "rt",
        encoding="utf-8",
    ) as file_handle:
        for raw_line in file_handle:
            if file_path.name not in raw_line:
                continue
            expected_sha1 = raw_line.split()[0]
            break
    if expected_sha1 is None:
        raise ValueError(
            f"missing SHA-1 entry for {file_path.name}",
        )

    digest = hashlib.sha1()
    with file_path.open(
        "rb",
    ) as file_handle:
        for chunk in iter(
            lambda: file_handle.read(1024 * 1024),
            b"",
        ):
            digest.update(
                chunk,
            )

    actual_sha1 = digest.hexdigest()
    if actual_sha1 != expected_sha1:
        raise ValueError(
            f"SHA-1 mismatch for {file_path.name}: expected {expected_sha1}, got {actual_sha1}",
        )
    _log_progress(
        progress_reporter,
        f"verified SHA-1 for {file_path.name}",
    )


def _trim_dump_if_missing(
    *,
    kind: DumpTrimKind,
    input_file_path: Path,
    output_file_path: Path,
    progress_reporter: ProgressReporter | None,
) -> None:
    if output_file_path.exists():
        _log_progress(
            progress_reporter,
            f"skip trim {kind.value} (already exists)",
        )
        return
    with _progress_step(
        progress_reporter,
        f"trim {kind.value}",
    ):
        processed_lines, written_rows = write_trimmed_dump(
            kind=kind,
            input_file_path=input_file_path,
            output_file_path=output_file_path,
            progress_callback=(
                progress_reporter.log if progress_reporter is not None else None
            ),
            progress_label=f"trim {kind.value}",
        )
    _log_progress(
        progress_reporter,
        f"trim {kind.value}: processed {processed_lines:,} SQL lines and wrote {written_rows:,} rows",
    )


def _write_gzip_rows_if_missing(
    *,
    output_file_path: Path,
    rows,
    sort_numeric_by_first_column: bool = False,
    progress_reporter: ProgressReporter | None,
    progress_label: str,
) -> None:
    if output_file_path.exists():
        _log_progress(
            progress_reporter,
            f"skip {progress_label} (already exists)",
        )
        return
    temp_output_path = output_file_path.with_suffix(
        output_file_path.suffix + ".tmp",
    )
    if sort_numeric_by_first_column:
        with tempfile.NamedTemporaryFile(
            mode="wt",
            encoding="utf-8",
            delete=False,
        ) as temp_file_handle:
            row_count = 0
            for row in rows:
                temp_file_handle.write(
                    row,
                )
                temp_file_handle.write("\n")
                row_count += 1
                if row_count % 1_000_000 == 0:
                    _log_progress(
                        progress_reporter,
                        f"{progress_label}: wrote {row_count:,} rows to temporary plaintext",
                    )
            temp_plaintext_path = Path(
                temp_file_handle.name,
            )
        sorted_plaintext_path = temp_plaintext_path.with_suffix(
            ".sorted",
        )
        try:
            _sort_plaintext_file(
                input_file_path=temp_plaintext_path,
                output_file_path=sorted_plaintext_path,
                sort_arguments=["-k1,1n"],
            )
            with (
                sorted_plaintext_path.open(
                    "rt",
                    encoding="utf-8",
                ) as input_file_handle,
                gzip.open(
                    temp_output_path,
                    "wt",
                    encoding="utf-8",
                ) as output_file_handle,
            ):
                shutil.copyfileobj(
                    input_file_handle,
                    output_file_handle,
                )
        finally:
            temp_plaintext_path.unlink(missing_ok=True)
            sorted_plaintext_path.unlink(missing_ok=True)
    else:
        with gzip.open(
            temp_output_path,
            "wt",
            encoding="utf-8",
        ) as output_file_handle:
            row_count = 0
            for row in rows:
                output_file_handle.write(
                    row,
                )
                output_file_handle.write("\n")
                row_count += 1
                if row_count % 1_000_000 == 0:
                    _log_progress(
                        progress_reporter,
                        f"{progress_label}: wrote {row_count:,} rows",
                    )

    temp_output_path.replace(
        output_file_path,
    )
    _log_progress(
        progress_reporter,
        f"done {progress_label} -> {output_file_path.name}",
    )


def _merge_links_with_duckdb(
    *,
    pages_trimmed_path: Path,
    linktarget_trimmed_path: Path,
    links_trimmed_path: Path,
    output_file_path: Path,
    temp_db_path: Path,
    progress_reporter: ProgressReporter | None,
) -> None:
    try:
        import duckdb
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "duckdb is required to prepare graph inputs; install dev dependencies with uv sync --all-groups",
        ) from exc

    temp_db_path.unlink(
        missing_ok=True,
    )
    with _progress_step(
        progress_reporter,
        f"merge raw article edge ids with DuckDB -> {output_file_path.name}",
    ):
        connection = duckdb.connect(
            str(temp_db_path),
        )
        try:
            connection.execute(
                "PRAGMA disable_progress_bar;",
            )
            connection.execute(
                f"""
            CREATE OR REPLACE TABLE pages AS
            SELECT
              page_id,
              ns,
              title
            FROM read_csv('{pages_trimmed_path}',
                          compression='gzip',
                          header=false,
                          delim='\t',
                          columns={{
                            'page_id': 'UBIGINT',
                            'ns': 'INTEGER',
                            'title': 'VARCHAR',
                            'is_redirect': 'INTEGER'
                          }})
            WHERE ns = 0;
                """,
            )
            connection.execute(
                "CREATE INDEX pages_page_id ON pages(page_id);",
            )
            connection.execute(
                "CREATE INDEX pages_ns_title ON pages(ns, title);",
            )
            connection.execute(
                f"""
            CREATE OR REPLACE TABLE linktargets AS
            SELECT
              lt_id,
              ns,
              title
            FROM read_csv('{linktarget_trimmed_path}',
                          compression='gzip',
                          header=false,
                          delim='\t',
                          columns={{
                            'lt_id': 'UBIGINT',
                            'ns': 'INTEGER',
                            'title': 'VARCHAR'
                          }})
            WHERE ns = 0;
                """,
            )
            connection.execute(
                "CREATE INDEX linktargets_lt_id ON linktargets(lt_id);",
            )
            connection.execute(
                "CREATE INDEX linktargets_ns_title ON linktargets(ns, title);",
            )
            connection.execute(
                f"""
            COPY (
                SELECT
                    l.src_id AS src_id,
                    tgt.page_id AS tgt_id
                FROM read_csv('{links_trimmed_path}',
                              compression='gzip',
                              header=false,
                              delim='\t',
                              columns={{
                                'src_id': 'UBIGINT',
                                'src_ns': 'INTEGER',
                                'tgt_lt_id': 'UBIGINT'
                              }}) AS l
                JOIN linktargets AS lt ON lt.lt_id = l.tgt_lt_id
                JOIN pages AS tgt ON (tgt.ns, tgt.title) = (lt.ns, lt.title)
                WHERE l.src_ns = 0
            )
            TO '{output_file_path}' (DELIMITER '\t', HEADER false, COMPRESSION 'gzip');
                """,
            )
        finally:
            connection.close()


def _merge_links_with_sort_join(
    *,
    pages_trimmed_path: Path,
    linktarget_trimmed_path: Path,
    links_trimmed_path: Path,
    output_file_path: Path,
    progress_reporter: ProgressReporter | None,
) -> None:
    join_tool = _resolve_gnu_join()
    sort_tool = _resolve_gnu_sort()
    gzip_tool = shutil.which("pigz") or shutil.which("gzip")
    if join_tool is None or sort_tool is None or gzip_tool is None:
        raise RuntimeError(
            "GNU join, GNU sort, and gzip/pigz are required for merge_engine=sortjoin",
        )

    gzip_compress_flag = "--fast" if os.path.basename(gzip_tool) == "pigz" else "-1"
    sort_mem_arg = "-S 60%" if _is_gnu_sort(sort_tool) else ""
    sort_cmd = f"LC_ALL=C {shlex.quote(sort_tool)} {sort_mem_arg} -t$'\\t'"
    command = f"""
set -euo pipefail
decompress() {{ {shlex.quote(gzip_tool)} -dc "$1"; }}
LC_ALL=C {shlex.quote(join_tool)} -t $'\t' -1 1 -2 1 \
  <(
    decompress {shlex.quote(str(pages_trimmed_path))} |
    awk -F'\t' '$2=="0" {{print $3"\t"$1}}' |
    {sort_cmd} -k1,1
  ) \
  <(
    decompress {shlex.quote(str(linktarget_trimmed_path))} |
    awk -F'\t' '$2=="0" {{print $3"\t"$1}}' |
    {sort_cmd} -k1,1
  ) |
awk -F'\t' '{{print $3"\t"$2}}' |
{sort_cmd} -k1,1 |
LC_ALL=C {shlex.quote(join_tool)} -t $'\t' -1 1 -2 1 \
  - \
  <(
    decompress {shlex.quote(str(links_trimmed_path))} |
    awk -F'\t' '$2=="0" {{print $3"\t"$1}}' |
    {sort_cmd} -k1,1
  ) |
awk -F'\t' '{{print $3"\t"$2}}' |
{shlex.quote(gzip_tool)} {gzip_compress_flag} > {shlex.quote(str(output_file_path))}
"""

    with _progress_step(
        progress_reporter,
        f"merge raw article edge ids with sort/join -> {output_file_path.name}",
    ):
        subprocess.run(
            ["bash", "-lc", command],
            check=True,
            env={**os.environ, "LC_ALL": "C"},
        )


def _sort_and_dedupe_links_if_missing(
    *,
    input_file_path: Path,
    output_file_path: Path,
    sort_column: int,
    progress_reporter: ProgressReporter | None,
    progress_label: str,
) -> None:
    if output_file_path.exists():
        _log_progress(
            progress_reporter,
            f"skip {progress_label} (already exists)",
        )
        return
    gzip_tool = shutil.which("pigz") or shutil.which("gzip")
    sort_tool = _resolve_gnu_sort()
    if gzip_tool is None or sort_tool is None:
        raise RuntimeError(
            "gzip/pigz and GNU sort are required to prepare graph inputs",
        )

    sort_arguments = [sort_tool]
    if _is_gnu_sort(
        sort_tool,
    ):
        sort_arguments.extend(["-S", "80%"])
    sort_arguments.extend(["-t", r"$'\t'", f"-k{sort_column},{sort_column}n"])
    quoted_input = shlex.quote(
        str(input_file_path),
    )
    quoted_output = shlex.quote(
        str(output_file_path) + ".tmp",
    )
    gzip_decompress_flag = "-dc"
    gzip_compress_flag = "--fast" if os.path.basename(gzip_tool) == "pigz" else "-1"
    command = (
        f"{shlex.quote(gzip_tool)} {gzip_decompress_flag} {quoted_input} | "
        f"{' '.join(sort_arguments)} | uniq | "
        f"{shlex.quote(gzip_tool)} {gzip_compress_flag} > {quoted_output}"
    )
    with _progress_step(
        progress_reporter,
        progress_label,
    ):
        subprocess.run(
            ["bash", "-lc", command],
            check=True,
        )
    Path(str(output_file_path) + ".tmp").replace(
        output_file_path,
    )


def _group_sorted_links_if_missing(
    *,
    input_file_path: Path,
    output_file_path: Path,
    key_column: int,
    progress_reporter: ProgressReporter | None,
    progress_label: str,
) -> None:
    if output_file_path.exists():
        _log_progress(
            progress_reporter,
            f"skip {progress_label} (already exists)",
        )
        return
    temp_output_path = Path(
        str(output_file_path) + ".tmp",
    )
    with _progress_step(
        progress_reporter,
        progress_label,
    ):
        with (
            gzip.open(
                input_file_path,
                "rt",
                encoding="utf-8",
            ) as input_file_handle,
            gzip.open(
                temp_output_path,
                "wt",
                encoding="utf-8",
            ) as output_file_handle,
        ):
            current_key: str | None = None
            current_values: list[str] = []
            input_row_count = 0

            for raw_line in input_file_handle:
                stripped_line = raw_line.rstrip("\n")
                if not stripped_line:
                    continue
                source_id, target_id = stripped_line.split("\t")
                key = source_id if key_column == 1 else target_id
                value = target_id if key_column == 1 else source_id
                if current_key is None:
                    current_key = key
                if key != current_key:
                    output_file_handle.write(
                        f"{current_key}\t{'|'.join(current_values)}\n",
                    )
                    current_key = key
                    current_values = [value]
                else:
                    current_values.append(
                        value,
                    )
                input_row_count += 1
                if input_row_count % 1_000_000 == 0:
                    _log_progress(
                        progress_reporter,
                        f"{progress_label}: grouped {input_row_count:,} sorted edges",
                    )

            if current_key is not None:
                output_file_handle.write(
                    f"{current_key}\t{'|'.join(current_values)}\n",
                )

    temp_output_path.replace(
        output_file_path,
    )


def _sort_plaintext_file(
    *,
    input_file_path: Path,
    output_file_path: Path,
    sort_arguments: list[str],
) -> None:
    sort_tool = _resolve_gnu_sort()
    if sort_tool is None:
        raise RuntimeError(
            "GNU sort is required to prepare graph inputs",
        )
    command = [sort_tool]
    if _is_gnu_sort(
        sort_tool,
    ):
        command.extend(["-S", "80%"])
    command.extend(["-t", "\t", *sort_arguments, str(input_file_path)])
    with output_file_path.open(
        "wb",
    ) as output_file_handle:
        subprocess.run(
            command,
            check=True,
            stdout=output_file_handle,
            env={**os.environ, "LC_ALL": "C"},
        )


def _is_gnu_sort(
    sort_tool: str,
) -> bool:
    result = subprocess.run(
        [sort_tool, "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and "GNU" in result.stdout


def _is_gnu_join(
    join_tool: str,
) -> bool:
    result = subprocess.run(
        [join_tool, "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and "GNU" in result.stdout


def _resolve_gnu_sort() -> str | None:
    gsort_tool = shutil.which("gsort")
    if gsort_tool is not None:
        return gsort_tool

    sort_tool = shutil.which("sort")
    if sort_tool is not None and _is_gnu_sort(sort_tool):
        return sort_tool
    return None


def _resolve_gnu_join() -> str | None:
    gjoin_tool = shutil.which("gjoin")
    if gjoin_tool is not None:
        return gjoin_tool

    join_tool = shutil.which("join")
    if join_tool is not None and _is_gnu_join(join_tool):
        return join_tool
    return None


def _log_progress(
    progress_reporter: ProgressReporter | None,
    message: str,
) -> None:
    if progress_reporter is None:
        return
    progress_reporter.log(
        message,
    )


def _progress_step(
    progress_reporter: ProgressReporter | None,
    label: str,
):
    if progress_reporter is None:
        return nullcontext()
    return progress_reporter.step(
        label,
    )
