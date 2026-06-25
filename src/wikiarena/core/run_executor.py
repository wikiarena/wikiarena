from __future__ import annotations

import asyncio
import inspect
from datetime import datetime
from typing import Awaitable, Callable

from pydantic import BaseModel, Field

from wikiarena.core.interfaces import (
    ParticipantDecision,
    ParticipantDriver,
    WikiNavigator,
)
from wikiarena.protocol.enums import (
    NavigationBackend,
    ResponseContract,
    RunEventType,
    SolverBackend,
    StepOutcome,
    TaskExecutionAnnotationStatus,
    TerminalOutcome,
    TerminationReason,
)
from wikiarena.protocol.errors import ErrorRecord
from wikiarena.protocol.events import EventEnvelope
from wikiarena.protocol.results import (
    RunResult,
    StepAttemptRecord,
    StepSolverMetrics,
    TaskExecutionAnnotation,
)
from wikiarena.protocol.rules import HarnessConfig, ScoringRules
from wikiarena.protocol.specs import RunSpec, TaskSpec
from wikiarena.protocol.version import DEFAULT_PROTOCOL_VERSION
from wikiarena.solver.backend import SolverTargetSession
from wikiarena.solver.models import PositionSolverFacts

EventSink = Callable[[EventEnvelope], Awaitable[None] | None]


class RunExecutionArtifact(BaseModel):
    run_result: RunResult
    events: list[EventEnvelope] = Field(
        default_factory=list,
    )


