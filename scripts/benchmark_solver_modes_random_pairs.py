"""Benchmark binary solver modes on deterministic random graph pairs."""

from __future__ import annotations

import argparse
import atexit
import heapq
import json
import math
import multiprocessing
import random
import re
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median
from typing import Literal

from wikiarena.analysis.taskset_candidates import DEFAULT_EXCLUDED_TITLE_PATTERNS
from wikiarena.solver.binary import (
    MappedBinarySolverGraph,
    search_all_shortest_paths_by_node_ids,
    search_shortest_path_by_node_ids,
)
from wikiarena.wiki_runtime import (
    infer_snapshot_id_from_graph_path,
    resolve_graph_file_path,
)

SolverPathMode = Literal["single", "all_shortest"]

DEFAULT_OUTPUT_ROOT = Path("artifacts/solver_mode_benchmarks")
DEFAULT_TOP_CASES = 25

_WORKER_GRAPH: MappedBinarySolverGraph | None = None


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    start_node_id: int
    target_node_id: int
    start_title: str
    target_title: str


@dataclass(frozen=True)
class SolverMeasurement:
    case_id: str
    path_mode: SolverPathMode
    start_node_id: int
    target_node_id: int
    start_title: str
    target_title: str
    status: str
    path_length: int | None
    paths_found: int
    pages_visited: int
    links_scanned: int
    path_node_total: int
    search_ms: float
    title_materialization_ms: float | None
    total_ms: float
    error_type: str | None
    error_message: str | None


