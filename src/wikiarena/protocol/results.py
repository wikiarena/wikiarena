from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator

from wikiarena.protocol.enums import RunStatus
from wikiarena.protocol.enums import SolverMode
from wikiarena.protocol.enums import StepOutcome
from wikiarena.protocol.enums import TerminalOutcome
from wikiarena.protocol.enums import TerminationReason
from wikiarena.protocol.enums import WikiBackend
from wikiarena.protocol.errors import ErrorRecord


class ModelCallMetrics(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    estimated_cost_usd: float = 0.0
    response_time_ms: float = 0.0


class StepSolverMetrics(BaseModel):
    distance_before: int | None = Field(
        default=None,
        ge=0,
    )
    distance_after: int | None = Field(
        default=None,
        ge=0,
    )


class StepAttemptRecord(BaseModel):
    step_index: int = Field(
        ge=1,
    )
    move_index: int | None = Field(
        default=None,
        ge=1,
    )
    from_page_title: str
    selected_link_text: str | None = None
    requested_to_page_title: str | None = None
    resolved_to_page_title: str | None = None
    was_redirect: bool | None = None
    outcome: StepOutcome
    rejection_reason_code: str | None = None
    consumed_invalid_budget: bool = False
    consumed_step_budget: bool = False
    duration_ms: float = Field(
        default=0.0,
        ge=0.0,
    )
    model_metrics: ModelCallMetrics | None = None
    solver_metrics: StepSolverMetrics | None = None
    error: ErrorRecord | None = None
    occurred_at: datetime = Field(
        default_factory=datetime.now,
    )

    @model_validator(mode="after")
    def validate_outcome_dependent_fields(self) -> "StepAttemptRecord":
        if self.outcome == StepOutcome.MOVE_COMMITTED:
            if self.move_index is None:
                raise ValueError(
                    "move_index is required when outcome is move_committed",
                )
            if self.resolved_to_page_title is None:
                raise ValueError(
                    "resolved_to_page_title is required when outcome is move_committed",
                )
            return self

        if self.move_index is not None:
            raise ValueError(
                "move_index must be null for non-committed step outcomes",
            )

        return self


class MoveRecord(BaseModel):
    move_index: int = Field(
        ge=1,
    )
    source_step_index: int = Field(
        ge=1,
    )
    from_page_title: str
    to_page_title: str
    requested_to_page_title: str | None = None
    was_redirect: bool | None = None
    occurred_at: datetime


class RunResult(BaseModel):
    run_id: str
    race_id: str
    benchmark_id: str
    task_id: str
    participant_id: str

    status: RunStatus = RunStatus.COMPLETED
    terminal_outcome: TerminalOutcome
    termination_reason: TerminationReason

    current_page_title: str | None = None
    step_attempts: list[StepAttemptRecord] = Field(
        default_factory=list,
    )
    committed_moves: list[MoveRecord] = Field(
        default_factory=list,
    )

    total_step_attempts: int = 0
    total_committed_moves: int = 0
    total_invalid_attempts: int = 0

    ranking_eligible: bool | None = None
    ranking_exclusion_reason: str | None = None

    error: ErrorRecord | None = None

    protocol_version: str = "1.0.0-draft"
    engine_commit: str | None = None
    ruleset_hash: str | None = None
    taskset_hash: str | None = None
    participant_hash: str | None = None
    solver_mode: SolverMode = SolverMode.NONE
    wiki_backend: WikiBackend | None = None
    wiki_snapshot_id: str | None = None

    started_at: datetime
    ended_at: datetime
    duration_ms: float | None = Field(
        default=None,
        ge=0.0,
    )

    @model_validator(mode="after")
    def derive_and_validate_runtime_fields(self) -> "RunResult":
        self._validate_terminal_outcome_reason_pair()
        self._validate_step_index_sequence()

        self.total_step_attempts = len(
            self.step_attempts,
        )
        self.total_committed_moves = sum(
            1
            for step_attempt in self.step_attempts
            if step_attempt.outcome == StepOutcome.MOVE_COMMITTED
        )
        self.total_invalid_attempts = (
            self.total_step_attempts - self.total_committed_moves
        )

        if not self.committed_moves:
            self.committed_moves = [
                MoveRecord(
                    move_index=step_attempt.move_index,
                    source_step_index=step_attempt.step_index,
                    from_page_title=step_attempt.from_page_title,
                    to_page_title=step_attempt.resolved_to_page_title,
                    requested_to_page_title=step_attempt.requested_to_page_title,
                    was_redirect=step_attempt.was_redirect,
                    occurred_at=step_attempt.occurred_at,
                )
                for step_attempt in self.step_attempts
                if step_attempt.outcome == StepOutcome.MOVE_COMMITTED
            ]

        self._validate_move_index_sequence()

        if self.ranking_eligible is None:
            self.ranking_eligible = self.terminal_outcome in {
                TerminalOutcome.SUCCESS,
                TerminalOutcome.MODEL_FAILURE,
            }

        if not self.ranking_eligible and self.ranking_exclusion_reason is None:
            self.ranking_exclusion_reason = self.termination_reason.value

        if self.ranking_eligible and self.ranking_exclusion_reason is not None:
            raise ValueError(
                "ranking_exclusion_reason must be null when ranking_eligible is true",
            )

        if self.duration_ms is None:
            duration_seconds = (self.ended_at - self.started_at).total_seconds()
            if duration_seconds < 0:
                raise ValueError(
                    "ended_at must not be before started_at",
                )
            self.duration_ms = duration_seconds * 1000.0

        return self

    def _validate_step_index_sequence(self) -> None:
        expected_step_index = 1
        for step_attempt in self.step_attempts:
            if step_attempt.step_index != expected_step_index:
                raise ValueError(
                    "step_attempts must use contiguous step_index values starting at 1",
                )
            expected_step_index += 1

    def _validate_move_index_sequence(self) -> None:
        expected_move_index = 1
        for move_record in self.committed_moves:
            if move_record.move_index != expected_move_index:
                raise ValueError(
                    "committed_moves must use contiguous move_index values starting at 1",
                )
            expected_move_index += 1

    def _validate_terminal_outcome_reason_pair(self) -> None:
        if self.terminal_outcome == TerminalOutcome.SUCCESS:
            if self.termination_reason != TerminationReason.TASK_COMPLETED:
                raise ValueError(
                    "success outcomes must use termination_reason task_completed",
                )
            return

        if self.terminal_outcome == TerminalOutcome.CANCELLED:
            if self.termination_reason != TerminationReason.CANCELLED:
                raise ValueError(
                    "cancelled outcomes must use termination_reason cancelled",
                )


class RaceResult(BaseModel):
    race_id: str
    benchmark_id: str
    task_id: str
    run_results: list[RunResult] = Field(
        default_factory=list,
    )
    error: ErrorRecord | None = None


class BenchmarkResult(BaseModel):
    benchmark_id: str
    race_results: list[RaceResult] = Field(
        default_factory=list,
    )
    error: ErrorRecord | None = None
