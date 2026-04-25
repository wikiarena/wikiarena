from __future__ import annotations

import asyncio
from typing import Sequence

import pytest

from wikiarena.core import (
    NavigationResolution,
    PageSnapshot,
    ParticipantDecision,
    RunExecutor,
)
from wikiarena.protocol import (
    HarnessConfig,
    NavigationRules,
    ResponseContract,
    RunEventType,
    RunSpec,
    ScoringRules,
    SolverBackend,
    StepOutcome,
    TaskExecutionAnnotation,
    TaskExecutionAnnotationStatus,
    TaskSpec,
    TerminalOutcome,
    TerminationReason,
)
from wikiarena.solver.models import PositionSolverFacts


class StubParticipant:
    def __init__(
        self,
        link_choices: Sequence[str | None],
    ):
        self._link_choices = list(
            link_choices,
        )
        self.feedback_count = 0

    async def choose_link(
        self,
        task,
        current_page,
        harness_config,
    ) -> ParticipantDecision:
        if not self._link_choices:
            return ParticipantDecision(
                selected_link_text=None,
                tool_call_name="navigate",
            )
        return ParticipantDecision(
            selected_link_text=self._link_choices.pop(0),
            tool_call_name="navigate",
        )

    async def record_step_feedback(
        self,
        *,
        step_attempt,
    ) -> None:
        self.feedback_count += 1


class StubWikiNavigator:
    def __init__(
        self,
        page_links: dict[str, list[str]],
        resolution_map: dict[tuple[str, str], str],
    ):
        self._page_links = page_links
        self._resolution_map = resolution_map

    async def get_page_snapshot(
        self,
        language,
        page_title,
        link_policy,
    ) -> PageSnapshot:
        return PageSnapshot(
            title=page_title,
            language=language,
            links=self._page_links[page_title],
        )

    async def resolve_navigation(
        self,
        language,
        from_page_title,
        selected_link_text,
    ) -> NavigationResolution:
        resolved_target = self._resolution_map.get(
            (from_page_title, selected_link_text),
            selected_link_text,
        )
        return NavigationResolution(
            requested_to_page_title=selected_link_text,
            resolved_to_page_title=resolved_target,
            was_redirect=resolved_target != selected_link_text,
        )


@pytest.mark.asyncio
async def test_run_executor_records_invalid_attempt_then_successful_move() -> None:
    task_spec = TaskSpec(
        language="en",
        start_page_title="Apple",
        target_page_title="Banana",
    )
    run_spec = RunSpec(
        run_id="run-1",
        benchmark_id="benchmark-1",
        race_id="race-1",
        task_id=task_spec.task_id,
        participant_id="participant-1",
        navigation_rules=NavigationRules(
            max_moves=5,
            max_invalid_attempts_per_run=2,
            max_invalid_attempts_per_step_context=2,
        ),
    )

    participant = StubParticipant(
        link_choices=[
            "Not On Page",
            "Banana",
        ],
    )
    wiki_navigator = StubWikiNavigator(
        page_links={
            "Apple": ["Banana"],
            "Banana": [],
        },
        resolution_map={
            ("Apple", "Banana"): "Banana",
        },
    )

    artifact = await RunExecutor().execute_run(
        run_spec=run_spec,
        task_spec=task_spec,
        participant=participant,
        wiki_navigator=wiki_navigator,
        harness_id="tool_strict_v1",
        harness_config=HarnessConfig(
            harness_id="tool_strict_v1",
        ),
        scoring_rules=ScoringRules(),
    )

    run_result = artifact.run_result
    assert run_result.terminal_outcome == TerminalOutcome.SUCCESS
    assert run_result.termination_reason == TerminationReason.TASK_COMPLETED
    assert run_result.total_step_attempts == 2
    assert run_result.total_committed_moves == 1
    assert run_result.total_invalid_attempts == 1
    assert participant.feedback_count == 2

    event_types = [event.event_type for event in artifact.events]
    assert event_types[0] == RunEventType.RUN_STARTED
    assert RunEventType.STEP_ATTEMPT_RECORDED in event_types
    assert RunEventType.RUN_TERMINATED in event_types


