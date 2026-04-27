from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wikiarena.protocol.events import EventEnvelope
from wikiarena.protocol.results import RunResult


class RaceParticipantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_id: str | None = None
    display_name: str | None = None
    provider: str = "openai"
    model: str
    settings: dict[str, Any] = Field(default_factory=dict)


class CreateRaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_title: str
    target_title: str
    participants: list[RaceParticipantRequest] = Field(min_length=1)
    benchmark_id: str = "adhoc_benchmark"
    max_moves: int = Field(default=50, ge=1)
    navigation_backend: Literal["graph", "live"] | None = None
    solver_backend: Literal["local", "none"] | None = None

    @field_validator("start_title", "target_title")
    @classmethod
    def strip_non_empty_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("title cannot be empty")
        return stripped


class RaceParticipantSummary(BaseModel):
    participant_id: str
    display_name: str
    provider: str
    model: str
    run_id: str


class RaceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    race_id: str
    benchmark_id: str
    task_id: str
    start_title: str
    target_title: str
    participants: list[RaceParticipantSummary]
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error_message: str | None = None


class StoredRaceEvent(BaseModel):
    stream_sequence: int = Field(ge=1)
    event: EventEnvelope


class RaceCreatedResponse(BaseModel):
    race_id: str
    status: str
    stream_url: str
    events_url: str
    race_url: str


class RaceStateResponse(BaseModel):
    metadata: RaceMetadata
    latest_stream_sequence: int
    events: list[StoredRaceEvent] = Field(default_factory=list)
    run_results: list[RunResult] = Field(default_factory=list)


class RaceEventsResponse(BaseModel):
    race_id: str
    latest_stream_sequence: int
    events: list[StoredRaceEvent] = Field(default_factory=list)
