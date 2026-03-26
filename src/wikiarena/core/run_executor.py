from __future__ import annotations

import inspect
from datetime import datetime
from typing import Awaitable
from typing import Callable

from pydantic import BaseModel
from pydantic import Field

from wikiarena.core.interfaces import ParticipantDecision
from wikiarena.core.interfaces import ParticipantDriver
from wikiarena.core.interfaces import WikiNavigator
from wikiarena.protocol.enums import RunEventType
from wikiarena.protocol.enums import ResponseContract
from wikiarena.protocol.enums import SolverMode
from wikiarena.protocol.enums import StepOutcome
from wikiarena.protocol.enums import TerminalOutcome
from wikiarena.protocol.enums import TerminationReason
from wikiarena.protocol.enums import WikiBackend
from wikiarena.protocol.errors import ErrorRecord
from wikiarena.protocol.events import EventEnvelope
from wikiarena.protocol.results import RunResult
from wikiarena.protocol.results import StepAttemptRecord
from wikiarena.protocol.rules import HarnessConfig
from wikiarena.protocol.rules import ScoringRules
from wikiarena.protocol.specs import RunSpec
from wikiarena.protocol.specs import TaskSpec


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
        protocol_version: str = "1.0.0-draft",
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
        solver_mode: SolverMode = SolverMode.NONE,
        wiki_backend: WikiBackend | None = None,
        wiki_snapshot_id: str | None = None,
        event_sink: EventSink | None = None,
    ) -> RunExecutionArtifact:
        started_at = datetime.now()

        events: list[EventEnvelope] = []
        next_sequence = 1

        async def emit_event(
            event_type: RunEventType,
            payload: dict,
            error: ErrorRecord | None = None,
        ) -> None:
            nonlocal next_sequence
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
            solver_mode=solver_mode,
            wiki_backend=wiki_backend,
            wiki_snapshot_id=wiki_snapshot_id,
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
