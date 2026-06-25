from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from wikiarena.protocol.enums import LinkPolicy, RedirectPolicy, ResponseContract

UnsolvedPairPolicy = Literal["skip", "draw"]


class NavigationRules(BaseModel):
    max_moves: int = Field(
        default=50,
        ge=1,
    )
    max_invalid_attempts_per_run: int = Field(
        default=15,
        ge=0,
    )
    max_invalid_attempts_per_step_context: int | None = Field(
        default=2,
        ge=0,
    )
    invalid_attempt_consumes_step_budget: bool = False
    terminate_on_invalid_budget_exhaustion: bool = True
    link_policy: LinkPolicy = LinkPolicy.RAW_ORDERED
    redirect_policy: RedirectPolicy = RedirectPolicy.RESOLVE_AFTER_SELECTION

    @property
    def derived_max_step_attempts(self) -> int:
        if self.invalid_attempt_consumes_step_budget:
            return self.max_moves
        return self.max_moves + self.max_invalid_attempts_per_run


class HarnessConfig(BaseModel):
    harness_id: str
    response_contract: ResponseContract = ResponseContract.TOOL_CALL_ONLY
    tool_name: str = "navigate"


class ExecutionPolicy(BaseModel):
    request_timeout_ms: int = Field(
        default=45_000,
        ge=1,
    )
    max_transport_retries: int = Field(
        default=2,
        ge=0,
    )
    initial_backoff_ms: int = Field(
        default=250,
        ge=0,
    )
    max_backoff_ms: int = Field(
        default=10_000,
        ge=0,
    )
    jitter_ratio: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
    )
    max_concurrency: int | None = Field(
        default=None,
        ge=1,
    )


class ScoringRules(BaseModel):
    exclude_system_failures_from_ranking: bool = True
    tie_breaker: str = "fewest_moves_then_draw"
    unsolved_pair_policy: UnsolvedPairPolicy = "skip"


class BenchmarkRules(BaseModel):
    navigation: NavigationRules = Field(
        default_factory=NavigationRules,
    )
    harness: HarnessConfig
    execution: ExecutionPolicy = Field(
        default_factory=ExecutionPolicy,
    )
    scoring: ScoringRules = Field(
        default_factory=ScoringRules,
    )
