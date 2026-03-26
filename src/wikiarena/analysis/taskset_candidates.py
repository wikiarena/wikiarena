from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from wikiarena.protocol import TaskSpec
from wikiarena.solver.binary.search import (
    BinarySearchGraph,
    find_shortest_path_by_node_ids,
)

DEFAULT_EXCLUDED_TITLE_PATTERNS = (
    r"\(disambiguation\)$",
    r"^List of ",
    r"^Index of ",
    r"^Outline of ",
    r"^\d{3,4}$",
)


class TaskCandidateGenerationResult(BaseModel):
    tasks: list[TaskSpec] = Field(
        default_factory=list,
    )
    requested_counts_by_distance: dict[int, int] = Field(
        default_factory=dict,
    )
    generated_counts_by_distance: dict[int, int] = Field(
        default_factory=dict,
    )
    attempts: int = 0
    unique_pairs_considered: int = 0
    seed: int = 0


class CandidateGraph(BinarySearchGraph, Protocol):
    @property
    def node_count(
        self,
    ) -> int: ...


def generate_task_candidates(
    graph: CandidateGraph,
    *,
    counts_by_distance: dict[int, int],
    language: str = "en",
    seed: int = 0,
    max_attempts: int = 100_000,
    excluded_title_patterns: tuple[str, ...] = DEFAULT_EXCLUDED_TITLE_PATTERNS,
) -> TaskCandidateGenerationResult:
    normalized_counts = _normalize_counts_by_distance(
        counts_by_distance,
    )
    if max_attempts < 1:
        raise ValueError(
            "max_attempts must be at least 1",
        )

    compiled_patterns = [
        re.compile(
            pattern,
            re.IGNORECASE,
        )
        for pattern in excluded_title_patterns
    ]
    rng = random.Random(
        seed,
    )

    generated_counts = {
        distance: 0
        for distance in sorted(
            normalized_counts,
        )
    }
    tasks: list[TaskSpec] = []
    seen_pairs: set[tuple[int, int]] = set()
    attempts = 0

    while attempts < max_attempts:
        if _counts_satisfied(
            generated_counts,
            normalized_counts,
        ):
            break

        attempts += 1
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
            continue

        shortest_path_node_ids = find_shortest_path_by_node_ids(
            graph,
            start_node_id=start_node_id,
            target_node_id=target_node_id,
        )
        if shortest_path_node_ids is None:
            continue

        shortest_path_length = (
            len(
                shortest_path_node_ids,
            )
            - 1
        )
        if shortest_path_length not in normalized_counts:
            continue
        if (
            generated_counts[shortest_path_length]
            >= normalized_counts[shortest_path_length]
        ):
            continue

        reference_shortest_path = [
            graph.title_for_node_id(
                node_id,
            )
            for node_id in shortest_path_node_ids
        ]
        tasks.append(
            TaskSpec(
                language=language,
                start_page_title=start_title,
                target_page_title=target_title,
                metadata={
                    "shortest_path_length": shortest_path_length,
                    "start_node_id": start_node_id,
                    "target_node_id": target_node_id,
                    "reference_shortest_path": reference_shortest_path,
                    "generator": "random_static_graph_pairs_v1",
                    "generator_seed": seed,
                    "sample_attempt": attempts,
                },
            ),
        )
        generated_counts[shortest_path_length] += 1

    return TaskCandidateGenerationResult(
        tasks=sorted(
            tasks,
            key=lambda task: (
                int(
                    task.metadata["shortest_path_length"],
                ),
                task.start_page_title,
                task.target_page_title,
            ),
        ),
        requested_counts_by_distance={
            distance: normalized_counts[distance]
            for distance in sorted(
                normalized_counts,
            )
        },
        generated_counts_by_distance={
            distance: generated_counts[distance]
            for distance in sorted(
                generated_counts,
            )
        },
        attempts=attempts,
        unique_pairs_considered=len(
            seen_pairs,
        ),
        seed=seed,
    )


def write_task_candidates_jsonl(
    tasks: list[TaskSpec],
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
        for task in tasks:
            file_handle.write(
                json.dumps(
                    task.model_dump(
                        mode="json",
                    ),
                    ensure_ascii=False,
                ),
            )
            file_handle.write(
                "\n",
            )


def _normalize_counts_by_distance(
    counts_by_distance: dict[int, int],
) -> dict[int, int]:
    if not counts_by_distance:
        raise ValueError(
            "counts_by_distance cannot be empty",
        )

    normalized_counts: dict[int, int] = {}
    for distance, count in counts_by_distance.items():
        if distance < 1:
            raise ValueError(
                f"distance must be at least 1, got {distance}",
            )
        if count < 1:
            raise ValueError(
                f"count must be at least 1 for distance {distance}",
            )
        normalized_counts[int(distance)] = int(
            count,
        )
    return normalized_counts


def _counts_satisfied(
    generated_counts: dict[int, int],
    requested_counts: dict[int, int],
) -> bool:
    return all(
        generated_counts[distance] >= requested_counts[distance]
        for distance in requested_counts
    )


def _title_is_excluded(
    title: str,
    compiled_patterns: list[re.Pattern[str]],
) -> bool:
    return any(
        pattern.search(
            title,
        )
        for pattern in compiled_patterns
    )
