from __future__ import annotations

from pathlib import Path

from wikiarena.analysis.taskset_pool import (
    generate_task_candidate_pool,
    read_task_candidate_pool_jsonl,
    write_task_candidate_pool_jsonl,
)
from wikiarena.solver.binary.io import SolverBinaryData, write_solver_binary


def test_generate_task_candidate_pool_produces_requested_candidates(
    tmp_path: Path,
) -> None:
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260401.bin"
    _write_candidate_test_graph(
        graph_path,
    )

    result = generate_task_candidate_pool(
        graph_path=graph_path,
        candidate_count=4,
        base_seed=7,
        worker_count=1,
        solver_snapshot_id="enwiki-20260401",
    )

    assert len(result.candidates) == 4
    assert len(result.worker_stats) == 1
    assert result.worker_stats[0].generated_candidates == 4
    assert result.worker_stats[0].solve_calls >= 4
    for candidate in result.candidates:
        assert candidate.task.shortest_path_length is not None
        assert candidate.task.solver_shortest_path is not None
        assert candidate.task.solver_shortest_path.solver_snapshot_id == (
            "enwiki-20260401"
        )
        assert candidate.task.solver_shortest_path.hop_count == (
            candidate.task.shortest_path_length
        )

    summary = result.build_summary()
    assert summary["total_candidates"] == 4
    assert summary["total_solve_calls"] >= 4


def test_task_candidate_pool_jsonl_round_trip(
    tmp_path: Path,
) -> None:
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260401.bin"
    output_path = tmp_path / "candidate_pool.jsonl"
    _write_candidate_test_graph(
        graph_path,
    )

    result = generate_task_candidate_pool(
        graph_path=graph_path,
        candidate_count=3,
        base_seed=11,
        worker_count=1,
        solver_snapshot_id="enwiki-20260401",
    )
    write_task_candidate_pool_jsonl(
        result.candidates,
        output_path=output_path,
    )
    round_tripped_candidates = read_task_candidate_pool_jsonl(
        output_path,
    )

    assert [candidate.model_dump() for candidate in round_tripped_candidates] == [
        candidate.model_dump() for candidate in result.candidates
    ]


def _write_candidate_test_graph(
    graph_path: Path,
) -> None:
    write_solver_binary(
        file_path=graph_path,
        data=SolverBinaryData(
            canonical_titles=("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"),
            out_offsets=(0, 2, 3, 4, 5, 5, 5),
            out_neighbors=(1, 2, 3, 3, 4),
            in_offsets=(0, 0, 1, 2, 4, 5, 5),
            in_neighbors=(0, 0, 1, 2, 3),
        ),
    )