@pytest.mark.asyncio
async def test_run_executor_terminates_when_invalid_budget_exhausted() -> None:
    task_spec = TaskSpec(
        language="en",
        start_page_title="Apple",
        target_page_title="Banana",
    )
    run_spec = RunSpec(
        run_id="run-2",
        benchmark_id="benchmark-1",
        race_id="race-1",
        task_id=task_spec.task_id,
        participant_id="participant-2",
        navigation_rules=NavigationRules(
            max_moves=5,
            max_invalid_attempts_per_run=1,
            max_invalid_attempts_per_step_context=5,
        ),
    )

    participant = StubParticipant(
        link_choices=[
            "X",
            "Y",
            "Banana",
        ],
    )
    wiki_navigator = StubWikiNavigator(
        page_links={
            "Apple": ["Banana"],
            "Banana": [],
        },
        resolution_map={
            ("Apple", "Banana"): "Banana",
        },
    )

    artifact = await RunExecutor().execute_run(
        run_spec=run_spec,
        task_spec=task_spec,
        participant=participant,
        wiki_navigator=wiki_navigator,
        harness_id="tool_strict_v1",
        harness_config=HarnessConfig(
            harness_id="tool_strict_v1",
        ),
        scoring_rules=ScoringRules(),
    )

    run_result = artifact.run_result
    assert run_result.terminal_outcome == TerminalOutcome.MODEL_FAILURE
    assert run_result.termination_reason == TerminationReason.INVALID_BUDGET_EXHAUSTED
    assert run_result.total_step_attempts == 2
    assert run_result.total_invalid_attempts == 2
    assert run_result.ranking_eligible is True


class WrongToolParticipant:
    async def choose_link(
        self,
        task,
        current_page,
        harness_config,
    ) -> ParticipantDecision:
        return ParticipantDecision(
            selected_link_text="Banana",
            tool_call_name="not_navigate",
        )


class StructuredModeToolParticipant:
    async def choose_link(
        self,
        task,
        current_page,
        harness_config,
    ) -> ParticipantDecision:
        return ParticipantDecision(
            selected_link_text="Banana",
            tool_call_name="navigate",
        )


class ToolCallRequiredViolationParticipant:
    async def choose_link(
        self,
        task,
        current_page,
        harness_config,
    ) -> ParticipantDecision:
        return ParticipantDecision(
            selected_link_text="Banana",
            tool_call_name=None,
        )


class MultipleToolCallsParticipant:
    async def choose_link(
        self,
        task,
        current_page,
        harness_config,
    ) -> ParticipantDecision:
        return ParticipantDecision(
            selected_link_text="Banana",
            tool_call_name="navigate",
            tool_call_id="tc_1",
            tool_call_count=2,
            tool_call_ids=["tc_1", "tc_2"],
            tool_call_names=["navigate", "navigate"],
        )


@pytest.mark.asyncio
async def test_run_executor_marks_wrong_tool_as_invalid_attempt() -> None:
    task_spec = TaskSpec(
        language="en",
        start_page_title="Apple",
        target_page_title="Banana",
    )
    run_spec = RunSpec(
        run_id="run-3",
        benchmark_id="benchmark-1",
        race_id="race-1",
        task_id=task_spec.task_id,
        participant_id="participant-3",
        navigation_rules=NavigationRules(
            max_moves=5,
            max_invalid_attempts_per_run=0,
            max_invalid_attempts_per_step_context=0,
        ),
    )

    artifact = await RunExecutor().execute_run(
        run_spec=run_spec,
        task_spec=task_spec,
        participant=WrongToolParticipant(),
        wiki_navigator=StubWikiNavigator(
            page_links={
                "Apple": ["Banana"],
                "Banana": [],
            },
            resolution_map={
                ("Apple", "Banana"): "Banana",
            },
        ),
        harness_id="tool_strict_v1",
        harness_config=HarnessConfig(
            harness_id="tool_strict_v1",
            tool_name="navigate",
        ),
        scoring_rules=ScoringRules(),
    )

    run_result = artifact.run_result
    assert run_result.terminal_outcome == TerminalOutcome.MODEL_FAILURE
    assert run_result.termination_reason == TerminationReason.INVALID_BUDGET_EXHAUSTED
    assert run_result.total_step_attempts == 1
    assert run_result.step_attempts[0].outcome.value == "tool_not_allowed"