def main() -> None:
    args = parse_args()
    resolved_graph_path = resolve_graph_file_path(
        args.graph_path,
    )
    snapshot_id = infer_snapshot_id_from_graph_path(
        resolved_graph_path,
    )
    run_started_at = datetime.now(
        UTC,
    )
    run_id = build_run_id(
        path_mode=args.path_mode,
        seed=args.seed,
        case_count=args.case_count,
        worker_count=args.workers,
        started_at=run_started_at,
    )
    output_dir = (args.output_root / run_id).resolve()
    output_dir.mkdir(
        parents=True,
        exist_ok=False,
    )
    results_path = output_dir / "results.jsonl"
    summary_path = output_dir / "summary.json"

    print(
        f"Sampling {args.case_count} cases from {resolved_graph_path} with seed {args.seed}",
    )
    sampling_started_at = time.perf_counter()
    sampling_result = sample_benchmark_cases(
        graph_path=resolved_graph_path,
        case_count=args.case_count,
        seed=args.seed,
        exclude_title_patterns=DEFAULT_EXCLUDED_TITLE_PATTERNS
        if args.exclude_special_titles
        else (),
        progress_interval=max(
            1_000,
            args.case_count // 20,
        ),
    )
    sampling_elapsed_ms = (time.perf_counter() - sampling_started_at) * 1000.0
    print(
        f"Sampled {len(sampling_result.cases)} cases in {sampling_elapsed_ms / 1000.0:.1f}s",
    )

    run_started_perf = time.perf_counter()
    measurement_state = MeasurementAggregationState(
        top_case_limit=args.top_cases,
    )

    process_context = multiprocessing.get_context(
        "spawn",
    )
    batches = list(
        chunk_cases(
            sampling_result.cases,
            chunk_size=args.chunk_size,
        ),
    )
    print(
        f"Running {args.path_mode} benchmark across {len(batches)} batches with {args.workers} workers",
    )
    with results_path.open(
        "w",
        encoding="utf-8",
    ) as results_file_handle:
        with ProcessPoolExecutor(
            max_workers=args.workers,
            mp_context=process_context,
            initializer=initialize_worker,
            initargs=(resolved_graph_path,),
        ) as executor:
            submitted_futures = [
                executor.submit(
                    measure_case_batch,
                    batch,
                    args.path_mode,
                    args.materialize_titles,
                )
                for batch in batches
            ]

            completed_cases = 0
            progress_interval = max(
                args.chunk_size,
                min(
                    5_000,
                    max(
                        1_000,
                        args.case_count // 20,
                    ),
                ),
            )
            next_progress_count = progress_interval
            for future in as_completed(
                submitted_futures,
            ):
                batch_measurements = future.result()
                for measurement in batch_measurements:
                    measurement_state.add(
                        measurement,
                    )
                    results_file_handle.write(
                        json.dumps(
                            asdict(
                                measurement,
                            ),
                            ensure_ascii=True,
                        ),
                    )
                    results_file_handle.write(
                        "\n",
                    )
                completed_cases += len(
                    batch_measurements,
                )
                if completed_cases >= next_progress_count:
                    elapsed_seconds = time.perf_counter() - run_started_perf
                    throughput = (
                        completed_cases / elapsed_seconds if elapsed_seconds else 0.0
                    )
                    print(
                        f"Completed {completed_cases}/{args.case_count} solves in {elapsed_seconds:.1f}s ({throughput:.1f} solves/s)",
                    )
                    next_progress_count += progress_interval

    total_run_elapsed_ms = (time.perf_counter() - run_started_perf) * 1000.0
    run_ended_at = datetime.now(
        UTC,
    )
    summary_payload = build_summary_payload(
        graph_path=resolved_graph_path,
        snapshot_id=snapshot_id,
        path_mode=args.path_mode,
        materialize_titles=args.materialize_titles,
        worker_count=args.workers,
        chunk_size=args.chunk_size,
        case_count=args.case_count,
        seed=args.seed,
        run_id=run_id,
        run_started_at=run_started_at,
        run_ended_at=run_ended_at,
        total_run_elapsed_ms=total_run_elapsed_ms,
        sampling_result=sampling_result,
        sampling_elapsed_ms=sampling_elapsed_ms,
        measurement_state=measurement_state,
        results_path=results_path,
    )
    summary_path.write_text(
        json.dumps(
            summary_payload,
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        f"Wrote results to {results_path}",
    )
    print(
        f"Wrote summary to {summary_path}",
    )
    print(
        f"Successful solves: {measurement_state.status_counts.get('ok', 0)} / {args.case_count}",
    )
    print(
        f"Wall time: {total_run_elapsed_ms / 1000.0:.1f}s",
    )


@dataclass(frozen=True)
class SamplingResult:
    cases: list[BenchmarkCase]
    attempts: int


class MeasurementAggregationState:
    def __init__(
        self,
        *,
        top_case_limit: int,
    ) -> None:
        self.top_case_limit = top_case_limit
        self.status_counts: dict[str, int] = {}
        self.found_path_count = 0
        self.error_count = 0
        self.search_ms_values: list[float] = []
        self.title_materialization_ms_values: list[float] = []
        self.total_ms_values: list[float] = []
        self.pages_visited_values: list[int] = []
        self.links_scanned_values: list[int] = []
        self.paths_found_values: list[int] = []
        self.path_node_total_values: list[int] = []
        self.path_length_values: list[int] = []
        self.path_length_histogram: dict[str, int] = {}
        self.paths_found_bucket_histogram: dict[str, int] = {}
        self._slowest_cases_heap: list[tuple[float, int, dict[str, object]]] = []
        self._slowest_case_serial = 0

    def add(
        self,
        measurement: SolverMeasurement,
    ) -> None:
        self.status_counts[measurement.status] = (
            self.status_counts.get(
                measurement.status,
                0,
            )
            + 1
        )
        if measurement.status != "ok":
            self.error_count += 1
            return

        self.search_ms_values.append(
            measurement.search_ms,
        )
        if measurement.title_materialization_ms is not None:
            self.title_materialization_ms_values.append(
                measurement.title_materialization_ms,
            )
        self.total_ms_values.append(
            measurement.total_ms,
        )
        self.pages_visited_values.append(
            measurement.pages_visited,
        )
        self.links_scanned_values.append(
            measurement.links_scanned,
        )
        self.paths_found_values.append(
            measurement.paths_found,
        )
        self.path_node_total_values.append(
            measurement.path_node_total,
        )
        if measurement.path_length is not None:
            self.found_path_count += 1
            self.path_length_values.append(
                measurement.path_length,
            )
            path_length_key = str(
                measurement.path_length,
            )
            self.path_length_histogram[path_length_key] = (
                self.path_length_histogram.get(
                    path_length_key,
                    0,
                )
                + 1
            )

        path_bucket_label = bucket_paths_found(
            measurement.paths_found,
        )
        self.paths_found_bucket_histogram[path_bucket_label] = (
            self.paths_found_bucket_histogram.get(
                path_bucket_label,
                0,
            )
            + 1
        )

        slow_case_payload = {
            "case_id": measurement.case_id,
            "start_title": measurement.start_title,
            "target_title": measurement.target_title,
            "path_length": measurement.path_length,
            "paths_found": measurement.paths_found,
            "pages_visited": measurement.pages_visited,
            "links_scanned": measurement.links_scanned,
            "search_ms": measurement.search_ms,
            "title_materialization_ms": measurement.title_materialization_ms,
            "total_ms": measurement.total_ms,
        }
        heap_entry = (
            measurement.total_ms,
            self._slowest_case_serial,
            slow_case_payload,
        )
        self._slowest_case_serial += 1
        if (
            len(
                self._slowest_cases_heap,
            )
            < self.top_case_limit
        ):
            heapq.heappush(
                self._slowest_cases_heap,
                heap_entry,
            )
            return
        if heap_entry[0] > self._slowest_cases_heap[0][0]:
            heapq.heapreplace(
                self._slowest_cases_heap,
                heap_entry,
            )

    def slowest_cases_descending(
        self,
    ) -> list[dict[str, object]]:
        ranked_entries = sorted(
            self._slowest_cases_heap,
            reverse=True,
        )
        return [entry[2] for entry in ranked_entries]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark binary solver modes on deterministic random graph pairs.",
    )
    parser.add_argument(
        "--graph-path",
        type=Path,
        default=None,
        help=(
            "Path to the dated graph binary. Defaults to WIKIARENA_GRAPH_PATH "
            "or the latest installed graph."
        ),
    )
    parser.add_argument(
        "--path-mode",
        choices=("single", "all_shortest"),
        default="all_shortest",
        help="Solver mode to benchmark.",
    )
    parser.add_argument(
        "--case-count",
        type=int,
        default=100_000,
        help="Number of random pairs to benchmark.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260301,
        help="Deterministic random seed for case sampling.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of worker processes.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=250,
        help="Number of solves per worker batch.",
    )
    parser.add_argument(
        "--top-cases",
        type=int,
        default=DEFAULT_TOP_CASES,
        help="Number of slowest cases to retain in the summary.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory where benchmark artifacts will be written.",
    )
    parser.add_argument(
        "--materialize-titles",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Measure title materialization after search.",
    )
    parser.add_argument(
        "--exclude-special-titles",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Exclude list, outline, index, year, and disambiguation titles during sampling.",
    )
    parsed_args = parser.parse_args()
    if parsed_args.case_count < 1:
        raise ValueError(
            "case_count must be at least 1",
        )
    if parsed_args.workers < 1:
        raise ValueError(
            "workers must be at least 1",
        )
    if parsed_args.chunk_size < 1:
        raise ValueError(
            "chunk_size must be at least 1",
        )
    if parsed_args.top_cases < 1:
        raise ValueError(
            "top_cases must be at least 1",
        )
    return parsed_args


