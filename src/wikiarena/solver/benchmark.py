from __future__ import annotations

import asyncio
import statistics
import time
from collections import defaultdict
from typing import Callable

from pydantic import BaseModel
from pydantic import Field

from wikiarena.solver.backend import SolverBackend
from wikiarena.solver.models import SolverResponse


class SolverBenchmarkCase(BaseModel):
    case_id: str
    start_page: str
    target_page: str


class TimingSummary(BaseModel):
    runs: int
    min_ms: float
    max_ms: float
    mean_ms: float
    median_ms: float

    @classmethod
    def from_measurements(
        cls,
        measurements_ms: list[float],
    ) -> "TimingSummary":
        if not measurements_ms:
            raise ValueError(
                "measurements_ms cannot be empty",
            )

        return cls(
            runs=len(measurements_ms),
            min_ms=min(measurements_ms),
            max_ms=max(measurements_ms),
            mean_ms=statistics.mean(measurements_ms),
            median_ms=statistics.median(measurements_ms),
        )


class SolverBenchmarkCaseResult(BaseModel):
    case: SolverBenchmarkCase
    cold_start_ms: float
    warm_query_ms: TimingSummary
    session_query_ms: TimingSummary | None = None
    path_length: int
    paths_found: int
    first_path: list[str] = Field(
        default_factory=list,
    )


class SolverBenchmarkResult(BaseModel):
    backend_id: str
    snapshot_id: str | None = None
    supports_target_sessions: bool = False
    case_results: list[SolverBenchmarkCaseResult] = Field(
        default_factory=list,
    )


async def benchmark_solver_backend(
    backend_factory: Callable[[], SolverBackend],
    cases: list[SolverBenchmarkCase],
    *,
    warm_repeats: int = 3,
) -> SolverBenchmarkResult:
    if not cases:
        raise ValueError(
            "cases cannot be empty",
        )

    probe_backend = backend_factory()
    try:
        backend_result = SolverBenchmarkResult(
            backend_id=probe_backend.capabilities.backend_id,
            snapshot_id=probe_backend.capabilities.snapshot_id,
            supports_target_sessions=probe_backend.capabilities.supports_target_sessions,
        )
    finally:
        await probe_backend.shutdown()

    cold_results = {}
    warm_results = {}
    response_snapshots = {}

    for case in cases:
        cold_ms, cold_response = await _measure_single_query_with_fresh_backend(
            backend_factory,
            case,
        )
        cold_results[case.case_id] = cold_ms
        response_snapshots[case.case_id] = cold_response

        warm_measurements = await _measure_warm_queries(
            backend_factory,
            case,
            repeats=warm_repeats,
        )
        warm_results[case.case_id] = TimingSummary.from_measurements(
            warm_measurements,
        )

    session_results = await _measure_target_sessions(
        backend_factory,
        cases,
    )

    for case in cases:
        response = response_snapshots[case.case_id]
        backend_result.case_results.append(
            SolverBenchmarkCaseResult(
                case=case,
                cold_start_ms=cold_results[case.case_id],
                warm_query_ms=warm_results[case.case_id],
                session_query_ms=session_results.get(case.case_id),
                path_length=response.path_length,
                paths_found=len(response.paths),
                first_path=response.paths[0] if response.paths else [],
            ),
        )

    return backend_result


async def _measure_single_query_with_fresh_backend(
    backend_factory: Callable[[], SolverBackend],
    case: SolverBenchmarkCase,
) -> tuple[float, SolverResponse]:
    backend = backend_factory()
    try:
        started_at = time.perf_counter()
        response = await backend.find_shortest_path(
            case.start_page,
            case.target_page,
        )
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        return elapsed_ms, response
    finally:
        await backend.shutdown()


async def _measure_warm_queries(
    backend_factory: Callable[[], SolverBackend],
    case: SolverBenchmarkCase,
    *,
    repeats: int,
) -> list[float]:
    backend = backend_factory()
    try:
        await backend.find_shortest_path(
            case.start_page,
            case.target_page,
        )

        measurements_ms: list[float] = []
        for _ in range(repeats):
            started_at = time.perf_counter()
            await backend.find_shortest_path(
                case.start_page,
                case.target_page,
            )
            measurements_ms.append(
                (time.perf_counter() - started_at) * 1000.0,
            )

        return measurements_ms
    finally:
        await backend.shutdown()


async def _measure_target_sessions(
    backend_factory: Callable[[], SolverBackend],
    cases: list[SolverBenchmarkCase],
) -> dict[str, TimingSummary]:
    backend = backend_factory()
    try:
        if not backend.capabilities.supports_target_sessions:
            return {}

        grouped_cases: dict[str, list[SolverBenchmarkCase]] = defaultdict(list)
        for case in cases:
            grouped_cases[case.target_page].append(case)

        session_summaries: dict[str, TimingSummary] = {}
        for target_page, target_cases in grouped_cases.items():
            session = await backend.create_target_session(
                target_page,
            )
            measurements_by_case: dict[str, list[float]] = defaultdict(list)
            for case in target_cases:
                started_at = time.perf_counter()
                await session.find_shortest_path(
                    case.start_page,
                )
                measurements_by_case[case.case_id].append(
                    (time.perf_counter() - started_at) * 1000.0,
                )

            for case_id, measurements in measurements_by_case.items():
                session_summaries[case_id] = TimingSummary.from_measurements(
                    measurements,
                )

        return session_summaries
    finally:
        await backend.shutdown()


async def benchmark_multiple_backends(
    backend_factories: dict[str, Callable[[], SolverBackend]],
    cases: list[SolverBenchmarkCase],
    *,
    warm_repeats: int = 3,
) -> list[SolverBenchmarkResult]:
    results: list[SolverBenchmarkResult] = []
    for _, backend_factory in backend_factories.items():
        results.append(
            await benchmark_solver_backend(
                backend_factory,
                cases,
                warm_repeats=warm_repeats,
            ),
        )
    return results
