from datetime import datetime

import pytest
from pydantic import ValidationError

from wikiarena.protocol import HarnessConfig
from wikiarena.protocol import ResponseContract
from wikiarena.protocol import NavigationRules
from wikiarena.protocol import RunResult
from wikiarena.protocol import SolverShortestPath
from wikiarena.protocol import StepAttemptRecord
from wikiarena.protocol import StepOutcome
from wikiarena.protocol import TaskSpec
from wikiarena.protocol import TaskExecutionAnnotation
from wikiarena.protocol import TaskExecutionAnnotationStatus
from wikiarena.protocol import TerminalOutcome
from wikiarena.protocol import TerminationReason


def test_task_spec_rejects_same_start_and_target_title() -> None:
    with pytest.raises(
        ValidationError,
        match="must be different",
    ):
        TaskSpec(
            language="en",
            start_page_title="Apple",
            target_page_title="Apple",
        )


def test_task_spec_derives_shortest_path_length_from_solver_shortest_path() -> None:
    task_spec = TaskSpec(
        language="en",
        start_page_title="Apple",
        target_page_title="Banana",
        solver_shortest_path=SolverShortestPath(
            page_titles=["Apple", "Fruit", "Banana"],
            computed_at=datetime(2026, 1, 1, 0, 0, 0),
            solver_snapshot_id="enwiki-20260301",
        ),
    )

    assert task_spec.shortest_path_length == 2


def test_task_spec_rejects_mismatched_shortest_path_length() -> None:
    with pytest.raises(
        ValidationError,
        match="shortest_path_length must equal len\\(solver_shortest_path.page_titles\\) - 1",
    ):
        TaskSpec(
            language="en",
            start_page_title="Apple",
            target_page_title="Banana",
            shortest_path_length=1,
            solver_shortest_path=SolverShortestPath(
                page_titles=["Apple", "Fruit", "Banana"],
                computed_at=datetime(2026, 1, 1, 0, 0, 0),
            ),
        )


def test_task_spec_rejects_legacy_reference_paths_field() -> None:
    with pytest.raises(
        ValidationError,
        match="reference_paths",
    ):
        TaskSpec.model_validate(
            {
                "language": "en",
                "start_page_title": "Apple",
                "target_page_title": "Banana",
                "reference_paths": [],
            },
        )


def test_harness_config_supports_minimal_v1_fields() -> None:
    harness_config = HarnessConfig(
        harness_id="tool_strict_v1",
        response_contract=ResponseContract.TOOL_CALL_ONLY,
        tool_name="navigate",
    )

    assert harness_config.harness_id == "tool_strict_v1"
    assert harness_config.response_contract == ResponseContract.TOOL_CALL_ONLY


def test_navigation_rules_expose_derived_max_step_attempts() -> None:
    rules = NavigationRules(
        max_moves=20,
        max_invalid_attempts_per_run=8,
        invalid_attempt_consumes_step_budget=False,
    )
    assert rules.derived_max_step_attempts == 28


def test_navigation_rules_defaults_match_current_benchmark_ruleset() -> None:
    rules = NavigationRules()

    assert rules.max_moves == 50
    assert rules.max_invalid_attempts_per_run == 15
    assert rules.max_invalid_attempts_per_step_context == 2
    assert rules.invalid_attempt_consumes_step_budget is False
    assert rules.derived_max_step_attempts == 65


def test_step_attempt_requires_move_index_for_committed_move() -> None:
    with pytest.raises(
        ValidationError,
        match="move_index is required",
    ):
        StepAttemptRecord(
            step_index=1,
            from_page_title="Apple",
            outcome=StepOutcome.MOVE_COMMITTED,
            resolved_to_page_title="Banana",
        )


