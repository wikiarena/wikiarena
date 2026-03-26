from __future__ import annotations

import re
from pathlib import Path

GRAPH_FILE_PREFIX = "wikiarena_graph"
GRAPH_FILE_SUFFIX = ".bin"
GRAPH_METADATA_SUFFIX = ".metadata.json"
STANDARD_GRAPH_FILE_NAME_PATTERN = re.compile(
    r"^wikiarena_graph_(?P<wiki>[A-Za-z0-9_-]+)_(?P<dump_date>\d{8})\.bin$",
)


def graph_file_name(
    *,
    wiki: str,
    dump_date: str,
) -> str:
    return f"{GRAPH_FILE_PREFIX}_{wiki}_{dump_date}{GRAPH_FILE_SUFFIX}"


def graph_metadata_file_name(
    *,
    wiki: str,
    dump_date: str,
) -> str:
    return f"{GRAPH_FILE_PREFIX}_{wiki}_{dump_date}{GRAPH_METADATA_SUFFIX}"


def graph_snapshot_id(
    *,
    wiki: str,
    dump_date: str,
) -> str:
    return f"{wiki}-{dump_date}"


def is_standard_graph_file_name(
    file_name: str,
) -> bool:
    return (
        STANDARD_GRAPH_FILE_NAME_PATTERN.fullmatch(
            file_name,
        )
        is not None
    )


def parse_standard_graph_file_name(
    file_name: str,
) -> tuple[str, str] | None:
    match = STANDARD_GRAPH_FILE_NAME_PATTERN.fullmatch(
        file_name,
    )
    if match is None:
        return None
    return (
        match.group("wiki"),
        match.group("dump_date"),
    )


def list_standard_graph_files(
    install_dir: Path,
) -> tuple[Path, ...]:
    if not install_dir.exists():
        return ()

    matching_paths = [
        child_path
        for child_path in install_dir.iterdir()
        if child_path.is_file() and is_standard_graph_file_name(child_path.name)
    ]
    matching_paths.sort(
        key=_graph_file_sort_key,
        reverse=True,
    )
    return tuple(
        matching_paths,
    )


def _graph_file_sort_key(
    file_path: Path,
) -> tuple[str, str]:
    parsed = parse_standard_graph_file_name(
        file_path.name,
    )
    if parsed is None:
        return ("", "")
    wiki, dump_date = parsed
    return dump_date, wiki
