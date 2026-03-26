from __future__ import annotations

import time
from pathlib import Path

from wikiarena.solver.backend import SolverCapabilities, SolverTargetSession
from wikiarena.solver.binary.mapped_graph import MappedBinarySolverGraph
from wikiarena.solver.binary.search import find_shortest_path_by_titles
from wikiarena.solver.models import SolverResponse


class BinarySolverTargetSession:
    def __init__(
        self,
        *,
        backend: "BinarySolverBackend",
        target_page: str,
    ):
        self.backend = backend
        self.target_page = target_page

    async def find_shortest_path(
        self,
        start_page: str,
    ) -> SolverResponse:
        return await self.backend.find_shortest_path(
            start_page,
            self.target_page,
        )

    async def get_shortest_path_length(
        self,
        start_page: str,
    ) -> int:
        response = await self.find_shortest_path(
            start_page,
        )
        return response.path_length


class BinarySolverBackend:
    def __init__(
        self,
        *,
        graph: MappedBinarySolverGraph,
        snapshot_id: str | None = None,
    ):
        self.graph = graph
        self.capabilities = SolverCapabilities(
            backend_id="binary_v1",
            snapshot_id=snapshot_id,
            supports_target_sessions=False,
        )

    @classmethod
    def from_file_path(
        cls,
        file_path: Path,
        *,
        snapshot_id: str | None = None,
    ) -> "BinarySolverBackend":
        return cls(
            graph=MappedBinarySolverGraph(
                file_path=file_path,
            ),
            snapshot_id=snapshot_id,
        )

    async def find_shortest_path(
        self,
        start_page: str,
        target_page: str,
    ) -> SolverResponse:
        started_at = time.perf_counter()
        result = find_shortest_path_by_titles(
            self.graph,
            start_title=start_page,
            target_title=target_page,
        )
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0

        if result is None:
            return SolverResponse(
                paths=[],
                path_length=-1,
                computation_time_ms=elapsed_ms,
            )

        return SolverResponse(
            paths=[
                list(
                    result.path_titles,
                ),
            ],
            path_length=result.path_length,
            computation_time_ms=elapsed_ms,
        )

    async def create_target_session(
        self,
        target_page: str,
    ) -> SolverTargetSession:
        return BinarySolverTargetSession(
            backend=self,
            target_page=target_page,
        )

    async def shutdown(
        self,
    ) -> None:
        self.graph.close()
