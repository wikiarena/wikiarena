from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field

from wikiarena.protocol.enums import LinkPolicy
from wikiarena.protocol.results import ModelCallMetrics
from wikiarena.protocol.rules import HarnessConfig
from wikiarena.protocol.specs import TaskSpec


class PageSnapshot(BaseModel):
    title: str
    language: str
    links: list[str] = Field(
        default_factory=list,
    )
    observed_at: datetime = Field(
        default_factory=datetime.now,
    )


class NavigationResolution(BaseModel):
    requested_to_page_title: str | None = None
    resolved_to_page_title: str | None = None
    was_redirect: bool = False


class ParticipantDecision(BaseModel):
    selected_link_text: str | None = None
    raw_response: str | None = None
    tool_call_name: str | None = None
    tool_call_id: str | None = None
    tool_call_count: int | None = Field(
        default=None,
        ge=0,
    )
    tool_call_ids: list[str] = Field(
        default_factory=list,
    )
    tool_call_names: list[str] = Field(
        default_factory=list,
    )
    model_metrics: ModelCallMetrics | None = None


class ParticipantDriver(Protocol):
    async def choose_link(
        self,
        task: TaskSpec,
        current_page: PageSnapshot,
        harness_config: HarnessConfig,
    ) -> ParticipantDecision: ...


class WikiNavigator(Protocol):
    async def get_page_snapshot(
        self,
        language: str,
        page_title: str,
        link_policy: LinkPolicy,
    ) -> PageSnapshot: ...

    async def resolve_navigation(
        self,
        language: str,
        from_page_title: str,
        selected_link_text: str,
    ) -> NavigationResolution: ...
