from __future__ import annotations

from wikiarena.core.interfaces import PageSnapshot
from wikiarena.core.interfaces import ParticipantDecision
from wikiarena.protocol.rules import HarnessConfig
from wikiarena.protocol.specs import TaskSpec


class FirstLinkParticipant:
    """Simple scripted participant that always picks the first available link."""

    async def choose_link(
        self,
        task: TaskSpec,
        current_page: PageSnapshot,
        harness_config: HarnessConfig,
    ) -> ParticipantDecision:
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
