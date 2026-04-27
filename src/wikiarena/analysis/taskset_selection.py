from __future__ import annotations

from pathlib import Path
from random import Random
import re

from pydantic import BaseModel, Field

from wikiarena.analysis.taskset_candidates import (
    DEFAULT_EXCLUDED_TITLE_PATTERNS,
    write_task_candidates_jsonl,
)
from wikiarena.analysis.taskset_pool import TaskCandidateRow
from wikiarena.protocol import TaskSpec


class TasksetSelectionResult(BaseModel):
    selection_seed: int
    requested_counts_by_distance: dict[int, int] = Field(
        default_factory=dict,
    )
    selected_counts_by_distance: dict[int, int] = Field(
        default_factory=dict,
    )
    available_counts_by_distance: dict[int, int] = Field(
        default_factory=dict,
    )
    input_candidate_count: int = 0
    filtered_candidate_count: int = 0
    deduped_candidate_count: int = 0
    tasks: list[TaskSpec] = Field(
        default_factory=list,
    )

    def build_summary(
        self,
    ) -> dict[str, object]:
        shortage_counts_by_distance: dict[int, int] = {}
        for distance, requested_count in self.requested_counts_by_distance.items():
            selected_count = self.selected_counts_by_distance.get(
                distance,
                0,
            )
            if selected_count < requested_count:
                shortage_counts_by_distance[distance] = (
                    requested_count - selected_count
                )

        return {
            "selection_seed": self.selection_seed,
            "input_candidate_count": self.input_candidate_count,
            "filtered_candidate_count": self.filtered_candidate_count,
            "deduped_candidate_count": self.deduped_candidate_count,
            "selected_task_count": len(
                self.tasks,
            ),
            "requested_counts_by_distance": self.requested_counts_by_distance,
            "available_counts_by_distance": self.available_counts_by_distance,
            "selected_counts_by_distance": self.selected_counts_by_distance,
            "shortage_counts_by_distance": shortage_counts_by_distance,
        }


def select_taskset_from_candidate_pool(
    candidates: list[TaskCandidateRow],
    *,
    counts_by_distance: dict[int, int],
    selection_seed: int,
    max_distance: int | None = None,
    excluded_title_patterns: tuple[str, ...] = DEFAULT_EXCLUDED_TITLE_PATTERNS,
) -> TasksetSelectionResult:
    normalized_counts = _normalize_counts_by_distance(
        counts_by_distance,
    )
    compiled_patterns = [
        re.compile(
            pattern,
            re.IGNORECASE,
        )
        for pattern in excluded_title_patterns
    ]

    filtered_candidates = [
        candidate
        for candidate in candidates
        if _candidate_passes_title_filters(
            candidate,
            compiled_patterns,
        )
    ]

    shuffled_candidates = list(
        filtered_candidates,
    )
    Random(
        selection_seed,
    ).shuffle(
        shuffled_candidates,
    )

    deduped_candidates: list[TaskCandidateRow] = []
    seen_task_ids: set[str] = set()
    for candidate in shuffled_candidates:
        task_id = candidate.task.task_id
        if task_id is None:
            raise ValueError(
                "candidate task_id cannot be null after TaskSpec validation",
            )
        if task_id in seen_task_ids:
            continue
        seen_task_ids.add(
            task_id,
        )
        if (
            max_distance is not None
            and candidate.task.shortest_path_length is not None
            and candidate.task.shortest_path_length > max_distance
        ):
            continue
        deduped_candidates.append(
            candidate,
        )

    available_by_distance: dict[int, list[TaskSpec]] = {
        distance: []
        for distance in sorted(
            normalized_counts,
        )
    }
    for candidate in deduped_candidates:
        shortest_path_length = candidate.task.shortest_path_length
        if shortest_path_length is None:
            continue
        if shortest_path_length not in available_by_distance:
            continue
        available_by_distance[shortest_path_length].append(
            candidate.task,
        )

    selected_tasks: list[TaskSpec] = []
    selected_counts_by_distance: dict[int, int] = {}
    available_counts_by_distance: dict[int, int] = {
        distance: len(
            available_by_distance[distance],
        )
        for distance in sorted(
            available_by_distance,
        )
    }
    for distance in sorted(
        normalized_counts,
    ):
        requested_count = normalized_counts[distance]
        selected_for_distance = available_by_distance[distance][
            :requested_count
        ]
        selected_tasks.extend(
            selected_for_distance,
        )
        selected_counts_by_distance[distance] = len(
            selected_for_distance,
        )

    selected_tasks.sort(
        key=lambda task: (
            task.shortest_path_length or -1,
            task.start_page_title,
            task.target_page_title,
        ),
    )

    return TasksetSelectionResult(
        selection_seed=selection_seed,
        requested_counts_by_distance={
            distance: normalized_counts[distance]
            for distance in sorted(
                normalized_counts,
            )
        },
        selected_counts_by_distance=selected_counts_by_distance,
        available_counts_by_distance=available_counts_by_distance,
        input_candidate_count=len(
            candidates,
        ),
        filtered_candidate_count=len(
            filtered_candidates,
        ),
        deduped_candidate_count=len(
            deduped_candidates,
        ),
        tasks=selected_tasks,
    )


def write_selected_taskset_jsonl(
    tasks: list[TaskSpec],
    *,
    output_path: str | Path,
) -> None:
    write_task_candidates_jsonl(
        tasks,
        output_path=output_path,
    )


def _normalize_counts_by_distance(
    counts_by_distance: dict[int, int],
) -> dict[int, int]:
    normalized_counts: dict[int, int] = {}
    for distance, count in counts_by_distance.items():
        if distance < 0:
            raise ValueError(
                "distance must be non-negative",
            )
        if count < 1:
            raise ValueError(
                "count must be at least 1",
            )
        normalized_counts[distance] = count
    return normalized_counts


def _candidate_passes_title_filters(
    candidate: TaskCandidateRow,
    compiled_patterns: list[re.Pattern[str]],
) -> bool:
    for pattern in compiled_patterns:
        if pattern.search(
            candidate.task.start_page_title,
        ):
            return False
        if pattern.search(
            candidate.task.target_page_title,
        ):
            return False
    return True