class RunExecutor:
    def __init__(
        self,
        *,
        protocol_version: str = DEFAULT_PROTOCOL_VERSION,
        engine_commit: str | None = None,
    ):
        self.protocol_version = protocol_version
        self.engine_commit = engine_commit

    async def execute_run(
        self,
        *,
        run_spec: RunSpec,
        task_spec: TaskSpec,
        participant: ParticipantDriver,
        wiki_navigator: WikiNavigator,
        harness_id: str,
        harness_config: HarnessConfig,
        scoring_rules: ScoringRules,
        ruleset_hash: str | None = None,
        taskset_hash: str | None = None,
        participant_hash: str | None = None,
        solver_backend: SolverBackend = SolverBackend.NONE,
        navigation_backend: NavigationBackend | None = None,
        navigation_snapshot_id: str | None = None,
        solver_snapshot_id: str | None = None,
        task_execution_annotation: TaskExecutionAnnotation | None = None,
        initial_position_solver_facts: PositionSolverFacts | None = None,
        solver_target_session: SolverTargetSession | None = None,
        event_sink: EventSink | None = None,
    ) -> RunExecutionArtifact:
        started_at = datetime.now()

        events: list[EventEnvelope] = []
        next_sequence = 1
        event_lock = asyncio.Lock()

        async def emit_event(
            event_type: RunEventType,
            payload: dict,
            error: ErrorRecord | None = None,
        ) -> None:
            nonlocal next_sequence
            async with event_lock:
                event = EventEnvelope(
                    event_id=f"{run_spec.run_id}:{next_sequence}",
                    event_type=event_type,
                    benchmark_id=run_spec.benchmark_id,
                    race_id=run_spec.race_id,
                    run_id=run_spec.run_id,
                    sequence=next_sequence,
                    occurred_at=datetime.now(),
                    payload=payload,
                    error=error,
                )
                events.append(
                    event,
                )

                if event_sink is not None:
                    sink_result = event_sink(
                        event,
                    )
                    if inspect.isawaitable(
                        sink_result,
                    ):
                        await sink_result

                next_sequence += 1

        await emit_event(
            RunEventType.RUN_STARTED,
            {
                "participant_id": run_spec.participant_id,
                "task_id": run_spec.task_id,
                "harness_id": harness_id,
            },
        )

        current_page_title = task_spec.start_page_title
        step_attempts: list[StepAttemptRecord] = []
        distance_cache = _initialize_solver_distance_cache(
            task_spec=task_spec,
            task_execution_annotation=task_execution_annotation,
        )
        position_solver_facts_by_page: dict[str, PositionSolverFacts] = {}
        pending_position_solver_fact_pages: set[str] = set()
        pending_position_solver_fact_tasks: list[asyncio.Task[None]] = []

        if initial_position_solver_facts is not None:
            position_solver_facts_by_page[initial_position_solver_facts.page_title] = (
                initial_position_solver_facts
            )
            distance_cache[initial_position_solver_facts.page_title] = (
                initial_position_solver_facts.shortest_path_length
            )
            await emit_event(
                RunEventType.POSITION_SOLVER_FACTS_RECORDED,
                {
                    "step_index": 0,
                    "move_index": 0,
                    "solver_facts": initial_position_solver_facts.model_dump(
                        mode="json",
                    ),
                },
            )

        committed_moves = 0
        invalid_attempts_run = 0
        invalid_attempts_in_page_context = 0
        step_budget_consumed = 0

        terminal_outcome: TerminalOutcome | None = None
        termination_reason: TerminationReason | None = None
        terminal_error: ErrorRecord | None = None

        while True:
            if current_page_title == task_spec.target_page_title:
                terminal_outcome = TerminalOutcome.SUCCESS
                termination_reason = TerminationReason.TASK_COMPLETED
                break

            if step_budget_consumed >= run_spec.navigation_rules.max_moves:
                terminal_outcome = TerminalOutcome.MODEL_FAILURE
                termination_reason = TerminationReason.MAX_MOVES_EXHAUSTED
                break

            if len(step_attempts) >= run_spec.max_step_attempts:
                terminal_outcome = TerminalOutcome.SYSTEM_FAILURE
                termination_reason = TerminationReason.HARNESS_ERROR
                terminal_error = ErrorRecord(
                    scope="run",
                    code="harness.max_step_attempt_guard_reached",
                    message="max_step_attempts reached before terminal condition",
                    retryable=False,
                )
                break

            try:
                current_page = await wiki_navigator.get_page_snapshot(
                    language=task_spec.language,
                    page_title=current_page_title,
                    link_policy=run_spec.navigation_rules.link_policy,
                )
                if not current_page.links:
                    terminal_outcome = TerminalOutcome.MODEL_FAILURE
                    termination_reason = TerminationReason.DEAD_END
                    current_page_title = current_page.title
                    break

                decision = await participant.choose_link(
                    task=task_spec,
                    current_page=current_page,
                    harness_config=harness_config,
                )
            except Exception as dependency_error:
                terminal_outcome = TerminalOutcome.SYSTEM_FAILURE
                termination_reason = TerminationReason.INFRASTRUCTURE_ERROR
                terminal_error = ErrorRecord(
                    scope="run",
                    code="infrastructure.dependency_call_failed",
                    message="participant or wiki dependency failed while executing run",
                    retryable=False,
                    details={
                        "exception_type": type(dependency_error).__name__,
                        "exception_message": str(dependency_error),
                    },
                )
                break

            step_attempt, current_page_title = await self._create_step_attempt(
                decision=decision,
                current_page_title=current_page_title,
                current_page_links=current_page.links,
                step_index=len(step_attempts) + 1,
                move_index=committed_moves + 1,
                task_spec=task_spec,
                run_spec=run_spec,
                expected_response_contract=harness_config.response_contract,
                expected_tool_name=harness_config.tool_name,
                wiki_navigator=wiki_navigator,
            )
            step_attempts.append(
                step_attempt,
            )

            await self._record_participant_feedback(
                participant=participant,
                step_attempt=step_attempt,
            )

            await emit_event(
                RunEventType.STEP_ATTEMPT_RECORDED,
                step_attempt.model_dump(mode="json"),
                error=step_attempt.error,
            )

            if step_attempt.outcome == StepOutcome.MOVE_COMMITTED:
                committed_moves += 1
                step_budget_consumed += 1
                invalid_attempts_in_page_context = 0

                await emit_event(
                    RunEventType.MOVE_COMMITTED,
                    {
                        "move_index": step_attempt.move_index,
                        "from_page_title": step_attempt.from_page_title,
                        "to_page_title": step_attempt.resolved_to_page_title,
                        "step_index": step_attempt.step_index,
                    },
                )
                if solver_target_session is not None:
                    assert step_attempt.resolved_to_page_title is not None
                    _schedule_position_solver_facts(
                        step_attempt=step_attempt,
                        solver_target_session=solver_target_session,
                        position_solver_facts_by_page=position_solver_facts_by_page,
                        pending_position_solver_fact_pages=pending_position_solver_fact_pages,
                        pending_position_solver_fact_tasks=pending_position_solver_fact_tasks,
                        distance_cache=distance_cache,
                        emit_event=emit_event,
                    )
                continue

            invalid_attempts_run += 1
            invalid_attempts_in_page_context += 1

            if step_attempt.consumed_step_budget:
                step_budget_consumed += 1

            should_terminate_for_invalid_budget = (
                invalid_attempts_run
                > run_spec.navigation_rules.max_invalid_attempts_per_run
            )

            per_context_limit = (
                run_spec.navigation_rules.max_invalid_attempts_per_step_context
            )
            if per_context_limit is not None:
                should_terminate_for_invalid_budget = (
                    should_terminate_for_invalid_budget
                    or invalid_attempts_in_page_context > per_context_limit
                )

            if (
                should_terminate_for_invalid_budget
                and run_spec.navigation_rules.terminate_on_invalid_budget_exhaustion
            ):
                terminal_outcome = TerminalOutcome.MODEL_FAILURE
                termination_reason = TerminationReason.INVALID_BUDGET_EXHAUSTED
                break

        if pending_position_solver_fact_tasks:
            await asyncio.gather(
                *pending_position_solver_fact_tasks,
            )
        _attach_solver_metrics_to_step_attempts(
            step_attempts=step_attempts,
            distance_cache=distance_cache,
        )

        ended_at = datetime.now()
        if terminal_outcome is None or termination_reason is None:
            terminal_outcome = TerminalOutcome.SYSTEM_FAILURE
            termination_reason = TerminationReason.HARNESS_ERROR
            terminal_error = ErrorRecord(
                scope="run",
                code="harness.terminal_state_not_set",
                message="run loop ended without terminal outcome",
                retryable=False,
            )

        run_result = RunResult(
            run_id=run_spec.run_id,
            race_id=run_spec.race_id,
            benchmark_id=run_spec.benchmark_id,
            task_id=run_spec.task_id,
            participant_id=run_spec.participant_id,
            terminal_outcome=terminal_outcome,
            termination_reason=termination_reason,
            current_page_title=current_page_title,
            step_attempts=step_attempts,
            ranking_eligible=_determine_ranking_eligibility(
                terminal_outcome=terminal_outcome,
                scoring_rules=scoring_rules,
            ),
            ranking_exclusion_reason=_determine_ranking_exclusion_reason(
                terminal_outcome=terminal_outcome,
                termination_reason=termination_reason,
                scoring_rules=scoring_rules,
            ),
            error=terminal_error,
            protocol_version=self.protocol_version,
            engine_commit=self.engine_commit,
            ruleset_hash=ruleset_hash,
            taskset_hash=taskset_hash,
            participant_hash=participant_hash,
            solver_backend=solver_backend,
            navigation_backend=navigation_backend,
            navigation_snapshot_id=navigation_snapshot_id,
            solver_snapshot_id=solver_snapshot_id,
            task_execution_annotation=task_execution_annotation,
            started_at=started_at,
            ended_at=ended_at,
        )

        await emit_event(
            RunEventType.RUN_TERMINATED,
            {
                "terminal_outcome": run_result.terminal_outcome.value,
                "termination_reason": run_result.termination_reason.value,
                "total_step_attempts": run_result.total_step_attempts,
                "total_committed_moves": run_result.total_committed_moves,
                "total_invalid_attempts": run_result.total_invalid_attempts,
                "estimated_cost_usd": run_result.estimated_cost_usd,
                "total_model_tokens": sum(
                    step_attempt.model_metrics.total_tokens
                    for step_attempt in run_result.step_attempts
                    if step_attempt.model_metrics is not None
                ),
                "ranking_eligible": run_result.ranking_eligible,
            },
            error=run_result.error,
        )

        return RunExecutionArtifact(
            run_result=run_result,
            events=events,
        )

    async def _create_step_attempt(
        self,
        *,
        decision: ParticipantDecision,
        current_page_title: str,
        current_page_links: list[str],
        step_index: int,
        move_index: int,
        task_spec: TaskSpec,
        run_spec: RunSpec,
        expected_response_contract: ResponseContract,
        expected_tool_name: str,
        wiki_navigator: WikiNavigator,
    ) -> tuple[StepAttemptRecord, str]:
        selected_link_text = decision.selected_link_text
        tool_call_count = _decision_tool_call_count(
            decision,
        )

        if (
            expected_response_contract == ResponseContract.TOOL_CALL_ONLY
            and tool_call_count > 1
        ):
            step_attempt = StepAttemptRecord(
                step_index=step_index,
                from_page_title=current_page_title,
                selected_link_text=None,
                outcome=StepOutcome.MALFORMED_TOOL_CALL,
                rejection_reason_code="harness.multiple_tool_calls",
                consumed_invalid_budget=True,
                consumed_step_budget=run_spec.navigation_rules.invalid_attempt_consumes_step_budget,
                model_metrics=decision.model_metrics,
                error=ErrorRecord(
                    scope="step",
                    code="harness.multiple_tool_calls",
                    message=(
                        "expected exactly one tool call, but the model returned "
                        f"{tool_call_count}"
                    ),
                    retryable=False,
                    details={
                        "tool_call_count": tool_call_count,
                        "tool_call_ids": _decision_tool_call_ids(
                            decision,
                        ),
                        "tool_call_names": _decision_tool_call_names(
                            decision,
                        ),
                    },
                ),
            )
            return step_attempt, current_page_title

        if (
            expected_response_contract == ResponseContract.TOOL_CALL_ONLY
            and decision.tool_call_name is None
        ):
            step_attempt = StepAttemptRecord(
                step_index=step_index,
                from_page_title=current_page_title,
                selected_link_text=selected_link_text,
                outcome=StepOutcome.MALFORMED_TOOL_CALL,
                rejection_reason_code="harness.tool_call_required",
                consumed_invalid_budget=True,
                consumed_step_budget=run_spec.navigation_rules.invalid_attempt_consumes_step_budget,
                model_metrics=decision.model_metrics,
                error=ErrorRecord(
                    scope="step",
                    code="harness.tool_call_required",
                    message="tool call is required for tool_call_only contract",
                    retryable=False,
                ),
            )
            return step_attempt, current_page_title

        if decision.tool_call_name and decision.tool_call_name != expected_tool_name:
            step_attempt = StepAttemptRecord(
                step_index=step_index,
                from_page_title=current_page_title,
                selected_link_text=selected_link_text,
                outcome=StepOutcome.TOOL_NOT_ALLOWED,
                rejection_reason_code="rule.tool_not_allowed",
                consumed_invalid_budget=True,
                consumed_step_budget=run_spec.navigation_rules.invalid_attempt_consumes_step_budget,
                model_metrics=decision.model_metrics,
                error=ErrorRecord(
                    scope="step",
                    code="rule.tool_not_allowed",
                    message=f"tool '{decision.tool_call_name}' is not allowed",
                    retryable=False,
                    details={
                        "expected_tool": expected_tool_name,
                        "actual_tool": decision.tool_call_name,
                    },
                ),
            )
            return step_attempt, current_page_title

        if not selected_link_text:
            step_attempt = StepAttemptRecord(
                step_index=step_index,
                from_page_title=current_page_title,
                selected_link_text=None,
                outcome=StepOutcome.MALFORMED_TOOL_CALL,
                rejection_reason_code="harness.missing_link_selection",
                consumed_invalid_budget=True,
                consumed_step_budget=run_spec.navigation_rules.invalid_attempt_consumes_step_budget,
                model_metrics=decision.model_metrics,
                error=ErrorRecord(
                    scope="step",
                    code="model.malformed_tool_call",
                    message="participant did not provide a link selection",
                    retryable=False,
                ),
            )
            return step_attempt, current_page_title

        if selected_link_text not in current_page_links:
            step_attempt = StepAttemptRecord(
                step_index=step_index,
                from_page_title=current_page_title,
                selected_link_text=selected_link_text,
                outcome=StepOutcome.INVALID_LINK,
                rejection_reason_code="rule.link_not_present",
                consumed_invalid_budget=True,
                consumed_step_budget=run_spec.navigation_rules.invalid_attempt_consumes_step_budget,
                model_metrics=decision.model_metrics,
                error=ErrorRecord(
                    scope="step",
                    code="rule.link_not_present",
                    message="selected link was not present in ordered page links",
                    retryable=False,
                ),
            )
            return step_attempt, current_page_title

        navigation_resolution = await wiki_navigator.resolve_navigation(
            language=task_spec.language,
            from_page_title=current_page_title,
            selected_link_text=selected_link_text,
        )

        if navigation_resolution.resolved_to_page_title is None:
            step_attempt = StepAttemptRecord(
                step_index=step_index,
                from_page_title=current_page_title,
                selected_link_text=selected_link_text,
                requested_to_page_title=navigation_resolution.requested_to_page_title,
                outcome=StepOutcome.VALIDATION_ERROR,
                rejection_reason_code="wiki.resolve_navigation_missing_target",
                consumed_invalid_budget=True,
                consumed_step_budget=run_spec.navigation_rules.invalid_attempt_consumes_step_budget,
                model_metrics=decision.model_metrics,
                error=ErrorRecord(
                    scope="step",
                    code="wiki.resolve_navigation_missing_target",
                    message="navigation resolution returned no resolved target page",
                    retryable=False,
                ),
            )
            return step_attempt, current_page_title

        step_attempt = StepAttemptRecord(
            step_index=step_index,
            move_index=move_index,
            from_page_title=current_page_title,
            selected_link_text=selected_link_text,
            requested_to_page_title=navigation_resolution.requested_to_page_title,
            resolved_to_page_title=navigation_resolution.resolved_to_page_title,
            was_redirect=navigation_resolution.was_redirect,
            outcome=StepOutcome.MOVE_COMMITTED,
            consumed_invalid_budget=False,
            consumed_step_budget=True,
            model_metrics=decision.model_metrics,
        )
        return step_attempt, navigation_resolution.resolved_to_page_title

    async def _record_participant_feedback(
        self,
        *,
        participant: ParticipantDriver,
        step_attempt: StepAttemptRecord,
    ) -> None:
        feedback_method = getattr(
            participant,
            "record_step_feedback",
            None,
        )
        if feedback_method is None:
            return

        if not callable(feedback_method):
            return

        feedback_result = feedback_method(
            step_attempt=step_attempt,
        )
        if inspect.isawaitable(
            feedback_result,
        ):
            await feedback_result