def build_run_id(
    *,
    path_mode: SolverPathMode,
    seed: int,
    case_count: int,
    worker_count: int,
    started_at: datetime,
) -> str:
    return (
        f"{path_mode}_{case_count}_seed{seed}_workers{worker_count}_"
        f"{started_at.strftime('%Y%m%dT%H%M%SZ')}"
    )


def sample_benchmark_cases(
    *,
    graph_path: Path,
    case_count: int,
    seed: int,
    exclude_title_patterns: tuple[str, ...],
    progress_interval: int,
) -> SamplingResult:
    rng = random.Random(
        seed,
    )
    compiled_patterns = [
        re.compile(
            pattern,
            re.IGNORECASE,
        )
        for pattern in exclude_title_patterns
    ]
    seen_pairs: set[tuple[int, int]] = set()
    sampled_cases: list[BenchmarkCase] = []
    attempts = 0

    with MappedBinarySolverGraph(
        file_path=graph_path,
    ) as graph:
        while (
            len(
                sampled_cases,
            )
            < case_count
        ):
            attempts += 1
            start_node_id = rng.randrange(
                graph.node_count,
            )
            if (
                graph.outgoing_degree(
                    start_node_id,
                )
                == 0
            ):
                continue

            target_node_id = rng.randrange(
                graph.node_count,
            )
            if start_node_id == target_node_id:
                continue
            if (
                graph.incoming_degree(
                    target_node_id,
                )
                == 0
            ):
                continue

            node_pair = (
                start_node_id,
                target_node_id,
            )
            if node_pair in seen_pairs:
                continue

            start_title = graph.title_for_node_id(
                start_node_id,
            )
            target_title = graph.title_for_node_id(
                target_node_id,
            )
            if compiled_patterns and (
                title_is_excluded(
                    start_title,
                    compiled_patterns,
                )
                or title_is_excluded(
                    target_title,
                    compiled_patterns,
                )
            ):
                continue

            seen_pairs.add(
                node_pair,
            )
            sampled_cases.append(
                BenchmarkCase(
                    case_id=f"case_{len(sampled_cases) + 1:06d}",
                    start_node_id=start_node_id,
                    target_node_id=target_node_id,
                    start_title=start_title,
                    target_title=target_title,
                ),
            )
            if (
                len(
                    sampled_cases,
                )
                % progress_interval
                == 0
            ):
                print(
                    f"Sampled {len(sampled_cases)}/{case_count} cases after {attempts} attempts",
                )

    return SamplingResult(
        cases=sampled_cases,
        attempts=attempts,
    )


