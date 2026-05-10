"""WikiArena solver package.

The official production backend is `BinarySolverBackend`, powered by
a dated graph binary like `wikiarena_graph_enwiki_20260301.bin`.
"""

from .backend import SolverBackend, SolverCapabilities, SolverTargetSession
from .backends import BinarySolverBackend
from .benchmark import (
    SolverBenchmarkCase,
    SolverBenchmarkCaseResult,
    SolverBenchmarkResult,
    TimingSummary,
    benchmark_multiple_backends,
    benchmark_solver_backend,
)
from .case_sampling import SampledSolverCase, sample_random_cases_by_path_length
from .models import PositionSolverFacts, SolverRequest, SolverResponse
from .path_audit import (
    PathAuditCache,
    PathAuditResult,
    PathEdgeAuditResult,
    audit_solver_path_against_live_wikipedia,
)
from .runtime_benchmark import (
    RuntimeBenchmarkCase,
    RuntimeBenchmarkCaseResult,
    RuntimeTimingSummary,
    SameTargetBenchmarkGroup,
    SameTargetBenchmarkResult,
    SolverRuntimeBenchmarkResult,
    benchmark_solver_runtime,
)

__all__ = [
    "SolverBackend",
    "SolverCapabilities",
    "SolverTargetSession",
    "SolverBenchmarkCase",
    "SolverBenchmarkCaseResult",
    "SolverBenchmarkResult",
    "SolverRuntimeBenchmarkResult",
    "TimingSummary",
    "RuntimeBenchmarkCase",
    "RuntimeBenchmarkCaseResult",
    "RuntimeTimingSummary",
    "SameTargetBenchmarkCaseResult",
    "SameTargetBenchmarkGroup",
    "SameTargetBenchmarkResult",
    "SampledSolverCase",
    "benchmark_multiple_backends",
    "benchmark_solver_backend",
    "benchmark_solver_runtime",
    "sample_random_cases_by_path_length",
    "BinarySolverBackend",
    "SolverRequest",
    "SolverResponse",
    "PositionSolverFacts",
    "PathAuditCache",
    "PathAuditResult",
    "PathEdgeAuditResult",
    "audit_solver_path_against_live_wikipedia",
]
