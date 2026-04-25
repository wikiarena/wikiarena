from __future__ import annotations

import asyncio

import pytest

from wikiarena.solver.backend import SolverCapabilities
from wikiarena.solver.models import SolverResponse
from wikiarena.solver.runtime_benchmark import RuntimeBenchmarkCase
from wikiarena.solver.runtime_benchmark import SameTargetBenchmarkGroup
from wikiarena.solver.runtime_benchmark import benchmark_solver_runtime


class FakeTargetSession:
    def __init__(
        self,
        *,
        target_page: str,
        backend: "FakeRuntimeBackend",
    ):
        self.target_page = target_page
        self.backend = backend

    async def find_shortest_path(
        self,
        start_page: str,
    ) -> SolverResponse:
        await asyncio.sleep(0)
        self.backend.session_calls.append((start_page, self.target_page))
        return SolverResponse(
            paths=[[start_page, self.target_page]],
            path_length=1,
            computation_time_ms=1.0,
        )

    async def get_shortest_path_length(
        self,
        start_page: str,
    ) -> int:
        return 1


class FakeRuntimeBackend:
    def __init__(
        self,
        *,
        backend_id: str,
        supports_target_sessions: bool,
    ):
        self.capabilities = SolverCapabilities(
            backend_id=backend_id,
            supports_target_sessions=supports_target_sessions,
        )
        self.calls: list[tuple[str, str]] = []
        self.session_calls: list[tuple[str, str]] = []

    async def find_shortest_path(
        self,
        start_page: str,
        target_page: str,
    ) -> SolverResponse:
        await asyncio.sleep(0)
        self.calls.append((start_page, target_page))
        return SolverResponse(
            paths=[[start_page, target_page]],
            path_length=1,
            computation_time_ms=1.0,
        )

    async def create_target_session(
        self,
        target_page: str,
    ) -> FakeTargetSession:
        return FakeTargetSession(
            target_page=target_page,
            backend=self,
        )

    async def shutdown(self) -> None:
        return None


@pytest.mark.asyncio
async def test_benchmark_solver_runtime_keeps_backend_running_and_measures_groups() -> (
    None
):
    backend = FakeRuntimeBackend(
        backend_id="fake_runtime",
        supports_target_sessions=True,
    )

    result = await benchmark_solver_runtime(
        lambda: backend,
        cases=[
            RuntimeBenchmarkCase(
                case_id="case_1",
                start_page="Apple",
                target_page="Fruit",
            ),
        ],
        same_target_groups=[
            SameTargetBenchmarkGroup(
                group_id="fruit_group",
                target_page="Fruit",
                start_pages=["Apple", "Pear"],
            ),
        ],
        startup_probe_case=RuntimeBenchmarkCase(
            case_id="startup_probe",
            start_page="Start",
            target_page="Target",
        ),
    )

    assert result.backend_id == "fake_runtime"
    assert result.startup_probe_ms is not None
    assert len(result.case_results) == 1
    assert len(result.same_target_results) == 1
    assert result.same_target_results[0].session_created is True
    assert result.same_target_results[0].subsequent_query_ms is not None
    assert backend.calls[0] == ("Start", "Target")
    assert backend.session_calls == [("Apple", "Fruit"), ("Pear", "Fruit")]


@pytest.mark.asyncio
async def test_benchmark_solver_runtime_without_target_sessions_still_runs_groups() -> (
    None
):
    backend = FakeRuntimeBackend(
        backend_id="fake_no_session",
        supports_target_sessions=False,
    )

    result = await benchmark_solver_runtime(
        lambda: backend,
        cases=[],
        same_target_groups=[
            SameTargetBenchmarkGroup(
                group_id="fruit_group",
                target_page="Fruit",
                start_pages=["Apple", "Pear"],
            ),
        ],
    )

    assert result.same_target_results[0].session_created is False
    assert result.same_target_results[0].subsequent_query_ms is not None
    assert backend.calls == [("Apple", "Fruit"), ("Pear", "Fruit")]