@pytest.mark.asyncio
async def test_run_executor_rejects_multiple_tool_calls_without_navigation() -> None:
    task_spec = TaskSpec(
        language="en",
        start_page_title="Apple",
        target_page_title="Banana",
    )
    run_spec = RunSpec(
        run_id="run-multiple-tool-calls-1",
        benchmark_id="benchmark-1",
        race_id="race-1",
        task_id=task_spec.task_id,
        participant_id="participant-multiple-tool-calls-1",
        navigation_rules=NavigationRules(
            max_moves=5,
            max_invalid_attempts_per_run=0,
            max_invalid_attempts_per_step_context=0,
        ),
    )

    artifact = await RunExecutor().execute_run(
        run_spec=run_spec,
        task_spec=task_spec,
        participant=MultipleToolCallsParticipant(),
        wiki_navigator=StubWikiNavigator(
            page_links={
                "Apple": ["Banana", "Cherry"],
                "Banana": [],
            },
            resolution_map={
                ("Apple", "Banana"): "Banana",
            },
        ),
        harness_id="tool_strict_v1",
        harness_config=HarnessConfig(
            harness_id="tool_strict_v1",
            tool_name="navigate",
        ),
        scoring_rules=ScoringRules(),
    )

    run_result = artifact.run_result
    assert run_result.terminal_outcome == TerminalOutcome.MODEL_FAILURE
    assert run_result.termination_reason == TerminationReason.INVALID_BUDGET_EXHAUSTED
    assert run_result.current_page_title == "Apple"
    assert run_result.total_step_attempts == 1
    assert run_result.total_committed_moves == 0
    step_attempt = run_result.step_attempts[0]
    assert step_attempt.outcome == StepOutcome.MALFORMED_TOOL_CALL
    assert step_attempt.rejection_reason_code == "harness.multiple_tool_calls"
    assert step_attempt.resolved_to_page_title is None
    assert step_attempt.error is not None
    assert step_attempt.error.code == "harness.multiple_tool_calls"
    assert step_attempt.error.details["tool_call_count"] == 2


@pytest.mark.asyncio
async def test_run_executor_does_not_reject_tool_fields_in_structured_mode() -> None:
    task_spec = TaskSpec(
        language="en",
        start_page_title="Apple",
        target_page_title="Banana",
    )
    run_spec = RunSpec(
        run_id="run-structured-1",
        benchmark_id="benchmark-1",
        race_id="race-1",
        task_id=task_spec.task_id,
        participant_id="participant-structured-1",
        navigation_rules=NavigationRules(
            max_moves=5,
            max_invalid_attempts_per_run=2,
            max_invalid_attempts_per_step_context=2,
        ),
    )

    artifact = await RunExecutor().execute_run(
        run_spec=run_spec,
        task_spec=task_spec,
        participant=StructuredModeToolParticipant(),
        wiki_navigator=StubWikiNavigator(
            page_links={
                "Apple": ["Banana"],
                "Banana": [],
            },
            resolution_map={
                ("Apple", "Banana"): "Banana",
            },
        ),
        harness_id="structured_v1",
        harness_config=HarnessConfig(
            harness_id="structured_v1",
            response_contract=ResponseContract.STRUCTURED_OUTPUT_ONLY,
            tool_name="navigate",
        ),
        scoring_rules=ScoringRules(),
    )

    run_result = artifact.run_result
    assert run_result.terminal_outcome == TerminalOutcome.SUCCESS
    assert run_result.termination_reason == TerminationReason.TASK_COMPLETED