def title_is_excluded(
    title: str,
    compiled_patterns: list[re.Pattern[str]],
) -> bool:
    return any(
        pattern.search(
            title,
        )
        for pattern in compiled_patterns
    )


def chunk_cases(
    cases: list[BenchmarkCase],
    *,
    chunk_size: int,
) -> list[list[BenchmarkCase]]:
    return [
        cases[start_index : start_index + chunk_size]
        for start_index in range(
            0,
            len(cases),
            chunk_size,
        )
    ]


def initialize_worker(
    graph_path: Path,
) -> None:
    global _WORKER_GRAPH
    if _WORKER_GRAPH is not None:
        return
    _WORKER_GRAPH = MappedBinarySolverGraph(
        file_path=graph_path,
    )
    atexit.register(
        close_worker_graph,
    )


def close_worker_graph() -> None:
    global _WORKER_GRAPH
    if _WORKER_GRAPH is None:
        return
    _WORKER_GRAPH.close()
    _WORKER_GRAPH = None


def measure_case_batch(
    batch: list[BenchmarkCase],
    path_mode: SolverPathMode,
    materialize_titles: bool,
) -> list[SolverMeasurement]:
    graph = require_worker_graph()
    return [
        measure_single_case(
            graph=graph,
            case=case,
            path_mode=path_mode,
            materialize_titles=materialize_titles,
        )
        for case in batch
    ]


def require_worker_graph() -> MappedBinarySolverGraph:
    if _WORKER_GRAPH is None:
        raise RuntimeError(
            "worker graph has not been initialized",
        )
    return _WORKER_GRAPH


