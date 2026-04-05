from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path

import requests

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


@dataclass(frozen=True)
class DumpFileMetadata:
    file_name: str
    url: str
    size_bytes: int
    sha1: str


WIKIMEDIA_DUMP_INDEX_URL = "https://dumps.wikimedia.org/index.json"
HTTP_TIMEOUT_SECONDS = 60
HTTP_DOWNLOAD_CHUNK_SIZE_BYTES = 1024 * 1024
SQL_TRIMMER_BIN_ENV_VAR = "WIKIARENA_SQL_TRIMMER_BIN"
DEFAULT_SQL_TRIMMER_BINARY_PATH = (
    Path(__file__).resolve().parents[3]
    / "rust/wikiarena-sql-trimmer/target/release/wikiarena-sql-trimmer"
)
REQUIRED_DUMP_FILE_SPECS = {
    "redirects": (
        "redirecttable",
        "redirect.sql.gz",
    ),
    "pages": (
        "pagetable",
        "page.sql.gz",
    ),
    "links": (
        "pagelinkstable",
        "pagelinks.sql.gz",
    ),
    "targets": (
        "linktargettable",
        "linktarget.sql.gz",
    ),
}


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

    dump_index = _fetch_dump_index_payload()
    wikis_payload = dump_index.get(
        "wikis",
    )
    if not isinstance(
        wikis_payload,
        dict,
    ):
        raise ValueError(
            "dump index payload is missing wikis metadata",
        )
    wiki_payload = wikis_payload.get(
        wiki,
    )
    if not isinstance(
        wiki_payload,
        dict,
    ):
        raise ValueError(
            f"dump index payload is missing wiki {wiki}",
        )
    jobs_payload = wiki_payload.get(
        "jobs",
    )
    if not isinstance(
        jobs_payload,
        dict,
    ):
        raise ValueError(
            f"dump index payload is missing jobs for wiki {wiki}",
        )
    pagelinkstable_payload = jobs_payload.get(
        "pagelinkstable",
    )
    if not isinstance(
        pagelinkstable_payload,
        dict,
    ):
        raise ValueError(
            f"dump index payload is missing pagelinkstable for wiki {wiki}",
        )
    dump_date = _resolve_dump_date_from_pagelinkstable_job(
        pagelinkstable_payload,
    )
    _validate_dump_date(
        dump_date,
    )
    return dump_date


def _fetch_dump_index_payload() -> dict[str, object]:
    return _fetch_json_payload(
        WIKIMEDIA_DUMP_INDEX_URL,
    )


def _fetch_dump_status_payload(
    *,
    wiki: str,
    dump_date: str,
) -> dict[str, object]:
    return _fetch_json_payload(
        f"https://dumps.wikimedia.org/{wiki}/{dump_date}/dumpstatus.json",
    )


def _fetch_json_payload(
    url: str,
) -> dict[str, object]:
    with requests.Session() as session:
        response = session.get(
            url,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            f"expected JSON object from {url}",
        )
    return payload


def _resolve_dump_date_from_pagelinkstable_job(
    job_payload: dict[str, object],
) -> str:
    files_payload = job_payload.get(
        "files",
    )
    if isinstance(
        files_payload,
        dict,
    ):
        for file_name, file_metadata in files_payload.items():
            dump_date = _extract_dump_date_from_text(
                file_name,
            )
            if dump_date is not None:
                return dump_date
            if not isinstance(
                file_metadata,
                dict,
            ):
                continue
            file_url = file_metadata.get(
                "url",
            )
            if not isinstance(
                file_url,
                str,
            ):
                continue
            dump_date = _extract_dump_date_from_text(
                file_url,
            )
            if dump_date is not None:
                return dump_date

    updated_value = job_payload.get(
        "updated",
    )
    if isinstance(
        updated_value,
        str,
    ):
        dump_date = _extract_dump_date_from_text(
            updated_value,
        )
        if dump_date is not None:
            return dump_date

    raise ValueError(
        "could not resolve pagelinkstable dump date from Wikimedia dump index",
    )


def _extract_dump_date_from_text(
    text: str,
) -> str | None:
    match = re.search(
        r"(?<!\d)(\d{8})(?!\d)",
        text,
    )
    if match is None:
        return None
    return match.group(
        1,
    )


