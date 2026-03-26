"""Archived SQLite solver backend retained for migration audits only."""

from __future__ import annotations

from pathlib import Path

from wikiarena.solver.backend import (
    SolverCapabilities,
    SolverTargetSession,
)
from wikiarena.solver.solver import WikiTaskSolver
from wikiarena.solver.static_db import StaticSolverDB


class SQLiteSolverTargetSession:
    def __init__(
        self,
        *,
        backend: "SQLiteSolverBackend",
        target_page: str,
    ):
        self.backend = backend
        self.target_page = target_page

    async def find_shortest_path(
        self,
        start_page: str,
    ):
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


class SQLiteSolverBackend:
    def __init__(
        self,
        *,
        solver: WikiTaskSolver,
        snapshot_id: str | None = None,
    ):
        self.solver = solver
        self.capabilities = SolverCapabilities(
            backend_id="sqlite_v2",
            snapshot_id=snapshot_id,
            supports_target_sessions=True,
        )

    @classmethod
    def from_db_path(
        cls,
        db_path: str | Path,
        *,
        snapshot_id: str | None = None,
    ) -> "SQLiteSolverBackend":
        static_db = StaticSolverDB()
        static_db.db_path = Path(
            db_path,
        )
        static_db._initialize_variable_limit()
        static_db._initialized = True
        return cls(
            solver=WikiTaskSolver(db=static_db),
            snapshot_id=snapshot_id,
        )

    async def find_shortest_path(
        self,
        start_page: str,
        target_page: str,
    ):
        return await self.solver.find_shortest_path(
            start_page,
            target_page,
        )

    async def create_target_session(
        self,
        target_page: str,
    ) -> SolverTargetSession:
        return SQLiteSolverTargetSession(
            backend=self,
            target_page=target_page,
        )

    async def shutdown(
        self,
    ) -> None:
        await self.solver.shutdown()