def measure_single_case(
    *,
    graph: MappedBinarySolverGraph,
    case: BenchmarkCase,
    path_mode: SolverPathMode,
    materialize_titles: bool,
) -> SolverMeasurement:
    started_at = time.perf_counter()
    try:
        if path_mode == "all_shortest":
            search_started_at = time.perf_counter()
            search_result = search_all_shortest_paths_by_node_ids(
                graph,
                start_node_id=case.start_node_id,
                target_node_id=case.target_node_id,
            )
            search_ms = (time.perf_counter() - search_started_at) * 1000.0
            path_node_id_paths = search_result.path_node_id_paths
            paths_found = len(
                path_node_id_paths,
            )
            path_length = search_result.path_length
            pages_visited = search_result.pages_visited
            links_scanned = search_result.links_scanned
            title_materialization_ms, path_node_total = materialize_path_titles(
                graph=graph,
                path_node_id_paths=path_node_id_paths,
                enabled=materialize_titles,
            )
        else:
            search_started_at = time.perf_counter()
            search_result = search_shortest_path_by_node_ids(
                graph,
                start_node_id=case.start_node_id,
                target_node_id=case.target_node_id,
            )
            search_ms = (time.perf_counter() - search_started_at) * 1000.0
            if search_result.path_node_ids is None:
                path_node_id_paths: tuple[tuple[int, ...], ...] = ()
            else:
                path_node_id_paths = (search_result.path_node_ids,)
            paths_found = len(
                path_node_id_paths,
            )
            path_length = search_result.path_length
            pages_visited = search_result.pages_visited
            links_scanned = search_result.links_scanned
            title_materialization_ms, path_node_total = materialize_path_titles(
                graph=graph,
                path_node_id_paths=path_node_id_paths,
                enabled=materialize_titles,
            )

        total_ms = (time.perf_counter() - started_at) * 1000.0
        return SolverMeasurement(
            case_id=case.case_id,
            path_mode=path_mode,
            start_node_id=case.start_node_id,
            target_node_id=case.target_node_id,
            start_title=case.start_title,
            target_title=case.target_title,
            status="ok",
            path_length=path_length,
            paths_found=paths_found,
            pages_visited=pages_visited,
            links_scanned=links_scanned,
            path_node_total=path_node_total,
            search_ms=search_ms,
            title_materialization_ms=title_materialization_ms,
            total_ms=total_ms,
            error_type=None,
            error_message=None,
        )
    except Exception as error:
        total_ms = (time.perf_counter() - started_at) * 1000.0
        return SolverMeasurement(
            case_id=case.case_id,
            path_mode=path_mode,
            start_node_id=case.start_node_id,
            target_node_id=case.target_node_id,
            start_title=case.start_title,
            target_title=case.target_title,
            status="error",
            path_length=None,
            paths_found=0,
            pages_visited=0,
            links_scanned=0,
            path_node_total=0,
            search_ms=total_ms,
            title_materialization_ms=None,
            total_ms=total_ms,
            error_type=type(error).__name__,
            error_message=str(
                error,
            ),
        )


def materialize_path_titles(
    *,
    graph: MappedBinarySolverGraph,
    path_node_id_paths: tuple[tuple[int, ...], ...],
    enabled: bool,
) -> tuple[float | None, int]:
    if not enabled:
        return None, sum(
            len(
                path_node_ids,
            )
            for path_node_ids in path_node_id_paths
        )

    started_at = time.perf_counter()
    path_node_total = 0
    for path_node_ids in path_node_id_paths:
        path_node_total += len(
            path_node_ids,
        )
        for node_id in path_node_ids:
            graph.title_for_node_id(
                node_id,
            )
    return (time.perf_counter() - started_at) * 1000.0, path_node_total


