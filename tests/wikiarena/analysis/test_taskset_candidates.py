from __future__ import annotations

from datetime import UTC, date, datetime
import re

from wikiarena.analysis import generate_task_candidates
from wikiarena.analysis.taskset_candidates import (
    DEFAULT_EXCLUDED_TITLE_PATTERNS,
    _title_is_excluded,
    default_task_candidate_seed,
)
from wikiarena.solver.binary.graph import BinarySolverGraph
from wikiarena.solver.binary.io import SolverBinaryData


def test_generate_task_candidates_collects_requested_distance_buckets() -> None:
    graph = BinarySolverGraph.from_solver_binary_data(
        _make_candidate_test_solver_binary_data(),
    )

    result = generate_task_candidates(
        graph,
        counts_by_distance={1: 1, 2: 1, 3: 1},
        seed=7,
        max_attempts=500,
        solver_snapshot_id="enwiki-20260301",
        generated_at=datetime(2026, 4, 19, 16, 30, tzinfo=UTC),
    )

    assert result.generated_counts_by_distance == {1: 1, 2: 1, 3: 1}
    assert len(result.tasks) == 3
    assert result.attempts <= 500
    assert result.unique_pairs_considered >= 3

    seen_pairs: set[tuple[str, str]] = set()
    for task in result.tasks:
        pair = (
            task.start_page_title,
            task.target_page_title,
        )
        assert pair not in seen_pairs
        seen_pairs.add(
            pair,
        )

        assert task.shortest_path_length is not None
        assert task.solver_shortest_path is not None
        assert task.solver_shortest_path.page_titles[0] == task.start_page_title
        assert task.solver_shortest_path.page_titles[-1] == task.target_page_title
        assert task.solver_shortest_path.hop_count == task.shortest_path_length
        assert task.metadata["generator"] == "random_static_graph_pairs_v1"
        assert task.metadata["generator_seed"] == 7
        assert task.solver_shortest_path.solver_snapshot_id == "enwiki-20260301"
        assert task.solver_shortest_path.computed_at == datetime(
            2026,
            4,
            19,
            16,
            30,
            tzinfo=UTC,
        )
        assert "reference_shortest_path" not in task.metadata
        assert "shortest_path_length" not in task.metadata
        assert "solver_snapshot_id" not in task.metadata


def test_generate_task_candidates_stops_after_max_attempts_for_missing_bucket() -> None:
    graph = BinarySolverGraph.from_solver_binary_data(
        _make_candidate_test_solver_binary_data(),
    )

    result = generate_task_candidates(
        graph,
        counts_by_distance={4: 1},
        seed=7,
        max_attempts=25,
    )

    assert result.generated_counts_by_distance == {4: 0}
    assert result.tasks == []
    assert result.attempts == 25


def test_default_task_candidate_seed_uses_yyyymmdd_date_format() -> None:
    assert default_task_candidate_seed(
        date(2026, 4, 19),
    ) == 20260419


def test_default_exclusions_only_drop_disambiguation_titles() -> None:
    compiled_patterns = [
        re.compile(
            pattern,
            re.IGNORECASE,
        )
        for pattern in DEFAULT_EXCLUDED_TITLE_PATTERNS
    ]

    assert _title_is_excluded(
        "Example (disambiguation)",
        compiled_patterns,
    )
    assert not _title_is_excluded(
        "List of examples",
        compiled_patterns,
    )
    assert not _title_is_excluded(
        "Outline of mathematics",
        compiled_patterns,
    )


def _make_candidate_test_solver_binary_data() -> SolverBinaryData:
    return SolverBinaryData(
        canonical_titles=("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"),
        out_offsets=(0, 2, 3, 4, 5, 5, 5),
        out_neighbors=(1, 2, 3, 3, 4),
        in_offsets=(0, 0, 1, 2, 4, 5, 5),
        in_neighbors=(0, 0, 1, 2, 3),
    )
