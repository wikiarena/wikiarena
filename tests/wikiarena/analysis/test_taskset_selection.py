from __future__ import annotations

from datetime import UTC, datetime

from wikiarena.analysis.taskset_selection import select_taskset_from_candidate_pool
from wikiarena.analysis.taskset_pool import TaskCandidateRow, TaskCandidateSolveMetrics
from wikiarena.protocol import PathSource, SolverShortestPath, TaskSpec


def test_select_taskset_from_candidate_pool_balances_and_dedupes() -> None:
    candidates = [
        _candidate_row(
            start_page_title="Alpha",
            target_page_title="Bravo",
            shortest_path_length=2,
            sample_index_within_worker=1,
        ),
        _candidate_row(
            start_page_title="Alpha",
            target_page_title="Bravo",
            shortest_path_length=2,
            sample_index_within_worker=2,
        ),
        _candidate_row(
            start_page_title="Charlie",
            target_page_title="Echo",
            shortest_path_length=2,
            sample_index_within_worker=3,
        ),
        _candidate_row(
            start_page_title="Delta",
            target_page_title="Foxtrot",
            shortest_path_length=3,
            sample_index_within_worker=4,
        ),
        _candidate_row(
            start_page_title="Golf",
            target_page_title="Hotel",
            shortest_path_length=3,
            sample_index_within_worker=5,
        ),
        _candidate_row(
            start_page_title="List of examples",
            target_page_title="India",
            shortest_path_length=3,
            sample_index_within_worker=6,
        ),
    ]

    result = select_taskset_from_candidate_pool(
        candidates,
        counts_by_distance={2: 1, 3: 2},
        selection_seed=7,
        excluded_title_patterns=(r"^List of ",),
    )

    assert len(result.tasks) == 3
    assert result.selected_counts_by_distance == {2: 1, 3: 2}
    assert result.available_counts_by_distance == {2: 2, 3: 2}
    assert result.deduped_candidate_count == 4
    assert {
        task.shortest_path_length for task in result.tasks
    } == {2, 3}


def test_select_taskset_from_candidate_pool_respects_max_distance() -> None:
    candidates = [
        _candidate_row(
            start_page_title="Alpha",
            target_page_title="Bravo",
            shortest_path_length=2,
            sample_index_within_worker=1,
        ),
        _candidate_row(
            start_page_title="Charlie",
            target_page_title="Echo",
            shortest_path_length=5,
            sample_index_within_worker=2,
        ),
    ]

    result = select_taskset_from_candidate_pool(
        candidates,
        counts_by_distance={2: 1, 5: 1},
        selection_seed=3,
        max_distance=4,
    )

    assert result.selected_counts_by_distance == {2: 1, 5: 0}
    assert result.available_counts_by_distance == {2: 1, 5: 0}
    assert len(result.tasks) == 1
    assert result.tasks[0].shortest_path_length == 2


def _candidate_row(
    *,
    start_page_title: str,
    target_page_title: str,
    shortest_path_length: int,
    sample_index_within_worker: int,
) -> TaskCandidateRow:
    page_titles = [start_page_title]
    for hop_index in range(
        shortest_path_length - 1,
    ):
        page_titles.append(
            f"Middle {sample_index_within_worker}-{hop_index}",
        )
    page_titles.append(
        target_page_title,
    )
    task = TaskSpec(
        language="en",
        start_page_title=start_page_title,
        target_page_title=target_page_title,
        shortest_path_length=shortest_path_length,
        solver_shortest_path=SolverShortestPath(
            page_titles=page_titles,
            computed_at=datetime(2026, 4, 19, 18, 0, tzinfo=UTC),
            solver_snapshot_id="enwiki-20260401",
            source=PathSource.LOCAL_GRAPH,
        ),
    )
    return TaskCandidateRow(
        task=task,
        worker_index=0,
        worker_seed=20260419,
        sample_index_within_worker=sample_index_within_worker,
        start_node_id=sample_index_within_worker,
        target_node_id=sample_index_within_worker + 100,
        solve_metrics=TaskCandidateSolveMetrics(
            solve_ms=50.0,
            pages_visited=10,
            links_scanned=20,
        ),
    )
