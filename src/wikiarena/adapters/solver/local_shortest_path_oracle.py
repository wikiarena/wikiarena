from __future__ import annotations

from datetime import datetime
from typing import Protocol

from wikiarena.protocol.enums import PathKind
from wikiarena.protocol.enums import PathSource
from wikiarena.protocol.specs import ReferencePath
from wikiarena.protocol.specs import TaskSpec
from wikiarena.solver.models import SolverResponse


class LocalShortestPathOracle:
    """Adapter around a local shortest-path backend."""

    def __init__(
        self,
        solver_backend: "ShortestPathBackend",
        *,
        snapshot_id: str | None = None,
        max_paths: int = 5,
    ):
        self.solver_backend = solver_backend
        self.snapshot_id = snapshot_id
        self.max_paths = max_paths

    async def get_reference_paths(
        self,
        task: TaskSpec,
    ) -> list[ReferencePath]:
        solver_response = await self.solver_backend.find_shortest_path(
            start_page=task.start_page_title,
            target_page=task.target_page_title,
        )
        selected_paths = solver_response.paths[: self.max_paths]
        computed_at = datetime.now()

        return [
            ReferencePath(
                path_kind=PathKind.SHORTEST,
                page_titles=path,
                hop_count=solver_response.path_length,
                computed_at=computed_at,
                valid_for_snapshot_id=self.snapshot_id,
                source=PathSource.LOCAL_SQLITE,
            )
            for path in selected_paths
        ]


class ShortestPathBackend(Protocol):
    async def find_shortest_path(
        self,
        start_page: str,
        target_page: str,
    ) -> SolverResponse: ...
