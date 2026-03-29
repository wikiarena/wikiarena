from __future__ import annotations

import time
from pathlib import Path

from wikiarena.solver.backend import SolverCapabilities, SolverTargetSession
from wikiarena.solver.binary.mapped_graph import MappedBinarySolverGraph
from wikiarena.solver.binary.search import search_shortest_path_by_node_ids
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
        start_node_id = self.graph.find_node_id(
            start_page,
        )
        if start_node_id is None:
            raise ValueError(
                f"unknown start title: {start_page}",
            )

        target_node_id = self.graph.find_node_id(
            target_page,
        )
        if target_node_id is None:
            raise ValueError(
                f"unknown target title: {target_page}",
            )

        started_at = time.perf_counter()
        result = search_shortest_path_by_node_ids(
            self.graph,
            start_node_id=start_node_id,
            target_node_id=target_node_id,
        )
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0

        if result.path_node_ids is None:
            return SolverResponse(
                paths=[],
                path_length=-1,
                computation_time_ms=elapsed_ms,
                pages_visited=result.pages_visited,
                links_scanned=result.links_scanned,
            )

        path_titles = [
            self.graph.title_for_node_id(
                node_id,
            )
            for node_id in result.path_node_ids
        ]

        return SolverResponse(
            paths=[
                path_titles,
            ],
            path_length=result.path_length,
            computation_time_ms=elapsed_ms,
            pages_visited=result.pages_visited,
            links_scanned=result.links_scanned,
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
