from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from wikiarena.graph.naming import (
    graph_file_name,
    graph_snapshot_id,
    list_standard_graph_files,
    parse_standard_graph_file_name,
)
from wikiarena.paths import get_default_graph_install_dir
from wikiarena.protocol.enums import NavigationBackend

GRAPH_PATH_ENV_VAR = "WIKIARENA_GRAPH_PATH"


@dataclass(frozen=True)
class GraphSelection:
    graph_path: Path
    selected_via: str


class NavigationRuntimeConfig(BaseModel):
    backend: NavigationBackend = NavigationBackend.LIVE
    graph_path: Path | None = None
    snapshot_id: str | None = None


def resolve_graph_file_path(
    graph_path: Path | None,
) -> Path:
    return resolve_graph_selection(
        graph_path,
    ).graph_path


def resolve_installed_graph_file_path() -> Path:
    return _resolve_installed_graph_file()


def resolve_graph_selection(
    graph_path: Path | None,
) -> GraphSelection:
    explicit_graph_path = _expand_optional_path(
        graph_path,
    )
    if explicit_graph_path is not None:
        return GraphSelection(
            graph_path=_require_graph_file(
                explicit_graph_path,
            ),
            selected_via="explicit",
        )

    env_graph_path = os.getenv(
        GRAPH_PATH_ENV_VAR,
    )
    if env_graph_path:
        return GraphSelection(
            graph_path=_require_graph_file(
                Path(
                    env_graph_path,
                ).expanduser(),
            ),
            selected_via="environment_variable",
        )

    return GraphSelection(
        graph_path=_resolve_installed_graph_file(),
        selected_via="installed_latest",
    )


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
    default_install_dir = get_default_graph_install_dir()
    if graph_path.is_dir():
        raise FileNotFoundError(
            f"graph path is a directory: {graph_path}",
        )
    if graph_path.exists():
        resolved_graph_path = graph_path.resolve()
        if (
            graph_path.name == "wikiarena_graph.bin"
            and parse_standard_graph_file_name(resolved_graph_path.name) is None
        ):
            raise FileNotFoundError(
                "legacy graph file name is no longer supported. "
                f"Checked: {graph_path}. "
                "Use a dated file name like "
                f"{_installed_graph_example_path(default_install_dir)}.",
            )
        return resolved_graph_path

    if graph_path.name == "wikiarena_graph.bin":
        raise FileNotFoundError(
            "legacy graph file name is no longer supported. "
            f"Checked: {graph_path}. "
            "Use a dated file name like "
            f"{_installed_graph_example_path(default_install_dir)}.",
        )
    raise FileNotFoundError(
        f"local graph file not found. Checked: {graph_path}. "
        f"{_graph_install_hint(default_install_dir)}",
    )


def _resolve_installed_graph_file() -> Path:
    install_dir = get_default_graph_install_dir()
    installed_graph_files = list_standard_graph_files(
        install_dir,
    )
    if not installed_graph_files:
        raise FileNotFoundError(
            f"no installed dated graph file found. Checked: {install_dir}. "
            f"{_graph_install_hint(install_dir)}",
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


def _graph_install_hint(
    install_dir: Path,
) -> str:
    return (
        "Run `wikiarena graph install`, pass an explicit graph path, set WIKIARENA_GRAPH_PATH, "
        "or install a dated graph like "
        f"{_installed_graph_example_path(install_dir)}."
    )


def _installed_graph_example_path(
    install_dir: Path,
) -> Path:
    return install_dir / graph_file_name(
        wiki="enwiki",
        dump_date="20260301",
    )
