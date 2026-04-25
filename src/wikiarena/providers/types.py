from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel
from pydantic import Field


class ProviderMessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ProviderToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(
        default_factory=dict,
    )


class ProviderReasoningItem(BaseModel):
    id: str
    summary: str | None = None
    encrypted_content: str | None = None
    status: str | None = None


class ProviderMessage(BaseModel):
    role: ProviderMessageRole
    content: str | None = None
    thinking: str | None = None
    reasoning_items: list[ProviderReasoningItem] = Field(
        default_factory=list,
    )
    tool_calls: list[ProviderToolCall] = Field(
        default_factory=list,
    )
    tool_call_id: str | None = None
    is_error: bool = False


class ProviderTool(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] = Field(
        default_factory=dict,
    )


class ProviderUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    input_token_details: dict[str, int] = Field(
        default_factory=dict,
    )
    output_token_details: dict[str, int] = Field(
        default_factory=dict,
    )
    estimated_cost_usd: float = 0.0
    response_time_ms: float = 0.0


class ProviderRequest(BaseModel):
    model_id: str
    messages: list[ProviderMessage] = Field(
        default_factory=list,
    )
    tools: list[ProviderTool] = Field(
        default_factory=list,
    )
    settings: dict[str, Any] = Field(
        default_factory=dict,
    )
    tool_choice: str = "auto"


class ProviderResponse(BaseModel):
    message: ProviderMessage
    usage: ProviderUsage = Field(
        default_factory=ProviderUsage,
    )
    provider_response_id: str | None = None