@pytest.mark.asyncio
async def test_run_executor_enforces_tool_call_only_contract() -> None:
    task_spec = TaskSpec(
        language="en",
        start_page_title="Apple",
        target_page_title="Banana",
    )
    run_spec = RunSpec(
        run_id="run-tool-contract-1",
        benchmark_id="benchmark-1",
        race_id="race-1",
        task_id=task_spec.task_id,
        participant_id="participant-tool-contract-1",
        navigation_rules=NavigationRules(
            max_moves=5,
            max_invalid_attempts_per_run=0,
            max_invalid_attempts_per_step_context=0,
        ),
    )

    artifact = await RunExecutor().execute_run(
        run_spec=run_spec,
        task_spec=task_spec,
        participant=ToolCallRequiredViolationParticipant(),
        wiki_navigator=StubWikiNavigator(
            page_links={
                "Apple": ["Banana"],
                "Banana": [],
            },
            resolution_map={
                ("Apple", "Banana"): "Banana",
            },
        ),
        harness_id="tool_v1",
        harness_config=HarnessConfig(
            harness_id="tool_v1",
            response_contract=ResponseContract.TOOL_CALL_ONLY,
            tool_name="navigate",
        ),
        scoring_rules=ScoringRules(),
    )

    run_result = artifact.run_result
    assert run_result.termination_reason == TerminationReason.INVALID_BUDGET_EXHAUSTED
    assert (
        run_result.step_attempts[0].rejection_reason_code
        == "harness.tool_call_required"
    )


@pytest.mark.asyncio
async def test_run_executor_streams_events_to_sink_during_execution() -> None:
    task_spec = TaskSpec(
        language="en",
        start_page_title="Apple",
        target_page_title="Banana",
    )
    run_spec = RunSpec(
        run_id="run-4",
        benchmark_id="benchmark-1",
        race_id="race-1",
        task_id=task_spec.task_id,
        participant_id="participant-4",
        navigation_rules=NavigationRules(
            max_moves=5,
            max_invalid_attempts_per_run=1,
            max_invalid_attempts_per_step_context=1,
        ),
    )

    observed_event_types = []

    async def event_sink(event) -> None:
        observed_event_types.append(
            event.event_type,
        )

    artifact = await RunExecutor().execute_run(
        run_spec=run_spec,
        task_spec=task_spec,
        participant=StubParticipant(
            link_choices=["Banana"],
        ),
        wiki_navigator=StubWikiNavigator(
            page_links={
                "Apple": ["Banana"],
                "Banana": [],
            },
            resolution_map={
                ("Apple", "Banana"): "Banana",
            },
        ),
        harness_id="tool_strict_v1",
        harness_config=HarnessConfig(
            harness_id="tool_strict_v1",
        ),
        scoring_rules=ScoringRules(),
        event_sink=event_sink,
    )

    emitted_types = [event.event_type for event in artifact.events]
    assert observed_event_types == emitted_types


@pytest.mark.asyncio
async def test_run_executor_terminates_with_dead_end_when_page_has_no_links() -> None:
    task_spec = TaskSpec(
        language="en",
        start_page_title="Dead End",
        target_page_title="Banana",
    )
    run_spec = RunSpec(
        run_id="run-dead-end-1",
        benchmark_id="benchmark-1",
        race_id="race-1",
        task_id=task_spec.task_id,
        participant_id="participant-dead-end-1",
        navigation_rules=NavigationRules(),
    )

    artifact = await RunExecutor().execute_run(
        run_spec=run_spec,
        task_spec=task_spec,
        participant=StubParticipant(
            link_choices=["Banana"],
        ),
        wiki_navigator=StubWikiNavigator(
            page_links={
                "Dead End": [],
            },
            resolution_map={},
        ),
        harness_id="tool_strict_v1",
        harness_config=HarnessConfig(
            harness_id="tool_strict_v1",
        ),
        scoring_rules=ScoringRules(),
        solver_backend=SolverBackend.NONE,
    )

    assert artifact.run_result.terminal_outcome == TerminalOutcome.MODEL_FAILURE
    assert artifact.run_result.termination_reason == TerminationReason.DEAD_END
    assert artifact.run_result.total_step_attempts == 0


class FailingWikiNavigator:
    async def get_page_snapshot(
        self,
        language,
        page_title,
        link_policy,
    ):
        raise RuntimeError("wiki unavailable")

    async def resolve_navigation(
        self,
        language,
        from_page_title,
        selected_link_text,
    ):
        raise RuntimeError("not used")