def prepare_graph_inputs(
    *,
    wiki: str,
    dump_date: str,
    output_dir: Path,
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
        _merge_links_with_sort_join(
            pages_trimmed_path=pages_trimmed_path,
            linktarget_trimmed_path=targets_trimmed_path,
            links_trimmed_path=links_trimmed_path,
            output_file_path=raw_edges_path,
            progress_reporter=progress_reporter,
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
    progress_reporter: ProgressReporter | None = None,
) -> GraphBuildPaths:
    preparation = prepare_graph_inputs(
        wiki=wiki,
        dump_date=dump_date,
        output_dir=output_dir,
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
    dump_files = _discover_dump_file_metadata(
        wiki=wiki,
        dump_date=dump_date,
    )

    file_map: dict[str, Path] = {}
    for file_label, dump_file in dump_files.items():
        file_path = output_dir / dump_file.file_name
        _download_file_if_missing(
            url=dump_file.url,
            output_file_path=file_path,
            expected_size_bytes=dump_file.size_bytes,
            progress_reporter=progress_reporter,
        )
        _verify_sha1(
            file_path=file_path,
            expected_sha1=dump_file.sha1,
            progress_reporter=progress_reporter,
        )
        file_map[file_label] = file_path
    return file_map


def _discover_dump_file_metadata(
    *,
    wiki: str,
    dump_date: str,
) -> dict[str, DumpFileMetadata]:
    dump_status_payload = _fetch_dump_status_payload(
        wiki=wiki,
        dump_date=dump_date,
    )
    jobs_payload = dump_status_payload.get(
        "jobs",
    )
    if not isinstance(
        jobs_payload,
        dict,
    ):
        raise ValueError(
            "dumpstatus payload is missing a jobs object",
        )

    dump_files: dict[str, DumpFileMetadata] = {}
    for file_label, (job_name, file_suffix) in REQUIRED_DUMP_FILE_SPECS.items():
        job_payload = jobs_payload.get(
            job_name,
        )
        if not isinstance(
            job_payload,
            dict,
        ):
            raise ValueError(
                f"dumpstatus payload is missing job {job_name}",
            )
        if job_payload.get("status") != "done":
            raise ValueError(
                f"dumpstatus job {job_name} is not done for {wiki}-{dump_date}",
            )

        files_payload = job_payload.get(
            "files",
        )
        if not isinstance(
            files_payload,
            dict,
        ):
            raise ValueError(
                f"dumpstatus job {job_name} is missing files metadata",
            )

        file_name = f"{wiki}-{dump_date}-{file_suffix}"
        file_payload = files_payload.get(
            file_name,
        )
        if not isinstance(
            file_payload,
            dict,
        ):
            raise ValueError(
                f"dumpstatus job {job_name} is missing file {file_name}",
            )

        file_url = file_payload.get(
            "url",
        )
        file_size = file_payload.get(
            "size",
        )
        file_sha1 = file_payload.get(
            "sha1",
        )
        if (
            not isinstance(
                file_url,
                str,
            )
            or not isinstance(
                file_size,
                int,
            )
            or not isinstance(
                file_sha1,
                str,
            )
        ):
            raise ValueError(
                f"dumpstatus file metadata is incomplete for {file_name}",
            )

        dump_files[file_label] = DumpFileMetadata(
            file_name=file_name,
            url=_absolute_dump_url(
                file_url,
            ),
            size_bytes=file_size,
            sha1=file_sha1,
        )

    return dump_files


def _absolute_dump_url(
    url: str,
) -> str:
    if url.startswith(
        "http://",
    ) or url.startswith(
        "https://",
    ):
        return url
    return f"https://dumps.wikimedia.org{url}"


def _download_file_if_missing(
    *,
    url: str,
    output_file_path: Path,
    expected_size_bytes: int,
    progress_reporter: ProgressReporter | None,
) -> None:
    existing_size_bytes = 0
    if output_file_path.exists():
        existing_size_bytes = output_file_path.stat().st_size
    if existing_size_bytes == expected_size_bytes:
        _log_progress(
            progress_reporter,
            f"skip download {output_file_path.name} (already exists)",
        )
        return

    if existing_size_bytes > expected_size_bytes:
        _log_progress(
            progress_reporter,
            f"restart download {output_file_path.name} (local file is larger than expected)",
        )
        existing_size_bytes = 0

    with _progress_step(
        progress_reporter,
        f"download {output_file_path.name} via python http",
    ):
        request_headers: dict[str, str] | None = None
        if existing_size_bytes > 0:
            request_headers = {
                "Range": f"bytes={existing_size_bytes}-",
            }

        with requests.Session() as session:
            with session.get(
                url,
                headers=request_headers,
                stream=True,
                timeout=HTTP_TIMEOUT_SECONDS,
            ) as response:
                response.raise_for_status()

                write_mode = "ab"
                if existing_size_bytes > 0 and response.status_code != 206:
                    _log_progress(
                        progress_reporter,
                        f"resume unsupported for {output_file_path.name}; restarting full download",
                    )
                    existing_size_bytes = 0
                    write_mode = "wb"
                elif existing_size_bytes == 0:
                    write_mode = "wb"

                with output_file_path.open(
                    write_mode,
                ) as file_handle:
                    for chunk in response.iter_content(
                        chunk_size=HTTP_DOWNLOAD_CHUNK_SIZE_BYTES,
                    ):
                        if not chunk:
                            continue
                        file_handle.write(
                            chunk,
                        )

    final_size_bytes = output_file_path.stat().st_size
    if final_size_bytes != expected_size_bytes:
        raise ValueError(
            f"download size mismatch for {output_file_path.name}: expected {expected_size_bytes}, got {final_size_bytes}",
        )


def _verify_sha1(
    *,
    file_path: Path,
    expected_sha1: str,
    progress_reporter: ProgressReporter | None,
) -> None:
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
        sql_trimmer_binary_path = _resolve_sql_trimmer_binary_path()
        if sql_trimmer_binary_path is None:
            processed_lines, written_rows = write_trimmed_dump(
                kind=kind,
                input_file_path=input_file_path,
                output_file_path=output_file_path,
                progress_callback=(
                    progress_reporter.log if progress_reporter is not None else None
                ),
                progress_label=f"trim {kind.value}",
            )
        else:
            processed_lines, written_rows = _write_trimmed_dump_with_rust(
                kind=kind,
                input_file_path=input_file_path,
                output_file_path=output_file_path,
                sql_trimmer_binary_path=sql_trimmer_binary_path,
            )
    _log_progress(
        progress_reporter,
        f"trim {kind.value}: processed {processed_lines:,} SQL lines and wrote {written_rows:,} rows",
    )


def _resolve_sql_trimmer_binary_path() -> Path | None:
    configured_binary_path = os.getenv(
        SQL_TRIMMER_BIN_ENV_VAR,
    )
    if configured_binary_path:
        resolved_binary_path = Path(
            configured_binary_path,
        ).expanduser()
        if not resolved_binary_path.exists():
            raise FileNotFoundError(
                f"configured SQL trimmer binary does not exist: {resolved_binary_path}",
            )
        return resolved_binary_path

    if DEFAULT_SQL_TRIMMER_BINARY_PATH.exists():
        return DEFAULT_SQL_TRIMMER_BINARY_PATH
    return None


def _write_trimmed_dump_with_rust(
    *,
    kind: DumpTrimKind,
    input_file_path: Path,
    output_file_path: Path,
    sql_trimmer_binary_path: Path,
) -> tuple[int, int]:
    gzip_tool = shutil.which("pigz") or shutil.which("gzip")
    if gzip_tool is None:
        raise RuntimeError(
            "gzip/pigz is required to run the Rust SQL trimmer",
        )

    temp_output_path = output_file_path.with_suffix(
        output_file_path.suffix + ".tmp",
    )
    with tempfile.NamedTemporaryFile(
        mode="wt",
        encoding="utf-8",
        suffix=".json",
        delete=False,
    ) as stats_file_handle:
        stats_file_path = Path(
            stats_file_handle.name,
        )

    command = f"""
set -euo pipefail
{shlex.quote(gzip_tool)} -dc {shlex.quote(str(input_file_path))} |
{shlex.quote(str(sql_trimmer_binary_path))} \
  --kind {shlex.quote(kind.value)} \
  --stats-path {shlex.quote(str(stats_file_path))} |
{shlex.quote(gzip_tool)} -c > {shlex.quote(str(temp_output_path))}
"""

    try:
        result = subprocess.run(
            ["bash", "-lc", command],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Rust SQL trimmer failed: "
                f"{result.stderr.strip() or result.stdout.strip() or 'unknown error'}",
            )

        stats_payload = json.loads(
            stats_file_path.read_text(
                encoding="utf-8",
            ),
        )
        processed_lines = stats_payload["processed_lines"]
        written_rows = stats_payload["written_rows"]
        if not isinstance(
            processed_lines,
            int,
        ) or not isinstance(
            written_rows,
            int,
        ):
            raise ValueError(
                "Rust SQL trimmer stats file is missing integer counters",
            )
        os.replace(
            temp_output_path,
            output_file_path,
        )
        return processed_lines, written_rows
    finally:
        temp_output_path.unlink(
            missing_ok=True,
        )
        stats_file_path.unlink(
            missing_ok=True,
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
            "GNU join, GNU sort, and gzip/pigz are required to prepare graph inputs",
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
