from __future__ import annotations

import asyncio
import random

from wikiarena.core.interfaces import PageSnapshot, ParticipantDecision
from wikiarena.protocol.rules import HarnessConfig
from wikiarena.protocol.specs import TaskSpec


class FirstLinkParticipant:
    """Simple scripted participant that always picks the first available link."""

    def __init__(self, *, move_delay_s: float = 1.0):
        self._move_delay_s = move_delay_s

    async def choose_link(
        self,
        task: TaskSpec,
        current_page: PageSnapshot,
        harness_config: HarnessConfig,
    ) -> ParticipantDecision:
        del task
        if self._move_delay_s > 0:
            await asyncio.sleep(self._move_delay_s)

        if not current_page.links:
            return ParticipantDecision(
                selected_link_text=None,
                raw_response="No links available",
            )

        return ParticipantDecision(
            selected_link_text=current_page.links[0],
            raw_response=f"Selected first link: {current_page.links[0]}",
            tool_call_name=harness_config.tool_name,
            tool_call_id=f"first-link-{current_page.title}",
        )


class RandomLinkParticipant:
    """Zero-token participant for cheap UI and backend iteration."""

    def __init__(self, *, seed: int | None = None, move_delay_s: float = 1.0):
        self._random = random.Random(seed)
        self._move_delay_s = move_delay_s

    async def choose_link(
        self,
        task: TaskSpec,
        current_page: PageSnapshot,
        harness_config: HarnessConfig,
    ) -> ParticipantDecision:
        del task
        if self._move_delay_s > 0:
            await asyncio.sleep(self._move_delay_s)

        if not current_page.links:
            return ParticipantDecision(
                selected_link_text=None,
                raw_response="No links available",
            )

        selected_link = self._random.choice(current_page.links)
        return ParticipantDecision(
            selected_link_text=selected_link,
            raw_response=f"Selected random link: {selected_link}",
            tool_call_name=harness_config.tool_name,
            tool_call_id=f"random-link-{current_page.title}",
        )