def _determine_ranking_eligibility(
    *,
    terminal_outcome: TerminalOutcome,
    scoring_rules: ScoringRules,
) -> bool:
    if terminal_outcome == TerminalOutcome.CANCELLED:
        return False

    if scoring_rules.exclude_system_failures_from_ranking:
        return terminal_outcome in {
            TerminalOutcome.SUCCESS,
            TerminalOutcome.MODEL_FAILURE,
        }

    return True


def _decision_tool_call_count(
    decision: ParticipantDecision,
) -> int:
    if decision.tool_call_count is not None:
        return decision.tool_call_count
    if decision.tool_call_ids or decision.tool_call_names:
        return max(
            len(
                decision.tool_call_ids,
            ),
            len(
                decision.tool_call_names,
            ),
        )
    if decision.tool_call_id is not None or decision.tool_call_name is not None:
        return 1
    return 0


def _decision_tool_call_ids(
    decision: ParticipantDecision,
) -> list[str]:
    if decision.tool_call_ids:
        return list(
            decision.tool_call_ids,
        )
    if decision.tool_call_id is not None:
        return [decision.tool_call_id]
    return []


def _decision_tool_call_names(
    decision: ParticipantDecision,
) -> list[str]:
    if decision.tool_call_names:
        return list(
            decision.tool_call_names,
        )
    if decision.tool_call_name is not None:
        return [decision.tool_call_name]
    return []


