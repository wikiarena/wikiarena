from __future__ import annotations

import statistics
import time
from typing import Callable

from pydantic import BaseModel
from pydantic import Field

from wikiarena.solver.backend import SolverBackend
from wikiarena.solver.models import SolverResponse


class RuntimeBenchmarkCase(BaseModel):
    case_id: str
    start_page: str
    target_page: str


class SameTargetBenchmarkGroup(BaseModel):
    group_id: str
    target_page: str
    start_pages: list[str] = Field(
        default_factory=list,
    )


class RuntimeTiming(BaseModel):
    elapsed_ms: float


class RuntimeTimingSummary(BaseModel):
    runs: int
    min_ms: float
    max_ms: float
    mean_ms: float
    median_ms: float

    @classmethod
    def from_timings(
        cls,
        timings_ms: list[float],
    ) -> "RuntimeTimingSummary":
        if not timings_ms:
            raise ValueError(
                "timings_ms cannot be empty",
            )
        return cls(
            runs=len(timings_ms),
            min_ms=min(timings_ms),
            max_ms=max(timings_ms),
            mean_ms=statistics.mean(timings_ms),
            median_ms=statistics.median(timings_ms),
        )


class RuntimeBenchmarkCaseResult(BaseModel):
    case: RuntimeBenchmarkCase
    elapsed_ms: float
    path_length: int
    paths_found: int
    first_path: list[str] = Field(
        default_factory=list,
    )


class SameTargetBenchmarkCaseResult(BaseModel):
    start_page: str
    elapsed_ms: float
    path_length: int
    first_path: list[str] = Field(
        default_factory=list,
    )


class SameTargetBenchmarkResult(BaseModel):
    group: SameTargetBenchmarkGroup
    session_created: bool
    case_results: list[SameTargetBenchmarkCaseResult] = Field(
        default_factory=list,
    )
    first_query_ms: float | None = None
    subsequent_query_ms: RuntimeTimingSummary | None = None


class SolverRuntimeBenchmarkResult(BaseModel):
    backend_id: str
    snapshot_id: str | None = None
    supports_target_sessions: bool = False
    startup_probe_ms: float | None = None
    startup_probe_case: RuntimeBenchmarkCase | None = None
    case_results: list[RuntimeBenchmarkCaseResult] = Field(
        default_factory=list,
    )
    same_target_results: list[SameTargetBenchmarkResult] = Field(
        default_factory=list,
    )


async def benchmark_solver_runtime(
    backend_factory: Callable[[], SolverBackend],
    *,
    cases: list[RuntimeBenchmarkCase],
    same_target_groups: list[SameTargetBenchmarkGroup] | None = None,
    startup_probe_case: RuntimeBenchmarkCase | None = None,
) -> SolverRuntimeBenchmarkResult:
    backend = backend_factory()
    try:
        result = SolverRuntimeBenchmarkResult(
            backend_id=backend.capabilities.backend_id,
            snapshot_id=backend.capabilities.snapshot_id,
            supports_target_sessions=backend.capabilities.supports_target_sessions,
        )

        if startup_probe_case is not None:
            startup_elapsed_ms, _ = await _timed_query(
                backend,
                startup_probe_case.start_page,
                startup_probe_case.target_page,
            )
            result.startup_probe_ms = startup_elapsed_ms
            result.startup_probe_case = startup_probe_case

        for case in cases:
            elapsed_ms, response = await _timed_query(
                backend,
                case.start_page,
                case.target_page,
            )
            result.case_results.append(
                RuntimeBenchmarkCaseResult(
                    case=case,
                    elapsed_ms=elapsed_ms,
                    path_length=response.path_length,
                    paths_found=len(response.paths),
                    first_path=response.paths[0] if response.paths else [],
                ),
            )

        for group in same_target_groups or []:
            result.same_target_results.append(
                await _benchmark_same_target_group(
                    backend,
                    group,
                ),
            )

        return result
    finally:
        await backend.shutdown()


async def _benchmark_same_target_group(
    backend: SolverBackend,
    group: SameTargetBenchmarkGroup,
) -> SameTargetBenchmarkResult:
    case_results: list[SameTargetBenchmarkCaseResult] = []
    timings_ms: list[float] = []

    if backend.capabilities.supports_target_sessions:
        session = await backend.create_target_session(
            group.target_page,
        )
        for start_page in group.start_pages:
            started_at = time.perf_counter()
            response = await session.find_shortest_path(
                start_page,
            )
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            timings_ms.append(elapsed_ms)
            case_results.append(
                SameTargetBenchmarkCaseResult(
                    start_page=start_page,
                    elapsed_ms=elapsed_ms,
                    path_length=response.path_length,
                    first_path=response.paths[0] if response.paths else [],
                ),
            )

        return SameTargetBenchmarkResult(
            group=group,
            session_created=True,
            case_results=case_results,
            first_query_ms=timings_ms[0] if timings_ms else None,
            subsequent_query_ms=(
                RuntimeTimingSummary.from_timings(timings_ms[1:])
                if len(timings_ms) > 1
                else None
            ),
        )

    for start_page in group.start_pages:
        elapsed_ms, response = await _timed_query(
            backend,
            start_page,
            group.target_page,
        )
        timings_ms.append(elapsed_ms)
        case_results.append(
            SameTargetBenchmarkCaseResult(
                start_page=start_page,
                elapsed_ms=elapsed_ms,
                path_length=response.path_length,
                first_path=response.paths[0] if response.paths else [],
            ),
        )

    return SameTargetBenchmarkResult(
        group=group,
        session_created=False,
        case_results=case_results,
        first_query_ms=timings_ms[0] if timings_ms else None,
        subsequent_query_ms=(
            RuntimeTimingSummary.from_timings(timings_ms[1:])
            if len(timings_ms) > 1
            else None
        ),
    )


async def _timed_query(
    backend: SolverBackend,
    start_page: str,
    target_page: str,
) -> tuple[float, SolverResponse]:
    started_at = time.perf_counter()
    response = await backend.find_shortest_path(
        start_page,
        target_page,
    )
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    return elapsed_ms, response