class CountingSolverTargetSession:
    def __init__(
        self,
        distances_by_page: dict[str, int],
    ):
        self._distances_by_page = distances_by_page
        self.lookup_calls: list[str] = []

    async def get_shortest_path_length(
        self,
        start_page: str,
    ) -> int:
        self.lookup_calls.append(
            start_page,
        )
        return self._distances_by_page[start_page]

    async def get_position_solver_facts(
        self,
        start_page: str,
    ) -> PositionSolverFacts:
        self.lookup_calls.append(
            start_page,
        )
        distance = self._distances_by_page[start_page]
        return PositionSolverFacts(
            page_title=start_page,
            target_page_title="Banana",
            shortest_path_length=distance,
            shortest_paths=[
                [
                    start_page,
                    "Banana",
                ]
            ],
            shortest_next_hop_titles=[
                "Banana",
            ],
        )


class SlowSolverTargetSession:
    def __init__(
        self,
        *,
        solver_started: asyncio.Event,
        release_solver: asyncio.Event,
    ):
        self.target_page = "Banana"
        self.solver_started = solver_started
        self.release_solver = release_solver

    async def get_shortest_path_length(
        self,
        start_page: str,
    ) -> int:
        return 1

    async def get_position_solver_facts(
        self,
        start_page: str,
    ) -> PositionSolverFacts:
        if start_page == "Cherry":
            self.solver_started.set()
            await self.release_solver.wait()
            distance = 1
        else:
            distance = 0
        return PositionSolverFacts(
            page_title=start_page,
            target_page_title="Banana",
            shortest_path_length=distance,
            shortest_paths=[
                [
                    start_page,
                    "Banana",
                ]
            ],
            shortest_next_hop_titles=[
                "Banana",
            ],
        )


class ObservingParticipant:
    def __init__(
        self,
        *,
        second_choose_started: asyncio.Event,
    ):
        self.second_choose_started = second_choose_started
        self.observed_pages: list[str] = []

    async def choose_link(
        self,
        task,
        current_page,
        harness_config,
    ) -> ParticipantDecision:
        self.observed_pages.append(
            current_page.title,
        )
        if current_page.title == "Cherry":
            self.second_choose_started.set()
            return ParticipantDecision(
                selected_link_text="Banana",
                tool_call_name="navigate",
            )
        return ParticipantDecision(
            selected_link_text="Cherry",
            tool_call_name="navigate",
        )

    async def record_step_feedback(
        self,
        *,
        step_attempt,
    ) -> None:
        return None


@pytest.mark.asyncio
async def test_run_executor_respects_scoring_rule_for_system_failures() -> None:
    task_spec = TaskSpec(
        language="en",
        start_page_title="Apple",
        target_page_title="Banana",
    )
    run_spec = RunSpec(
        run_id="run-scoring-1",
        benchmark_id="benchmark-1",
        race_id="race-1",
        task_id=task_spec.task_id,
        participant_id="participant-scoring-1",
        navigation_rules=NavigationRules(),
    )

    artifact = await RunExecutor().execute_run(
        run_spec=run_spec,
        task_spec=task_spec,
        participant=StubParticipant(
            link_choices=["Banana"],
        ),
        wiki_navigator=FailingWikiNavigator(),
        harness_id="tool_strict_v1",
        harness_config=HarnessConfig(
            harness_id="tool_strict_v1",
        ),
        scoring_rules=ScoringRules(
            exclude_system_failures_from_ranking=False,
        ),
        solver_backend=SolverBackend.NONE,
    )

    assert artifact.run_result.terminal_outcome == TerminalOutcome.SYSTEM_FAILURE
    assert artifact.run_result.ranking_eligible is True
    assert artifact.run_result.ranking_exclusion_reason is None