def _determine_ranking_exclusion_reason(
    *,
    terminal_outcome: TerminalOutcome,
    termination_reason: TerminationReason,
    scoring_rules: ScoringRules,
) -> str | None:
    if _determine_ranking_eligibility(
        terminal_outcome=terminal_outcome,
        scoring_rules=scoring_rules,
    ):
        return None
    return termination_reason.value


def _initialize_solver_distance_cache(
    *,
    task_spec: TaskSpec,
    task_execution_annotation: TaskExecutionAnnotation | None,
) -> dict[str, int | None]:
    if (
        task_execution_annotation is not None
        and task_execution_annotation.status == TaskExecutionAnnotationStatus.OK
        and task_execution_annotation.shortest_path_length is not None
    ):
        return {
            task_spec.start_page_title: task_execution_annotation.shortest_path_length,
        }
    return {}


async def _record_position_solver_facts(
    *,
    page_title: str,
    step_attempt: StepAttemptRecord,
    solver_target_session: SolverTargetSession,
    position_solver_facts_by_page: dict[str, PositionSolverFacts],
    pending_position_solver_fact_pages: set[str],
    distance_cache: dict[str, int | None],
    emit_event: Callable[[RunEventType, dict, ErrorRecord | None], Awaitable[None]],
) -> None:
    try:
        position_solver_facts = await solver_target_session.get_position_solver_facts(
            page_title,
        )
    except Exception:
        return
    finally:
        pending_position_solver_fact_pages.discard(
            page_title,
        )

    position_solver_facts_by_page[page_title] = position_solver_facts
    distance_cache[page_title] = position_solver_facts.shortest_path_length
    await emit_event(
        RunEventType.POSITION_SOLVER_FACTS_RECORDED,
        {
            "step_index": step_attempt.step_index,
            "move_index": step_attempt.move_index,
            "solver_facts": position_solver_facts.model_dump(
                mode="json",
            ),
        },
        None,
    )


