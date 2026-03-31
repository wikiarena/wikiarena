from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

from wikiarena.solver.backend import SolverCapabilities, SolverTargetSession
from wikiarena.solver.binary.mapped_graph import MappedBinarySolverGraph
from wikiarena.solver.binary.search import (
    search_all_shortest_paths_by_node_ids,
    search_shortest_path_by_node_ids,
)
from wikiarena.solver.models import SolverResponse

BinarySolverPathMode = Literal["single", "all_shortest"]


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
        path_mode: BinarySolverPathMode = "single",
    ):
        self.graph = graph
        self.path_mode = path_mode
        self.capabilities = SolverCapabilities(
            backend_id="binary_v1",
            snapshot_id=snapshot_id,
            supports_target_sessions=False,
            metadata={
                "path_mode": path_mode,
            },
        )

    @classmethod
    def from_file_path(
        cls,
        file_path: Path,
        *,
        snapshot_id: str | None = None,
        path_mode: BinarySolverPathMode = "single",
    ) -> "BinarySolverBackend":
        return cls(
            graph=MappedBinarySolverGraph(
                file_path=file_path,
            ),
            snapshot_id=snapshot_id,
            path_mode=path_mode,
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
        if self.path_mode == "all_shortest":
            return self._find_all_shortest_path(
                start_node_id=start_node_id,
                target_node_id=target_node_id,
                started_at=started_at,
            )

        return self._find_single_shortest_path(
            start_node_id=start_node_id,
            target_node_id=target_node_id,
            started_at=started_at,
        )

    def _find_all_shortest_path(
        self,
        *,
        start_node_id: int,
        target_node_id: int,
        started_at: float,
    ) -> SolverResponse:
        result = search_all_shortest_paths_by_node_ids(
            self.graph,
            start_node_id=start_node_id,
            target_node_id=target_node_id,
        )
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0

        if not result.path_node_id_paths:
            return SolverResponse(
                paths=[],
                path_length=-1,
                computation_time_ms=elapsed_ms,
                pages_visited=result.pages_visited,
                links_scanned=result.links_scanned,
            )

        return SolverResponse(
            paths=[
                [
                    self.graph.title_for_node_id(
                        node_id,
                    )
                    for node_id in path_node_ids
                ]
                for path_node_ids in result.path_node_id_paths
            ],
            path_length=len(result.path_node_id_paths[0]) - 1,
            computation_time_ms=elapsed_ms,
            pages_visited=result.pages_visited,
            links_scanned=result.links_scanned,
        )

    def _find_single_shortest_path(
        self,
        *,
        start_node_id: int,
        target_node_id: int,
        started_at: float,
    ) -> SolverResponse:
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
            path_length=len(result.path_node_ids) - 1,
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
