from __future__ import annotations

import os
import re
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
SNAPSHOT_ID_PATTERN = re.compile(
    r"^(?P<wiki>[A-Za-z0-9_-]+)-(?P<dump_date>\d{8})$",
)


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
    *,
    snapshot_id: str | None = None,
) -> Path:
    return resolve_graph_selection(
        graph_path,
        snapshot_id=snapshot_id,
    ).graph_path


def resolve_installed_graph_file_path(
    *,
    snapshot_id: str | None = None,
) -> Path:
    if snapshot_id is not None:
        return _resolve_installed_graph_file_for_snapshot(
            snapshot_id,
        )
    return _resolve_installed_graph_file()


def resolve_graph_selection(
    graph_path: Path | None,
    *,
    snapshot_id: str | None = None,
) -> GraphSelection:
    explicit_graph_path = _expand_optional_path(
        graph_path,
    )
    if explicit_graph_path is not None:
        return GraphSelection(
            graph_path=_require_graph_file_for_snapshot(
                explicit_graph_path,
                snapshot_id=snapshot_id,
            ),
            selected_via="explicit",
        )

    if snapshot_id is not None:
        return GraphSelection(
            graph_path=_resolve_installed_graph_file_for_snapshot(
                snapshot_id,
            ),
            selected_via="installed_snapshot",
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
        if graph_path is not None:
            _validate_graph_snapshot_id(
                resolve_graph_file_path(
                    graph_path,
                ),
                snapshot_id,
            )
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


def _require_graph_file_for_snapshot(
    graph_path: Path,
    *,
    snapshot_id: str | None,
) -> Path:
    resolved_graph_path = _require_graph_file(
        graph_path,
    )
    _validate_graph_snapshot_id(
        resolved_graph_path,
        snapshot_id,
    )
    return resolved_graph_path


def _validate_graph_snapshot_id(
    graph_path: Path,
    snapshot_id: str | None,
) -> None:
    if snapshot_id is None:
        return
    inferred_snapshot_id = infer_snapshot_id_from_graph_path(
        graph_path,
    )
    if inferred_snapshot_id == snapshot_id:
        return
    if inferred_snapshot_id is None:
        raise ValueError(
            "cannot verify pinned graph snapshot_id "
            f"{snapshot_id!r} from graph file name: {graph_path}. "
            "Use a dated graph file name like "
            f"{graph_file_name_for_snapshot_id(snapshot_id)!r}.",
        )
    raise ValueError(
        "graph snapshot_id mismatch: "
        f"requested {snapshot_id!r}, selected {inferred_snapshot_id!r} "
        f"from {graph_path}",
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


def _resolve_installed_graph_file_for_snapshot(
    snapshot_id: str,
) -> Path:
    install_dir = get_default_graph_install_dir()
    graph_path = install_dir / graph_file_name_for_snapshot_id(
        snapshot_id,
    )
    if graph_path.exists():
        return _require_graph_file_for_snapshot(
            graph_path,
            snapshot_id=snapshot_id,
        )
    raise FileNotFoundError(
        f"pinned graph snapshot {snapshot_id!r} is not installed. "
        f"Checked: {graph_path}. "
        f"{_graph_install_hint(install_dir, snapshot_id=snapshot_id)}",
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


def graph_file_name_for_snapshot_id(
    snapshot_id: str,
) -> str:
    wiki, dump_date = _parse_snapshot_id(
        snapshot_id,
    )
    return graph_file_name(
        wiki=wiki,
        dump_date=dump_date,
    )


def _parse_snapshot_id(
    snapshot_id: str,
) -> tuple[str, str]:
    match = SNAPSHOT_ID_PATTERN.fullmatch(
        snapshot_id,
    )
    if match is None:
        raise ValueError(
            f"invalid graph snapshot_id {snapshot_id!r}; "
            "expected a value like 'enwiki-20260401'",
        )
    return (
        match.group(
            "wiki",
        ),
        match.group(
            "dump_date",
        ),
    )


def _graph_install_hint(
    install_dir: Path,
    *,
    snapshot_id: str | None = None,
) -> str:
    if snapshot_id is not None:
        wiki, dump_date = _parse_snapshot_id(
            snapshot_id,
        )
        return (
            f"Run `wikiarena graph install --tag graph-{wiki}-{dump_date}`, "
            "or pass an explicit matching graph path."
        )
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
