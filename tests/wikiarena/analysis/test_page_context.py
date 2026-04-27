from __future__ import annotations

import json
from datetime import datetime

from wikiarena.analysis import approximate_token_count
from wikiarena.analysis import build_page_links_prompt
from wikiarena.analysis import inspect_run_token_usage
from wikiarena.protocol import ModelCallMetrics
from wikiarena.protocol import RunResult
from wikiarena.protocol import StepAttemptRecord
from wikiarena.protocol import StepOutcome
from wikiarena.protocol import TerminalOutcome
from wikiarena.protocol import TerminationReason


def test_build_page_links_prompt_and_token_estimate() -> None:
    prompt = build_page_links_prompt(
        title="Apple",
        links=["Fruit", "Tree"],
    )

    assert "Apple" in prompt
    assert "Fruit" in prompt
    assert approximate_token_count(prompt) >= 1


def test_inspect_run_token_usage_reads_metrics(
    tmp_path,
) -> None:
    results_path = tmp_path / "results.jsonl"
    run_result = RunResult(
        run_id="run-1",
        race_id="race-1",
        benchmark_id="benchmark-1",
        task_id="en__apple__fruit",
        participant_id="participant-1",
        terminal_outcome=TerminalOutcome.SUCCESS,
        termination_reason=TerminationReason.TASK_COMPLETED,
        step_attempts=[
            StepAttemptRecord(
                step_index=1,
                move_index=1,
                from_page_title="Apple",
                selected_link_text="Fruit",
                requested_to_page_title="Fruit",
                resolved_to_page_title="Fruit",
                outcome=StepOutcome.MOVE_COMMITTED,
                consumed_step_budget=True,
                model_metrics=ModelCallMetrics(
                    input_tokens=100,
                    output_tokens=20,
                    total_tokens=120,
                    response_time_ms=500.0,
                ),
            ),
        ],
        started_at=datetime(2026, 1, 1, 0, 0, 0),
        ended_at=datetime(2026, 1, 1, 0, 0, 1),
    )
    results_path.write_text(
        json.dumps(
            run_result.model_dump(mode="json"),
        )
        + "\n",
        encoding="utf-8",
    )

    summary = inspect_run_token_usage(
        str(results_path),
    )

    assert len(summary.runs) == 1
    assert summary.runs[0].total_input_tokens == 100
    assert summary.runs[0].max_input_tokens_per_step == 100