def test_run_result_derives_counts_and_ranking_for_success() -> None:
    run_result = RunResult(
        run_id="run-1",
        race_id="race-1",
        benchmark_id="benchmark-1",
        task_id="en__apple__banana",
        participant_id="participant-1",
        terminal_outcome=TerminalOutcome.SUCCESS,
        termination_reason=TerminationReason.TASK_COMPLETED,
        step_attempts=[
            StepAttemptRecord(
                step_index=1,
                from_page_title="Apple",
                selected_link_text="Bananas",
                outcome=StepOutcome.INVALID_LINK,
                rejection_reason_code="rule.link_not_present",
                consumed_invalid_budget=True,
                consumed_step_budget=False,
            ),
            StepAttemptRecord(
                step_index=2,
                move_index=1,
                from_page_title="Apple",
                selected_link_text="Banana",
                requested_to_page_title="Banana",
                resolved_to_page_title="Banana",
                outcome=StepOutcome.MOVE_COMMITTED,
                consumed_invalid_budget=False,
                consumed_step_budget=True,
            ),
        ],
        started_at=datetime(2026, 1, 1, 0, 0, 0),
        ended_at=datetime(2026, 1, 1, 0, 0, 1),
    )

    assert run_result.total_step_attempts == 2
    assert run_result.total_committed_moves == 1
    assert run_result.total_invalid_attempts == 1
    assert run_result.ranking_eligible is True
    assert run_result.ranking_exclusion_reason is None
    assert run_result.duration_ms == 1000.0
    assert len(run_result.committed_moves) == 1


def test_run_result_excludes_system_failure_from_ranking() -> None:
    run_result = RunResult(
        run_id="run-2",
        race_id="race-1",
        benchmark_id="benchmark-1",
        task_id="en__apple__banana",
        participant_id="participant-1",
        terminal_outcome=TerminalOutcome.SYSTEM_FAILURE,
        termination_reason=TerminationReason.INFRASTRUCTURE_ERROR,
        step_attempts=[],
        started_at=datetime(2026, 1, 1, 0, 0, 0),
        ended_at=datetime(2026, 1, 1, 0, 0, 0),
    )

    assert run_result.ranking_eligible is False
    assert run_result.ranking_exclusion_reason == "infrastructure_error"


def test_task_execution_annotation_requires_distance_for_ok_status() -> None:
    with pytest.raises(
        ValidationError,
        match="shortest_path_length is required",
    ):
        TaskExecutionAnnotation(
            status=TaskExecutionAnnotationStatus.OK,
        )


def test_task_execution_annotation_rejects_distance_for_missing_status() -> None:
    with pytest.raises(
        ValidationError,
        match="must be null",
    ):
        TaskExecutionAnnotation(
            status=TaskExecutionAnnotationStatus.TARGET_MISSING_IN_SOLVER,
            shortest_path_length=3,
        )


def test_solver_shortest_path_rejects_legacy_snapshot_field_name() -> None:
    with pytest.raises(
        ValidationError,
        match="valid_for_solver_snapshot_id",
    ):
        SolverShortestPath.model_validate(
            {
                "page_titles": ["Apple", "Banana"],
                "computed_at": datetime(2026, 1, 1, 0, 0, 0),
                "valid_for_solver_snapshot_id": "enwiki-20260301",
            },
        )


def test_run_result_rejects_legacy_runtime_field_names() -> None:
    with pytest.raises(
        ValidationError,
        match="solver_mode",
    ):
        RunResult.model_validate(
            {
                "run_id": "run-3",
                "race_id": "race-1",
                "benchmark_id": "benchmark-1",
                "task_id": "en__apple__banana",
                "participant_id": "participant-1",
                "terminal_outcome": TerminalOutcome.SUCCESS,
                "termination_reason": TerminationReason.TASK_COMPLETED,
                "step_attempts": [],
                "solver_mode": "local",
                "started_at": datetime(2026, 1, 1, 0, 0, 0),
                "ended_at": datetime(2026, 1, 1, 0, 0, 1),
            },
        )
