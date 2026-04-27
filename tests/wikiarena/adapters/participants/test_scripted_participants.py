from __future__ import annotations

from wikiarena.adapters.participants import FirstLinkParticipant, RandomLinkParticipant
from wikiarena.core.interfaces import PageSnapshot
from wikiarena.eval.run_service import _default_participant_factory
from wikiarena.protocol.enums import ParticipantKind
from wikiarena.protocol.rules import HarnessConfig
from wikiarena.protocol.specs import DriverConfig, ParticipantSpec, TaskSpec


async def test_random_link_participant_selects_available_link() -> None:
    participant = RandomLinkParticipant(seed=1, move_delay_s=0)

    decision = await participant.choose_link(
        task=TaskSpec(
            start_page_title="Apple",
            target_page_title="Fruit",
        ),
        current_page=PageSnapshot(
            title="Apple",
            language="en",
            links=["Fruit", "Tree"],
        ),
        harness_config=HarnessConfig(harness_id="tool_strict_v1"),
    )

    assert decision.selected_link_text in {"Fruit", "Tree"}
    assert decision.tool_call_name == "navigate"
    assert decision.tool_call_id == "random-link-Apple"


async def test_first_link_participant_selects_first_available_link() -> None:
    participant = FirstLinkParticipant(move_delay_s=0)

    decision = await participant.choose_link(
        task=TaskSpec(
            start_page_title="Apple",
            target_page_title="Fruit",
        ),
        current_page=PageSnapshot(
            title="Apple",
            language="en",
            links=["Fruit", "Tree"],
        ),
        harness_config=HarnessConfig(harness_id="tool_strict_v1"),
    )

    assert decision.selected_link_text == "Fruit"
    assert decision.tool_call_name == "navigate"
    assert decision.tool_call_id == "first-link-Apple"


def test_wikiarena_random_participant_factory_uses_random_link_participant() -> None:
    participant = _default_participant_factory(
        ParticipantSpec(
            participant_id="wikiarena_random_1",
            participant_kind=ParticipantKind.SCRIPTED,
            display_name="Random Walker",
            driver_config=DriverConfig(
                provider="wikiarena",
                model="random",
            ),
        )
    )

    assert isinstance(participant, RandomLinkParticipant)


def test_wikiarena_first_link_participant_factory_uses_move_delay_setting() -> None:
    participant = _default_participant_factory(
        ParticipantSpec(
            participant_id="wikiarena_first_1",
            participant_kind=ParticipantKind.SCRIPTED,
            display_name="First Link",
            driver_config=DriverConfig(
                provider="wikiarena",
                model="first",
                settings={
                    "move_delay_s": 0.25,
                },
            ),
        )
    )

    assert isinstance(participant, FirstLinkParticipant)
    assert participant._move_delay_s == 0.25