def _attach_solver_metrics_to_step_attempts(
    *,
    step_attempts: list[StepAttemptRecord],
    distance_cache: dict[str, int | None],
) -> None:
    for step_attempt in step_attempts:
        if step_attempt.outcome != StepOutcome.MOVE_COMMITTED:
            continue
        if step_attempt.resolved_to_page_title is None:
            continue

        distance_before = distance_cache.get(
            step_attempt.from_page_title,
        )
        distance_after = distance_cache.get(
            step_attempt.resolved_to_page_title,
        )
        if distance_before is None and distance_after is None:
            continue

        step_attempt.solver_metrics = StepSolverMetrics(
            distance_before=distance_before,
            distance_after=distance_after,
        )


def _schedule_position_solver_facts(
    *,
    step_attempt: StepAttemptRecord,
    solver_target_session: SolverTargetSession,
    position_solver_facts_by_page: dict[str, PositionSolverFacts],
    pending_position_solver_fact_pages: set[str],
    pending_position_solver_fact_tasks: list[asyncio.Task[None]],
    distance_cache: dict[str, int | None],
    emit_event: Callable[[RunEventType, dict, ErrorRecord | None], Awaitable[None]],
) -> None:
    resolved_page_title = step_attempt.resolved_to_page_title
    if resolved_page_title is None:
        return
    if (
        resolved_page_title in position_solver_facts_by_page
        or resolved_page_title in pending_position_solver_fact_pages
        or resolved_page_title in distance_cache
    ):
        return

    pending_position_solver_fact_pages.add(
        resolved_page_title,
    )
    pending_position_solver_fact_tasks.append(
        asyncio.create_task(
            _record_position_solver_facts(
                page_title=resolved_page_title,
                step_attempt=step_attempt,
                solver_target_session=solver_target_session,
                position_solver_facts_by_page=position_solver_facts_by_page,
                pending_position_solver_fact_pages=pending_position_solver_fact_pages,
                distance_cache=distance_cache,
                emit_event=emit_event,
            ),
        ),
    )