def build_summary_payload(
    *,
    graph_path: Path,
    snapshot_id: str | None,
    path_mode: SolverPathMode,
    materialize_titles: bool,
    worker_count: int,
    chunk_size: int,
    case_count: int,
    seed: int,
    run_id: str,
    run_started_at: datetime,
    run_ended_at: datetime,
    total_run_elapsed_ms: float,
    sampling_result: SamplingResult,
    sampling_elapsed_ms: float,
    measurement_state: MeasurementAggregationState,
    results_path: Path,
) -> dict[str, object]:
    successful_case_count = measurement_state.status_counts.get(
        "ok",
        0,
    )
    throughput = (
        successful_case_count / (total_run_elapsed_ms / 1000.0)
        if total_run_elapsed_ms > 0
        else 0.0
    )
    return {
        "run_id": run_id,
        "graph_path": str(
            graph_path,
        ),
        "snapshot_id": snapshot_id,
        "path_mode": path_mode,
        "materialize_titles": materialize_titles,
        "seed": seed,
        "case_count": case_count,
        "worker_count": worker_count,
        "chunk_size": chunk_size,
        "run_started_at": run_started_at.isoformat(),
        "run_ended_at": run_ended_at.isoformat(),
        "total_run_elapsed_ms": total_run_elapsed_ms,
        "throughput_solves_per_second": throughput,
        "sampling": {
            "attempts": sampling_result.attempts,
            "sampled_cases": len(
                sampling_result.cases,
            ),
            "sampling_elapsed_ms": sampling_elapsed_ms,
        },
        "results_path": str(
            results_path,
        ),
        "status_counts": measurement_state.status_counts,
        "found_path_count": measurement_state.found_path_count,
        "error_count": measurement_state.error_count,
        "search_ms": summarize_numeric(
            measurement_state.search_ms_values,
        ),
        "title_materialization_ms": summarize_numeric(
            measurement_state.title_materialization_ms_values,
        ),
        "total_ms": summarize_numeric(
            measurement_state.total_ms_values,
        ),
        "pages_visited": summarize_numeric(
            measurement_state.pages_visited_values,
        ),
        "links_scanned": summarize_numeric(
            measurement_state.links_scanned_values,
        ),
        "paths_found": summarize_numeric(
            measurement_state.paths_found_values,
        ),
        "path_node_total": summarize_numeric(
            measurement_state.path_node_total_values,
        ),
        "path_length": summarize_numeric(
            measurement_state.path_length_values,
        ),
        "path_length_histogram": dict(
            sorted(
                measurement_state.path_length_histogram.items(),
                key=lambda item: int(
                    item[0],
                ),
            ),
        ),
        "paths_found_bucket_histogram": dict(
            sorted(
                measurement_state.paths_found_bucket_histogram.items(),
            ),
        ),
        "slowest_cases": measurement_state.slowest_cases_descending(),
    }


def summarize_numeric(
    values: list[int] | list[float],
) -> dict[str, float | int] | None:
    if not values:
        return None
    numeric_values = sorted(
        values,
    )
    return {
        "count": len(
            numeric_values,
        ),
        "min": numeric_values[0],
        "max": numeric_values[-1],
        "mean": mean(
            numeric_values,
        ),
        "median": median(
            numeric_values,
        ),
        "p90": percentile(
            numeric_values,
            0.90,
        ),
        "p95": percentile(
            numeric_values,
            0.95,
        ),
        "p99": percentile(
            numeric_values,
            0.99,
        ),
        "p999": percentile(
            numeric_values,
            0.999,
        ),
    }


def percentile(
    sorted_values: list[int] | list[float],
    quantile: float,
) -> float:
    if not sorted_values:
        raise ValueError(
            "sorted_values cannot be empty",
        )
    if (
        len(
            sorted_values,
        )
        == 1
    ):
        return float(
            sorted_values[0],
        )
    rank = (len(sorted_values) - 1) * quantile
    lower_index = math.floor(
        rank,
    )
    upper_index = math.ceil(
        rank,
    )
    lower_value = float(
        sorted_values[lower_index],
    )
    upper_value = float(
        sorted_values[upper_index],
    )
    if lower_index == upper_index:
        return lower_value
    interpolation_weight = rank - lower_index
    return lower_value + ((upper_value - lower_value) * interpolation_weight)


def bucket_paths_found(
    paths_found: int,
) -> str:
    if paths_found == 0:
        return "0"
    if paths_found == 1:
        return "1"
    if paths_found == 2:
        return "2"
    if paths_found <= 4:
        return "3-4"
    if paths_found <= 9:
        return "5-9"
    if paths_found <= 19:
        return "10-19"
    if paths_found <= 49:
        return "20-49"
    if paths_found <= 99:
        return "50-99"
    if paths_found <= 499:
        return "100-499"
    return "500+"


if __name__ == "__main__":
    main()
