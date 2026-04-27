from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
import json
import os
from pathlib import Path
from random import Random
import re
from time import perf_counter

from pydantic import BaseModel, Field

from wikiarena.analysis.taskset_candidates import DEFAULT_EXCLUDED_TITLE_PATTERNS
from wikiarena.protocol import PathSource, SolverShortestPath, TaskSpec
from wikiarena.solver.binary import MappedBinarySolverGraph
from wikiarena.solver.binary.search import search_shortest_path_by_node_ids


class TaskCandidateSolveMetrics(BaseModel):
    solve_ms: float = Field(
        ge=0.0,
    )
    pages_visited: int = Field(
        ge=0,
    )
    links_scanned: int = Field(
        ge=0,
    )


class TaskCandidateRow(BaseModel):
    task: TaskSpec
    worker_index: int = Field(
        ge=0,
    )
    worker_seed: int
    sample_index_within_worker: int = Field(
        ge=1,
    )
    start_node_id: int = Field(
        ge=0,
    )
    target_node_id: int = Field(
        ge=0,
    )
    solve_metrics: TaskCandidateSolveMetrics


class TaskCandidateWorkerStats(BaseModel):
    worker_index: int = Field(
        ge=0,
    )
    worker_seed: int
    requested_candidates: int = Field(
        ge=0,
    )
    generated_candidates: int = Field(
        ge=0,
    )
    sample_attempts: int = Field(
        ge=0,
    )
    unique_pairs_considered: int = Field(
        ge=0,
    )
    duplicate_pairs: int = Field(
        ge=0,
    )
    excluded_titles: int = Field(
        ge=0,
    )
    unreachable_pairs: int = Field(
        ge=0,
    )
    solve_calls: int = Field(
        ge=0,
    )
    solve_time_ms: float = Field(
        ge=0.0,
    )
    wall_time_ms: float = Field(
        ge=0.0,
    )


class TaskCandidatePoolResult(BaseModel):
    base_seed: int
    worker_count: int = Field(
        ge=1,
    )
    solver_snapshot_id: str | None = None
    candidates: list[TaskCandidateRow] = Field(
        default_factory=list,
    )
    worker_stats: list[TaskCandidateWorkerStats] = Field(
        default_factory=list,
    )

    def build_summary(
        self,
    ) -> dict[str, object]:
        distance_counts: dict[int, int] = {}
        total_solve_calls = 0
        total_solve_time_ms = 0.0
        total_sample_attempts = 0
        total_unique_pairs = 0
        total_duplicates = 0
        total_excluded = 0
        total_unreachable = 0
        total_wall_time_ms = 0.0
        for candidate in self.candidates:
            shortest_path_length = candidate.task.shortest_path_length
            if shortest_path_length is None:
                continue
            distance_counts[shortest_path_length] = (
                distance_counts.get(
                    shortest_path_length,
                    0,
                )
                + 1
            )

        for worker_stats in self.worker_stats:
            total_solve_calls += worker_stats.solve_calls
            total_solve_time_ms += worker_stats.solve_time_ms
            total_sample_attempts += worker_stats.sample_attempts
            total_unique_pairs += worker_stats.unique_pairs_considered
            total_duplicates += worker_stats.duplicate_pairs
            total_excluded += worker_stats.excluded_titles
            total_unreachable += worker_stats.unreachable_pairs
            total_wall_time_ms += worker_stats.wall_time_ms

        average_solve_ms = 0.0
        if total_solve_calls > 0:
            average_solve_ms = total_solve_time_ms / total_solve_calls

        return {
            "base_seed": self.base_seed,
            "worker_count": self.worker_count,
            "solver_snapshot_id": self.solver_snapshot_id,
            "total_candidates": len(
                self.candidates,
            ),
            "distance_counts": {
                distance: distance_counts[distance]
                for distance in sorted(
                    distance_counts,
                )
            },
            "total_sample_attempts": total_sample_attempts,
            "total_unique_pairs_considered": total_unique_pairs,
            "total_duplicate_pairs": total_duplicates,
            "total_excluded_titles": total_excluded,
            "total_unreachable_pairs": total_unreachable,
            "total_solve_calls": total_solve_calls,
            "average_solve_ms": round(
                average_solve_ms,
                3,
            ),
            "total_solve_time_ms": round(
                total_solve_time_ms,
                1,
            ),
            "aggregate_worker_wall_time_ms": round(
                total_wall_time_ms,
                1,
            ),
        }


