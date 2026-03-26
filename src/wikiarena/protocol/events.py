from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel
from pydantic import Field

from wikiarena.protocol.enums import RunEventType
from wikiarena.protocol.errors import ErrorRecord


class EventEnvelope(BaseModel):
    event_id: str
    event_type: RunEventType
    benchmark_id: str
    race_id: str
    run_id: str
    sequence: int = Field(
        ge=1,
    )
    occurred_at: datetime = Field(
        default_factory=datetime.now,
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
    )
    error: ErrorRecord | None = None
