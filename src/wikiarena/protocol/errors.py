from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic import Field

from wikiarena.protocol.enums import ErrorScope


class ErrorRecord(BaseModel):
    scope: ErrorScope
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(
        default_factory=dict,
    )
    caused_by: ErrorRecord | None = None


ErrorRecord.model_rebuild()