@dataclass(frozen=True)
class TaskCandidateWorkerConfig:
    graph_path: Path
    requested_candidates: int
    language: str
    worker_index: int
    worker_seed: int
    solver_snapshot_id: str | None
    excluded_title_patterns: tuple[str, ...]


def default_task_candidate_worker_count() -> int:
    cpu_count = os.cpu_count() or 1
    return max(
        1,
        cpu_count,
    )


def generate_task_candidate_pool(
    *,
    graph_path: Path,
    candidate_count: int,
    language: str = "en",
    base_seed: int = 0,
    worker_count: int | None = None,
    solver_snapshot_id: str | None = None,
    excluded_title_patterns: tuple[str, ...] = DEFAULT_EXCLUDED_TITLE_PATTERNS,
) -> TaskCandidatePoolResult:
    if candidate_count < 1:
        raise ValueError(
            "candidate_count must be at least 1",
        )

    resolved_worker_count = worker_count or default_task_candidate_worker_count()
    if resolved_worker_count < 1:
        raise ValueError(
            "worker_count must be at least 1",
        )

    worker_request_counts = _split_requested_candidates(
        candidate_count,
        resolved_worker_count,
    )
    worker_seeds = _derive_worker_seeds(
        base_seed=base_seed,
        worker_count=resolved_worker_count,
    )
    worker_configs = [
        TaskCandidateWorkerConfig(
            graph_path=graph_path.expanduser().resolve(),
            requested_candidates=requested_count,
            language=language,
            worker_index=worker_index,
            worker_seed=worker_seeds[worker_index],
            solver_snapshot_id=solver_snapshot_id,
            excluded_title_patterns=excluded_title_patterns,
        )
        for worker_index, requested_count in enumerate(
            worker_request_counts,
        )
        if requested_count > 0
    ]

    worker_results: list[tuple[list[TaskCandidateRow], TaskCandidateWorkerStats]] = []
    with ProcessPoolExecutor(
        max_workers=resolved_worker_count,
    ) as executor:
        future_to_worker_index = {
            executor.submit(
                _generate_candidates_for_worker,
                worker_config,
            ): worker_config.worker_index
            for worker_config in worker_configs
        }
        for future in as_completed(
            future_to_worker_index,
        ):
            worker_results.append(
                future.result(),
            )

    candidates: list[TaskCandidateRow] = []
    worker_stats: list[TaskCandidateWorkerStats] = []
    for candidate_rows, worker_stat in worker_results:
        candidates.extend(
            candidate_rows,
        )
        worker_stats.append(
            worker_stat,
        )

    candidates.sort(
        key=lambda candidate: (
            candidate.worker_index,
            candidate.sample_index_within_worker,
            candidate.task.task_id or "",
        ),
    )
    worker_stats.sort(
        key=lambda stats: stats.worker_index,
    )

    return TaskCandidatePoolResult(
        base_seed=base_seed,
        worker_count=resolved_worker_count,
        solver_snapshot_id=solver_snapshot_id,
        candidates=candidates,
        worker_stats=worker_stats,
    )


def write_task_candidate_pool_jsonl(
    candidates: list[TaskCandidateRow],
    *,
    output_path: str | Path,
) -> None:
    resolved_output_path = Path(
        output_path,
    ).expanduser()
    with resolved_output_path.open(
        "w",
        encoding="utf-8",
    ) as file_handle:
        for candidate in candidates:
            file_handle.write(
                json.dumps(
                    candidate.model_dump(
                        mode="json",
                    ),
                ),
            )
            file_handle.write(
                "\n",
            )


def read_task_candidate_pool_jsonl(
    input_path: str | Path,
) -> list[TaskCandidateRow]:
    resolved_input_path = Path(
        input_path,
    ).expanduser()
    candidates: list[TaskCandidateRow] = []
    with resolved_input_path.open(
        "r",
        encoding="utf-8",
    ) as file_handle:
        for line in file_handle:
            stripped_line = line.strip()
            if not stripped_line:
                continue
            candidates.append(
                TaskCandidateRow.model_validate_json(
                    stripped_line,
                ),
            )
    return candidates


def _split_requested_candidates(
    candidate_count: int,
    worker_count: int,
) -> list[int]:
    base_count = candidate_count // worker_count
    remainder = candidate_count % worker_count
    return [
        base_count + (1 if worker_index < remainder else 0)
        for worker_index in range(
            worker_count,
        )
    ]


