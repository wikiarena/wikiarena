from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from wikiarena.solver.models import PositionSolverFacts, SolverResponse


class SolverCapabilities(BaseModel):
    backend_id: str
    snapshot_id: str | None = None
    supports_target_sessions: bool = False
    metadata: dict[str, str] = Field(
        default_factory=dict,
    )


class SolverTargetSession(Protocol):
    target_page: str

    async def find_shortest_path(
        self,
        start_page: str,
    ) -> SolverResponse: ...

    async def get_shortest_path_length(
        self,
        start_page: str,
    ) -> int: ...

    async def get_position_solver_facts(
        self,
        start_page: str,
    ) -> PositionSolverFacts: ...


class SolverBackend(Protocol):
    capabilities: SolverCapabilities

    async def find_shortest_path(
        self,
        start_page: str,
        target_page: str,
    ) -> SolverResponse: ...

    async def create_target_session(
        self,
        target_page: str,
    ) -> SolverTargetSession: ...

    async def shutdown(
        self,
    ) -> None: ...
