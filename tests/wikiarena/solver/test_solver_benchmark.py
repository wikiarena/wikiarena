from __future__ import annotations

import asyncio
from typing import Callable

import pytest

from wikiarena.solver import SolverBenchmarkCase
from wikiarena.solver import benchmark_multiple_backends
from wikiarena.solver import benchmark_solver_backend
from wikiarena.solver.backend import SolverCapabilities
from wikiarena.solver.models import SolverResponse


class FakeTargetSession:
    def __init__(
        self,
        *,
        backend: "FakeSolverBackend",
        target_page: str,
    ):
        self.backend = backend
        self.target_page = target_page

    async def find_shortest_path(
        self,
        start_page: str,
    ) -> SolverResponse:
        await asyncio.sleep(0)
        self.backend.session_queries.append((start_page, self.target_page))
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


class FakeSolverBackend:
    def __init__(
        self,
        *,
        backend_id: str,
        supports_target_sessions: bool,
        factory_state: dict[str, int],
    ):
        self.capabilities = SolverCapabilities(
            backend_id=backend_id,
            supports_target_sessions=supports_target_sessions,
        )
        self.factory_state = factory_state
        self.find_calls: list[tuple[str, str]] = []
        self.session_queries: list[tuple[str, str]] = []

    async def find_shortest_path(
        self,
        start_page: str,
        target_page: str,
    ) -> SolverResponse:
        await asyncio.sleep(0)
        self.find_calls.append((start_page, target_page))
        return SolverResponse(
            paths=[[start_page, target_page]],
            path_length=1,
            computation_time_ms=1.0,
        )

    async def create_target_session(
        self,
        target_page: str,
    ) -> FakeTargetSession:
        self.factory_state["session_count"] += 1
        return FakeTargetSession(
            backend=self,
            target_page=target_page,
        )

    async def shutdown(
        self,
    ) -> None:
        return None


def build_backend_factory(
    *,
    backend_id: str,
    supports_target_sessions: bool,
) -> tuple[dict[str, int], Callable[[], FakeSolverBackend]]:
    factory_state = {
        "instances": 0,
        "session_count": 0,
    }

    def factory() -> FakeSolverBackend:
        factory_state["instances"] += 1
        return FakeSolverBackend(
            backend_id=backend_id,
            supports_target_sessions=supports_target_sessions,
            factory_state=factory_state,
        )

    return factory_state, factory


@pytest.mark.asyncio
async def test_benchmark_solver_backend_measures_cases_and_sessions() -> None:
    factory_state, factory = build_backend_factory(
        backend_id="fake",
        supports_target_sessions=True,
    )
    cases = [
        SolverBenchmarkCase(
            case_id="case_1",
            start_page="Apple",
            target_page="Fruit",
        ),
        SolverBenchmarkCase(
            case_id="case_2",
            start_page="Pear",
            target_page="Fruit",
        ),
    ]

    result = await benchmark_solver_backend(
        factory,
        cases,
        warm_repeats=2,
    )

    assert result.backend_id == "fake"
    assert len(result.case_results) == 2
    assert all(case_result.path_length == 1 for case_result in result.case_results)
    assert all(
        case_result.warm_query_ms.runs == 2 for case_result in result.case_results
    )
    assert all(
        case_result.session_query_ms is not None for case_result in result.case_results
    )
    assert factory_state["instances"] == 6
    assert factory_state["session_count"] == 1


@pytest.mark.asyncio
async def test_benchmark_multiple_backends_runs_each_factory() -> None:
    _, factory_a = build_backend_factory(
        backend_id="a",
        supports_target_sessions=True,
    )
    _, factory_b = build_backend_factory(
        backend_id="b",
        supports_target_sessions=False,
    )

    results = await benchmark_multiple_backends(
        {
            "a": factory_a,
            "b": factory_b,
        },
        [
            SolverBenchmarkCase(
                case_id="case_1",
                start_page="Apple",
                target_page="Fruit",
            ),
        ],
        warm_repeats=1,
    )

    assert [result.backend_id for result in results] == ["a", "b"]
