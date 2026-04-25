from __future__ import annotations

from datetime import datetime
from typing import Protocol

from wikiarena.protocol.enums import PathSource
from wikiarena.protocol.specs import SolverShortestPath, TaskSpec
from wikiarena.solver.models import SolverResponse


class LocalShortestPathOracle:
    """Adapter around a local shortest-path backend."""

    def __init__(
        self,
        solver_backend: "ShortestPathBackend",
        *,
        snapshot_id: str | None = None,
    ):
        self.solver_backend = solver_backend
        self.snapshot_id = snapshot_id

    async def get_solver_shortest_path(
        self,
        task: TaskSpec,
    ) -> SolverShortestPath | None:
        solver_response = await self.solver_backend.find_shortest_path(
            start_page=task.start_page_title,
            target_page=task.target_page_title,
        )
        if solver_response.path_length < 0 or not solver_response.paths:
            return None

        return SolverShortestPath(
            page_titles=solver_response.paths[0],
            computed_at=datetime.now(),
            solver_snapshot_id=self.snapshot_id,
            source=PathSource.LOCAL_GRAPH,
        )


class ShortestPathBackend(Protocol):
    async def find_shortest_path(
        self,
        start_page: str,
        target_page: str,
    ) -> SolverResponse: ...