@pytest.mark.asyncio
async def test_run_executor_populates_committed_move_solver_metrics_with_cached_distances() -> (
    None
):
    task_spec = TaskSpec(
        language="en",
        start_page_title="Apple",
        target_page_title="Banana",
    )
    run_spec = RunSpec(
        run_id="run-solver-metrics-1",
        benchmark_id="benchmark-1",
        race_id="race-1",
        task_id=task_spec.task_id,
        participant_id="participant-solver-metrics-1",
        navigation_rules=NavigationRules(
            max_moves=5,
            max_invalid_attempts_per_run=2,
            max_invalid_attempts_per_step_context=2,
        ),
    )

    participant = StubParticipant(
        link_choices=[
            "Cherry",
            "Apple",
            "Banana",
        ],
    )
    wiki_navigator = StubWikiNavigator(
        page_links={
            "Apple": ["Cherry", "Banana"],
            "Cherry": ["Apple"],
            "Banana": [],
        },
        resolution_map={
            ("Apple", "Cherry"): "Cherry",
            ("Cherry", "Apple"): "Apple",
            ("Apple", "Banana"): "Banana",
        },
    )
    solver_target_session = CountingSolverTargetSession(
        distances_by_page={
            "Cherry": 2,
            "Banana": 0,
        },
    )

    artifact = await RunExecutor().execute_run(
        run_spec=run_spec,
        task_spec=task_spec,
        participant=participant,
        wiki_navigator=wiki_navigator,
        harness_id="tool_strict_v1",
        harness_config=HarnessConfig(
            harness_id="tool_strict_v1",
        ),
        scoring_rules=ScoringRules(),
        solver_backend=SolverBackend.LOCAL,
        task_execution_annotation=TaskExecutionAnnotation(
            status=TaskExecutionAnnotationStatus.OK,
            shortest_path_length=1,
        ),
        initial_position_solver_facts=PositionSolverFacts(
            page_title="Apple",
            target_page_title="Banana",
            shortest_path_length=1,
            shortest_paths=[
                [
                    "Apple",
                    "Banana",
                ],
            ],
            shortest_next_hop_titles=[
                "Banana",
            ],
        ),
        solver_target_session=solver_target_session,
    )

    committed_steps = artifact.run_result.step_attempts
    assert [step.solver_metrics.distance_before for step in committed_steps] == [
        1,
        2,
        1,
    ]
    assert [step.solver_metrics.distance_after for step in committed_steps] == [2, 1, 0]
    assert solver_target_session.lookup_calls == ["Cherry", "Banana"]
    solver_fact_events = [
        event
        for event in artifact.events
        if event.event_type == RunEventType.POSITION_SOLVER_FACTS_RECORDED
    ]
    assert solver_fact_events[0].payload["step_index"] == 0
    assert solver_fact_events[0].payload["move_index"] == 0


@pytest.mark.asyncio
async def test_run_executor_does_not_block_next_turn_on_solver_facts() -> None:
    task_spec = TaskSpec(
        language="en",
        start_page_title="Apple",
        target_page_title="Banana",
    )
    run_spec = RunSpec(
        run_id="run-solver-nonblocking-1",
        benchmark_id="benchmark-1",
        race_id="race-1",
        task_id=task_spec.task_id,
        participant_id="participant-solver-nonblocking-1",
        navigation_rules=NavigationRules(
            max_moves=5,
            max_invalid_attempts_per_run=2,
            max_invalid_attempts_per_step_context=2,
        ),
    )
    solver_started = asyncio.Event()
    release_solver = asyncio.Event()
    second_choose_started = asyncio.Event()

    run_task = asyncio.create_task(
        RunExecutor().execute_run(
            run_spec=run_spec,
            task_spec=task_spec,
            participant=ObservingParticipant(
                second_choose_started=second_choose_started,
            ),
            wiki_navigator=StubWikiNavigator(
                page_links={
                    "Apple": ["Cherry"],
                    "Cherry": ["Banana"],
                    "Banana": [],
                },
                resolution_map={
                    ("Apple", "Cherry"): "Cherry",
                    ("Cherry", "Banana"): "Banana",
                },
            ),
            harness_id="tool_strict_v1",
            harness_config=HarnessConfig(
                harness_id="tool_strict_v1",
            ),
            scoring_rules=ScoringRules(),
            solver_backend=SolverBackend.LOCAL,
            task_execution_annotation=TaskExecutionAnnotation(
                status=TaskExecutionAnnotationStatus.OK,
                shortest_path_length=2,
            ),
            solver_target_session=SlowSolverTargetSession(
                solver_started=solver_started,
                release_solver=release_solver,
            ),
        ),
    )

    await asyncio.wait_for(
        solver_started.wait(),
        timeout=1,
    )
    await asyncio.wait_for(
        second_choose_started.wait(),
        timeout=1,
    )
    release_solver.set()

    artifact = await run_task

    assert artifact.run_result.terminal_outcome == TerminalOutcome.SUCCESS
