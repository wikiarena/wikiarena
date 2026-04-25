from __future__ import annotations

from datetime import datetime

from wikiarena.eval.summary import compare_run_results
from wikiarena.eval.summary import summarize_run_results
from wikiarena.protocol import RunResult
from wikiarena.protocol import TerminalOutcome
from wikiarena.protocol import TerminationReason


def _build_run_result(
    *,
    run_id: str,
    race_id: str,
    participant_id: str,
    terminal_outcome: TerminalOutcome,
    termination_reason: TerminationReason,
    total_committed_moves: int,
    duration_ms: float,
    ranking_eligible: bool = True,
) -> RunResult:
    return RunResult(
        run_id=run_id,
        race_id=race_id,
        benchmark_id="benchmark-1",
        task_id="en__apple__banana",
        participant_id=participant_id,
        terminal_outcome=terminal_outcome,
        termination_reason=termination_reason,
        committed_moves=[
            {
                "move_index": index,
                "source_step_index": index,
                "from_page_title": f"page-{index}",
                "to_page_title": f"page-{index + 1}",
                "occurred_at": datetime(2026, 1, 1, 0, 0, index),
            }
            for index in range(1, total_committed_moves + 1)
        ],
        ranking_eligible=ranking_eligible,
        ruleset_hash="ruleset-1",
        taskset_hash="taskset-1",
        started_at=datetime(2026, 1, 1, 0, 0, 0),
        ended_at=datetime(2026, 1, 1, 0, 0, 0),
        duration_ms=duration_ms,
    )


def test_compare_run_results_prefers_fewer_moves_then_draw() -> None:
    faster_run = _build_run_result(
        run_id="run-a",
        race_id="race-1",
        participant_id="a",
        terminal_outcome=TerminalOutcome.SUCCESS,
        termination_reason=TerminationReason.TASK_COMPLETED,
        total_committed_moves=4,
        duration_ms=500.0,
    )
    slower_run = _build_run_result(
        run_id="run-b",
        race_id="race-1",
        participant_id="b",
        terminal_outcome=TerminalOutcome.SUCCESS,
        termination_reason=TerminationReason.TASK_COMPLETED,
        total_committed_moves=4,
        duration_ms=100.0,
    )

    assert (
        compare_run_results(
            faster_run,
            slower_run,
            tie_breaker="fewest_moves_then_draw",
        )
        == 0
    )
    assert (
        compare_run_results(
            faster_run,
            slower_run,
            tie_breaker="fewest_moves_then_fastest_ms",
        )
        == -1
    )


def test_summarize_run_results_orders_participants_by_elo() -> None:
    winner = _build_run_result(
        run_id="run-a",
        race_id="race-1",
        participant_id="winner",
        terminal_outcome=TerminalOutcome.SUCCESS,
        termination_reason=TerminationReason.TASK_COMPLETED,
        total_committed_moves=3,
        duration_ms=100.0,
    )
    loser = _build_run_result(
        run_id="run-b",
        race_id="race-1",
        participant_id="loser",
        terminal_outcome=TerminalOutcome.SUCCESS,
        termination_reason=TerminationReason.TASK_COMPLETED,
        total_committed_moves=5,
        duration_ms=100.0,
    )

    summary = summarize_run_results(
        [winner, loser],
    )

    assert summary.total_runs == 2
    assert summary.total_races == 1
    assert summary.participants[0].participant_id == "winner"
    assert summary.participants[0].elo is not None