def _derive_worker_seeds(
    *,
    base_seed: int,
    worker_count: int,
) -> list[int]:
    seed_rng = Random(
        base_seed,
    )
    return [
        seed_rng.randrange(
            0,
            2**63,
        )
        for _ in range(
            worker_count,
        )
    ]


def _generate_candidates_for_worker(
    worker_config: TaskCandidateWorkerConfig,
) -> tuple[list[TaskCandidateRow], TaskCandidateWorkerStats]:
    compiled_patterns = [
        re.compile(
            pattern,
            re.IGNORECASE,
        )
        for pattern in worker_config.excluded_title_patterns
    ]
    rng = Random(
        worker_config.worker_seed,
    )
    seen_pairs: set[tuple[int, int]] = set()
    candidate_rows: list[TaskCandidateRow] = []
    sample_attempts = 0
    duplicate_pairs = 0
    excluded_titles = 0
    unreachable_pairs = 0
    solve_calls = 0
    solve_time_ms = 0.0
    wall_start = perf_counter()

    with MappedBinarySolverGraph(
        file_path=worker_config.graph_path,
    ) as graph:
        while len(candidate_rows) < worker_config.requested_candidates:
            sample_attempts += 1
            start_node_id = rng.randrange(
                graph.node_count,
            )
            target_node_id = rng.randrange(
                graph.node_count,
            )
            if start_node_id == target_node_id:
                continue

            pair_node_ids = (
                start_node_id,
                target_node_id,
            )
            if pair_node_ids in seen_pairs:
                duplicate_pairs += 1
                continue
            seen_pairs.add(
                pair_node_ids,
            )

            start_title = graph.title_for_node_id(
                start_node_id,
            )
            target_title = graph.title_for_node_id(
                target_node_id,
            )
            if _title_is_excluded(
                start_title,
                compiled_patterns,
            ) or _title_is_excluded(
                target_title,
                compiled_patterns,
            ):
                excluded_titles += 1
                continue

            solve_start = perf_counter()
            solve_result = search_shortest_path_by_node_ids(
                graph,
                start_node_id=start_node_id,
                target_node_id=target_node_id,
            )
            solve_elapsed_ms = (
                perf_counter() - solve_start
            ) * 1000.0
            solve_calls += 1
            solve_time_ms += solve_elapsed_ms

            if solve_result.path_node_ids is None:
                unreachable_pairs += 1
                continue

            solver_shortest_path_titles = [
                graph.title_for_node_id(
                    node_id,
                )
                for node_id in solve_result.path_node_ids
            ]
            candidate_rows.append(
                TaskCandidateRow(
                    task=TaskSpec(
                        language=worker_config.language,
                        start_page_title=start_title,
                        target_page_title=target_title,
                        shortest_path_length=solve_result.path_length,
                        solver_shortest_path=SolverShortestPath(
                            page_titles=solver_shortest_path_titles,
                            computed_at=datetime_now_utc(),
                            solver_snapshot_id=worker_config.solver_snapshot_id,
                            source=PathSource.LOCAL_GRAPH,
                        ),
                    ),
                    worker_index=worker_config.worker_index,
                    worker_seed=worker_config.worker_seed,
                    sample_index_within_worker=len(
                        seen_pairs,
                    ),
                    start_node_id=start_node_id,
                    target_node_id=target_node_id,
                    solve_metrics=TaskCandidateSolveMetrics(
                        solve_ms=solve_elapsed_ms,
                        pages_visited=solve_result.pages_visited,
                        links_scanned=solve_result.links_scanned,
                    ),
                ),
            )

    worker_stats = TaskCandidateWorkerStats(
        worker_index=worker_config.worker_index,
        worker_seed=worker_config.worker_seed,
        requested_candidates=worker_config.requested_candidates,
        generated_candidates=len(
            candidate_rows,
        ),
        sample_attempts=sample_attempts,
        unique_pairs_considered=len(
            seen_pairs,
        ),
        duplicate_pairs=duplicate_pairs,
        excluded_titles=excluded_titles,
        unreachable_pairs=unreachable_pairs,
        solve_calls=solve_calls,
        solve_time_ms=solve_time_ms,
        wall_time_ms=(perf_counter() - wall_start) * 1000.0,
    )
    return candidate_rows, worker_stats


def _title_is_excluded(
    title: str,
    compiled_patterns: list[re.Pattern[str]],
) -> bool:
    for pattern in compiled_patterns:
        if pattern.search(
            title,
        ):
            return True
    return False


def datetime_now_utc():
    from datetime import UTC, datetime

    return datetime.now(
        UTC,
    )
