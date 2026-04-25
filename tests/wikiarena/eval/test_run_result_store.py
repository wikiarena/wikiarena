from __future__ import annotations

import json
from datetime import datetime

from wikiarena.eval import RunResultStore, inspect_result_file_identity
from wikiarena.protocol import (
    NavigationBackend,
    RunResult,
    SolverBackend,
    TerminalOutcome,
    TerminationReason,
)


def test_run_result_store_appends_jsonl_records(
    tmp_path,
) -> None:
    output_path = tmp_path / "results" / "run_results.jsonl"
    store = RunResultStore(
        output_path=output_path,
    )

    run_result = RunResult(
        run_id="run_1",
        race_id="race_1",
        benchmark_id="benchmark_1",
        task_id="en__apple__banana",
        participant_id="participant_1",
        terminal_outcome=TerminalOutcome.SUCCESS,
        termination_reason=TerminationReason.TASK_COMPLETED,
        step_attempts=[],
        started_at=datetime(2026, 1, 1, 0, 0, 0),
        ended_at=datetime(2026, 1, 1, 0, 0, 1),
    )

    store.append_run_result(
        run_result,
    )
    store.append_run_result(
        run_result.model_copy(
            update={"run_id": "run_2"},
        ),
    )

    lines = output_path.read_text(
        encoding="utf-8",
    ).splitlines()
    assert len(lines) == 2

    first_record = json.loads(
        lines[0],
    )
    second_record = json.loads(
        lines[1],
    )
    assert first_record["run_id"] == "run_1"
    assert second_record["run_id"] == "run_2"


def test_inspect_result_file_identity_collects_ruleset_and_taskset_hashes(
    tmp_path,
) -> None:
    output_path = tmp_path / "results" / "run_results.jsonl"
    store = RunResultStore(
        output_path=output_path,
    )

    store.append_run_result(
        RunResult(
            run_id="run_1",
            race_id="race_1",
            benchmark_id="benchmark_1",
            task_id="en__apple__banana",
            participant_id="participant_1",
            terminal_outcome=TerminalOutcome.SUCCESS,
            termination_reason=TerminationReason.TASK_COMPLETED,
            step_attempts=[],
            ruleset_hash="ruleset_a",
            taskset_hash="taskset_a",
            started_at=datetime(2026, 1, 1, 0, 0, 0),
            ended_at=datetime(2026, 1, 1, 0, 0, 1),
        ),
    )
    store.append_run_result(
        RunResult(
            run_id="run_2",
            race_id="race_2",
            benchmark_id="benchmark_1",
            task_id="en__cat__dog",
            participant_id="participant_2",
            terminal_outcome=TerminalOutcome.SUCCESS,
            termination_reason=TerminationReason.TASK_COMPLETED,
            step_attempts=[],
            ruleset_hash="ruleset_a",
            taskset_hash="taskset_b",
            started_at=datetime(2026, 1, 1, 0, 0, 0),
            ended_at=datetime(2026, 1, 1, 0, 0, 1),
        ),
    )

    identity = inspect_result_file_identity(
        output_path,
    )

    assert identity.total_runs == 2
    assert identity.ruleset_hashes == ["ruleset_a"]
    assert identity.taskset_hashes == ["taskset_a", "taskset_b"]


def test_inspect_result_file_identity_collects_navigation_and_solver_provenance(
    tmp_path,
) -> None:
    output_path = tmp_path / "results" / "run_results.jsonl"
    store = RunResultStore(
        output_path=output_path,
    )

    store.append_run_result(
        RunResult(
            run_id="run_1",
            race_id="race_1",
            benchmark_id="benchmark_1",
            task_id="en__apple__banana",
            participant_id="participant_1",
            terminal_outcome=TerminalOutcome.SUCCESS,
            termination_reason=TerminationReason.TASK_COMPLETED,
            step_attempts=[],
            navigation_backend=NavigationBackend.LIVE,
            solver_backend=SolverBackend.LOCAL,
            solver_snapshot_id="enwiki-20260301",
            started_at=datetime(2026, 1, 1, 0, 0, 0),
            ended_at=datetime(2026, 1, 1, 0, 0, 1),
        ),
    )

    identity = inspect_result_file_identity(
        output_path,
    )

    assert identity.navigation_backends == ["live"]
    assert identity.solver_backends == ["local"]
    assert identity.solver_snapshot_ids == ["enwiki-20260301"]
