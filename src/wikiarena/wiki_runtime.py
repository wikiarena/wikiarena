from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

from wikiarena.graph import (
    graph_snapshot_id,
    list_standard_graph_files,
    parse_standard_graph_file_name,
)
from wikiarena.protocol.enums import WikiBackend

DEFAULT_GRAPH_INSTALL_DIR = Path("~/.wikiarena").expanduser()
GRAPH_PATH_ENV_VAR = "WIKIARENA_GRAPH_PATH"


class WikiRuntimeConfig(BaseModel):
    backend: WikiBackend = WikiBackend.LIVE
    graph_path: Path | None = None
    snapshot_id: str | None = None


def resolve_graph_file_path(
    graph_path: Path | None,
) -> Path:
    explicit_graph_path = _expand_optional_path(
        graph_path,
    )
    if explicit_graph_path is not None:
        return _require_graph_file(
            explicit_graph_path,
        )

    env_graph_path = os.getenv(
        GRAPH_PATH_ENV_VAR,
    )
    if env_graph_path:
        return _require_graph_file(
            Path(
                env_graph_path,
            ).expanduser(),
        )

    return _resolve_installed_graph_file()


def resolve_graph_snapshot_id(
    graph_path: Path | None,
    snapshot_id: str | None,
) -> str | None:
    if snapshot_id is not None:
        return snapshot_id
    resolved_graph_path = resolve_graph_file_path(
        graph_path,
    )
    return infer_snapshot_id_from_graph_path(
        resolved_graph_path,
    )


def _expand_optional_path(
    graph_path: Path | None,
) -> Path | None:
    if graph_path is None:
        return None
    return Path(
        graph_path,
    ).expanduser()


def _require_graph_file(
    graph_path: Path,
) -> Path:
    if graph_path.is_dir():
        raise FileNotFoundError(
            f"graph path is a directory: {graph_path}",
        )
    if graph_path.name == "wikiarena_graph.bin":
        raise FileNotFoundError(
            "legacy graph file name is no longer supported. "
            f"Checked: {graph_path}. "
            "Use a dated file name like wikiarena_graph_enwiki_20260301.bin.",
        )
    if not graph_path.exists():
        raise FileNotFoundError(
            "local graph file not found. "
            f"Checked: {graph_path}. "
            "Pass --graph-path, set WIKIARENA_GRAPH_PATH, or install a dated graph like ~/.wikiarena/wikiarena_graph_enwiki_20260301.bin.",
        )
    return graph_path.resolve()


def _resolve_installed_graph_file() -> Path:
    installed_graph_files = list_standard_graph_files(
        DEFAULT_GRAPH_INSTALL_DIR,
    )
    if not installed_graph_files:
        raise FileNotFoundError(
            "no installed dated graph file found. "
            f"Checked: {DEFAULT_GRAPH_INSTALL_DIR}. "
            "Pass --graph-path, set WIKIARENA_GRAPH_PATH, or install a dated graph like ~/.wikiarena/wikiarena_graph_enwiki_20260301.bin.",
        )
    assert installed_graph_files
    installed_graph_file = next(
        iter(installed_graph_files),
    )
    return _require_graph_file(
        installed_graph_file,
    )


def infer_snapshot_id_from_graph_path(
    graph_path: Path,
) -> str | None:
    parsed = parse_standard_graph_file_name(
        graph_path.name,
    )
    if parsed is None:
        return None
    wiki, dump_date = parsed
    return graph_snapshot_id(
        wiki=wiki,
        dump_date=dump_date,
    )
