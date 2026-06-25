from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from wikiarena.protocol.enums import SolverBackend
from wikiarena.wiki_runtime import resolve_graph_file_path, resolve_graph_snapshot_id


class SolverRuntimeConfig(BaseModel):
    backend: SolverBackend = SolverBackend.NONE
    graph_path: Path | None = None
    snapshot_id: str | None = None
    endpoint: str | None = None


def resolve_solver_graph_file_path(
    graph_path: Path | None,
    *,
    fallback_graph_path: Path | None = None,
    snapshot_id: str | None = None,
) -> Path:
    if graph_path is not None:
        return resolve_graph_file_path(
            graph_path,
            snapshot_id=snapshot_id,
        )
    if fallback_graph_path is not None:
        return resolve_graph_file_path(
            fallback_graph_path,
            snapshot_id=snapshot_id,
        )
    return resolve_graph_file_path(
        None,
        snapshot_id=snapshot_id,
    )


def resolve_solver_snapshot_id(
    graph_path: Path | None,
    snapshot_id: str | None,
    *,
    fallback_graph_path: Path | None = None,
) -> str | None:
    if snapshot_id is not None:
        if graph_path is not None or fallback_graph_path is not None:
            resolve_solver_graph_file_path(
                graph_path,
                fallback_graph_path=fallback_graph_path,
                snapshot_id=snapshot_id,
            )
        return snapshot_id
    resolved_graph_path = resolve_solver_graph_file_path(
        graph_path,
        fallback_graph_path=fallback_graph_path,
    )
    return resolve_graph_snapshot_id(
        resolved_graph_path,
        None,
    )
