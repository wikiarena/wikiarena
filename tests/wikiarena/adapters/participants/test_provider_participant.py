from __future__ import annotations

import pytest

from wikiarena.adapters.participants import ProviderParticipant
from wikiarena.core.interfaces import PageSnapshot
from wikiarena.protocol.enums import ResponseContract, StepOutcome
from wikiarena.protocol.errors import ErrorRecord
from wikiarena.protocol.results import StepAttemptRecord
from wikiarena.protocol.rules import HarnessConfig
from wikiarena.protocol.specs import TaskSpec
from wikiarena.providers import (
    ProviderMessage,
    ProviderMessageRole,
    ProviderResponse,
    ProviderToolCall,
    ProviderUsage,
)


class FakeProviderClient:
    def __init__(
        self,
        responses: list[ProviderResponse],
    ):
        self.responses = responses
        self.requests = []

    async def generate(
        self,
        request,
    ) -> ProviderResponse:
        self.requests.append(
            request,
        )
        return self.responses.pop(0)


async def test_provider_participant_parses_tool_call_decision() -> None:
    provider_client = FakeProviderClient(
        responses=[
            ProviderResponse(
                message=ProviderMessage(
                    role=ProviderMessageRole.ASSISTANT,
                    content="Use navigate tool",
                    tool_calls=[
                        ProviderToolCall(
                            id="tc_1",
                            name="navigate",
                            arguments={
                                "to_page_title": "Banana",
                            },
                        ),
                    ],
                ),
                usage=ProviderUsage(
                    input_tokens=200,
                    output_tokens=20,
                    total_tokens=220,
                    cache_creation_input_tokens=50,
                    cache_read_input_tokens=25,
                    input_token_details={
                        "cached_tokens": 25,
                    },
                    output_token_details={
                        "reasoning_tokens": 12,
                    },
                    estimated_cost_usd=0.0123,
                    response_time_ms=123.0,
                ),
            ),
        ],
    )
    participant = ProviderParticipant(
        provider_client=provider_client,
        model_id="gpt-x",
        model_settings={
            "temperature": 0,
        },
    )

    decision = await participant.choose_link(
        task=TaskSpec(
            language="en",
            start_page_title="Apple",
            target_page_title="Banana",
        ),
        current_page=PageSnapshot(
            title="Apple",
            language="en",
            links=["Banana"],
        ),
        harness_config=HarnessConfig(
            harness_id="tool_strict_v1",
        ),
    )

    assert decision.selected_link_text == "Banana"
    assert decision.tool_call_name == "navigate"
    assert decision.tool_call_id == "tc_1"
    assert decision.model_metrics is not None
    assert decision.model_metrics.total_tokens == 220
    assert decision.model_metrics.cache_creation_input_tokens == 50
    assert decision.model_metrics.cache_read_input_tokens == 25
    assert decision.model_metrics.input_token_details == {
        "cached_tokens": 25,
    }
    assert decision.model_metrics.output_token_details == {
        "reasoning_tokens": 12,
    }
    assert decision.model_metrics.estimated_cost_usd == 0.0123
    assert provider_client.requests[0].settings == {"temperature": 0}
    first_request_messages = provider_client.requests[0].messages
    assert first_request_messages[0].role == ProviderMessageRole.SYSTEM
    assert "Wikipedia race game" in (first_request_messages[0].content or "")
    assert first_request_messages[1].role == ProviderMessageRole.USER
    assert first_request_messages[1].content == "Navigate from 'Apple' to 'Banana'."
    assert first_request_messages[2].role == ProviderMessageRole.ASSISTANT
    assert first_request_messages[2].tool_calls[0].name == "navigate"
    assert first_request_messages[2].tool_calls[0].arguments == {
        "to_page_title": "Apple",
    }
    assert first_request_messages[3].role == ProviderMessageRole.TOOL
    assert first_request_messages[3].content is not None
    assert "You are currently on the page 'Apple'" in first_request_messages[3].content
    assert "Banana" in first_request_messages[3].content


async def test_provider_participant_supports_structured_output_contract() -> None:
    provider_client = FakeProviderClient(
        responses=[
            ProviderResponse(
                message=ProviderMessage(
                    role=ProviderMessageRole.ASSISTANT,
                    content='{"to_page_title":"Physics"}',
                ),
            ),
        ],
    )
    participant = ProviderParticipant(
        provider_client=provider_client,
        model_id="claude-x",
    )

    decision = await participant.choose_link(
        task=TaskSpec(
            language="en",
            start_page_title="Science",
            target_page_title="Philosophy",
        ),
        current_page=PageSnapshot(
            title="Science",
            language="en",
            links=["Physics"],
        ),
        harness_config=HarnessConfig(
            harness_id="structured_v1",
            response_contract=ResponseContract.STRUCTURED_OUTPUT_ONLY,
        ),
    )

    assert decision.selected_link_text == "Physics"
    assert decision.tool_call_name is None
    assert provider_client.requests[0].tools == []


async def test_provider_participant_ignores_tool_calls_in_structured_mode() -> None:
    provider_client = FakeProviderClient(
        responses=[
            ProviderResponse(
                message=ProviderMessage(
                    role=ProviderMessageRole.ASSISTANT,
                    content='{"to_page_title":"Chemistry"}',
                    tool_calls=[
                        ProviderToolCall(
                            id="tc_structured_1",
                            name="navigate",
                            arguments={"to_page_title": "Physics"},
                        ),
                    ],
                ),
            ),
        ],
    )
    participant = ProviderParticipant(
        provider_client=provider_client,
        model_id="claude-x",
    )

    decision = await participant.choose_link(
        task=TaskSpec(
            language="en",
            start_page_title="Science",
            target_page_title="Philosophy",
        ),
        current_page=PageSnapshot(
            title="Science",
            language="en",
            links=["Chemistry", "Physics"],
        ),
        harness_config=HarnessConfig(
            harness_id="structured_v1",
            response_contract=ResponseContract.STRUCTURED_OUTPUT_ONLY,
        ),
    )

    assert decision.selected_link_text == "Chemistry"
    assert decision.tool_call_name is None


async def test_provider_participant_records_feedback_as_tool_message() -> None:
    provider_client = FakeProviderClient(
        responses=[
            ProviderResponse(
                message=ProviderMessage(
                    role=ProviderMessageRole.ASSISTANT,
                    tool_calls=[
                        ProviderToolCall(
                            id="tc_feedback",
                            name="navigate",
                            arguments={
                                "to_page_title": "Banana",
                            },
                        ),
                    ],
                ),
            ),
        ],
    )
    participant = ProviderParticipant(
        provider_client=provider_client,
        model_id="gpt-x",
    )

    task = TaskSpec(
        language="en",
        start_page_title="Apple",
        target_page_title="Banana",
    )
    await participant.choose_link(
        task=task,
        current_page=PageSnapshot(
            title="Apple",
            language="en",
            links=["Banana"],
        ),
        harness_config=HarnessConfig(
            harness_id="tool_strict_v1",
        ),
    )

    await participant.record_step_feedback(
        step_attempt=StepAttemptRecord(
            step_index=1,
            move_index=1,
            from_page_title="Apple",
            selected_link_text="Banana",
            requested_to_page_title="Banana",
            resolved_to_page_title="Banana",
            outcome=StepOutcome.MOVE_COMMITTED,
            consumed_step_budget=True,
        ),
    )

    assert participant._pending_success_tool_call_id == "tc_feedback"


async def test_provider_participant_appends_next_page_context_after_successful_move() -> (
    None
):
    provider_client = FakeProviderClient(
        responses=[
            ProviderResponse(
                message=ProviderMessage(
                    role=ProviderMessageRole.ASSISTANT,
                    tool_calls=[
                        ProviderToolCall(
                            id="tc_1",
                            name="navigate",
                            arguments={
                                "to_page_title": "Banana",
                            },
                        ),
                    ],
                ),
            ),
            ProviderResponse(
                message=ProviderMessage(
                    role=ProviderMessageRole.ASSISTANT,
                    tool_calls=[
                        ProviderToolCall(
                            id="tc_2",
                            name="navigate",
                            arguments={
                                "to_page_title": "Cherry",
                            },
                        ),
                    ],
                ),
            ),
        ],
    )
    participant = ProviderParticipant(
        provider_client=provider_client,
        model_id="gpt-x",
    )
    task = TaskSpec(
        language="en",
        start_page_title="Apple",
        target_page_title="Cherry",
    )

    await participant.choose_link(
        task=task,
        current_page=PageSnapshot(
            title="Apple",
            language="en",
            links=["Banana"],
        ),
        harness_config=HarnessConfig(
            harness_id="tool_strict_v1",
        ),
    )
    await participant.record_step_feedback(
        step_attempt=StepAttemptRecord(
            step_index=1,
            move_index=1,
            from_page_title="Apple",
            selected_link_text="Banana",
            requested_to_page_title="Banana",
            resolved_to_page_title="Banana",
            outcome=StepOutcome.MOVE_COMMITTED,
            consumed_step_budget=True,
        ),
    )

    await participant.choose_link(
        task=task,
        current_page=PageSnapshot(
            title="Banana",
            language="en",
            links=["Cherry"],
        ),
        harness_config=HarnessConfig(
            harness_id="tool_strict_v1",
        ),
    )

    second_request_messages = provider_client.requests[1].messages
    assert second_request_messages[-1].role == ProviderMessageRole.TOOL
    assert second_request_messages[-1].content is not None
    assert (
        "You are currently on the page 'Banana'" in second_request_messages[-1].content
    )
    assert "Cherry" in second_request_messages[-1].content


async def test_provider_participant_invalid_feedback_does_not_append_followup_user_message() -> (
    None
):
    provider_client = FakeProviderClient(
        responses=[
            ProviderResponse(
                message=ProviderMessage(
                    role=ProviderMessageRole.ASSISTANT,
                    tool_calls=[
                        ProviderToolCall(
                            id="tc_invalid",
                            name="navigate",
                            arguments={
                                "to_page_title": "Pear",
                            },
                        ),
                    ],
                ),
            ),
        ],
    )
    participant = ProviderParticipant(
        provider_client=provider_client,
        model_id="gpt-x",
    )

    await participant.choose_link(
        task=TaskSpec(
            language="en",
            start_page_title="Apple",
            target_page_title="Banana",
        ),
        current_page=PageSnapshot(
            title="Apple",
            language="en",
            links=["Banana"],
        ),
        harness_config=HarnessConfig(
            harness_id="tool_strict_v1",
        ),
    )

    await participant.record_step_feedback(
        step_attempt=StepAttemptRecord(
            step_index=1,
            from_page_title="Apple",
            selected_link_text="Pear",
            outcome=StepOutcome.INVALID_LINK,
            rejection_reason_code="rule.link_not_present",
            consumed_invalid_budget=True,
        ),
    )

    assert participant._messages[-1].role == ProviderMessageRole.TOOL
    assert participant._messages[-1].tool_call_id == "tc_invalid"
    assert participant._messages[-1].content is not None
    assert "Invalid move." in participant._messages[-1].content
    assert "You are still on 'Apple'" in participant._messages[-1].content
    assert "'Pear' is not one of the links listed on the current page" in participant._messages[-1].content
    assert "Do not paraphrase or guess" in participant._messages[-1].content


async def test_provider_participant_returns_error_feedback_for_every_parallel_tool_call() -> (
    None
):
    provider_client = FakeProviderClient(
        responses=[
            ProviderResponse(
                message=ProviderMessage(
                    role=ProviderMessageRole.ASSISTANT,
                    tool_calls=[
                        ProviderToolCall(
                            id="tc_parallel_1",
                            name="navigate",
                            arguments={
                                "to_page_title": "Banana",
                            },
                        ),
                        ProviderToolCall(
                            id="tc_parallel_2",
                            name="navigate",
                            arguments={
                                "to_page_title": "Cherry",
                            },
                        ),
                    ],
                ),
            ),
        ],
    )
    participant = ProviderParticipant(
        provider_client=provider_client,
        model_id="gpt-x",
    )

    decision = await participant.choose_link(
        task=TaskSpec(
            language="en",
            start_page_title="Apple",
            target_page_title="Banana",
        ),
        current_page=PageSnapshot(
            title="Apple",
            language="en",
            links=["Banana", "Cherry"],
        ),
        harness_config=HarnessConfig(
            harness_id="tool_strict_v1",
        ),
    )

    assert decision.selected_link_text is None
    assert decision.tool_call_count == 2
    assert decision.tool_call_ids == ["tc_parallel_1", "tc_parallel_2"]

    await participant.record_step_feedback(
        step_attempt=StepAttemptRecord(
            step_index=1,
            from_page_title="Apple",
            selected_link_text=None,
            outcome=StepOutcome.MALFORMED_TOOL_CALL,
            rejection_reason_code="harness.multiple_tool_calls",
            consumed_invalid_budget=True,
            error=ErrorRecord(
                scope="step",
                code="harness.multiple_tool_calls",
                message="expected exactly one tool call, but the model returned 2",
                details={
                    "tool_call_count": 2,
                },
            ),
        ),
    )

    tool_messages = [
        message
        for message in participant._messages
        if message.role == ProviderMessageRole.TOOL
        and message.tool_call_id in {"tc_parallel_1", "tc_parallel_2"}
    ]
    assert [message.tool_call_id for message in tool_messages] == [
        "tc_parallel_1",
        "tc_parallel_2",
    ]
    assert all(message.is_error for message in tool_messages)
    assert all(message.content is not None for message in tool_messages)
    assert all("Invalid move." in (message.content or "") for message in tool_messages)
    assert all(
        "called 2 tools, but WikiArena allows exactly one navigation tool call per step"
        in (message.content or "")
        for message in tool_messages
    )


async def test_provider_participant_feedback_requires_tool_call_after_plain_text_reply() -> (
    None
):
    provider_client = FakeProviderClient(
        responses=[
            ProviderResponse(
                message=ProviderMessage(
                    role=ProviderMessageRole.ASSISTANT,
                    content="I will go to Banana next.",
                ),
            ),
        ],
    )
    participant = ProviderParticipant(
        provider_client=provider_client,
        model_id="gpt-x",
    )

    await participant.choose_link(
        task=TaskSpec(
            language="en",
            start_page_title="Apple",
            target_page_title="Banana",
        ),
        current_page=PageSnapshot(
            title="Apple",
            language="en",
            links=["Banana"],
        ),
        harness_config=HarnessConfig(
            harness_id="tool_strict_v1",
        ),
    )

    await participant.record_step_feedback(
        step_attempt=StepAttemptRecord(
            step_index=1,
            from_page_title="Apple",
            selected_link_text=None,
            outcome=StepOutcome.MALFORMED_TOOL_CALL,
            rejection_reason_code="harness.tool_call_required",
            consumed_invalid_budget=True,
            error=ErrorRecord(
                scope="step",
                code="harness.tool_call_required",
                message="tool call is required for tool_call_only contract",
            ),
        ),
    )

    assert participant._messages[-1].role == ProviderMessageRole.USER
    assert participant._messages[-1].content is not None
    assert "Only `navigate` is allowed for moves" in (
        participant._messages[-1].content
    )
    assert "If you want to move, call" in participant._messages[-1].content


@pytest.mark.parametrize(
    ("provider_response", "step_attempt", "expected_substrings"),
    [
        (
            ProviderResponse(
                message=ProviderMessage(
                    role=ProviderMessageRole.ASSISTANT,
                    tool_calls=[
                        ProviderToolCall(
                            id="tc_wrong_tool",
                            name="search",
                            arguments={
                                "to_page_title": "Banana",
                            },
                        ),
                    ],
                ),
            ),
            StepAttemptRecord(
                step_index=1,
                from_page_title="Apple",
                selected_link_text="Banana",
                outcome=StepOutcome.TOOL_NOT_ALLOWED,
                rejection_reason_code="rule.tool_not_allowed",
                consumed_invalid_budget=True,
                error=ErrorRecord(
                    scope="step",
                    code="rule.tool_not_allowed",
                    message="tool 'search' is not allowed",
                    details={
                        "expected_tool": "navigate",
                        "actual_tool": "search",
                    },
                ),
            ),
            [
                "You called `search` but only `navigate` is allowed",
                'navigate({"to_page_title": "<exact link title from the current page>"})',
            ],
        ),
        (
            ProviderResponse(
                message=ProviderMessage(
                    role=ProviderMessageRole.ASSISTANT,
                    tool_calls=[
                        ProviderToolCall(
                            id="tc_missing_link",
                            name="navigate",
                            arguments={},
                        ),
                    ],
                ),
            ),
            StepAttemptRecord(
                step_index=1,
                from_page_title="Apple",
                selected_link_text=None,
                outcome=StepOutcome.MALFORMED_TOOL_CALL,
                rejection_reason_code="harness.missing_link_selection",
                consumed_invalid_budget=True,
                error=ErrorRecord(
                    scope="step",
                    code="model.malformed_tool_call",
                    message="participant did not provide a link selection",
                ),
            ),
            [
                "did not include a destination page title",
                '`navigate({"to_page_title": "<exact link title from the current page>"})`',
            ],
        ),
        (
            ProviderResponse(
                message=ProviderMessage(
                    role=ProviderMessageRole.ASSISTANT,
                    tool_calls=[
                        ProviderToolCall(
                            id="tc_unresolved",
                            name="navigate",
                            arguments={
                                "to_page_title": "Banana",
                            },
                        ),
                    ],
                ),
            ),
            StepAttemptRecord(
                step_index=1,
                from_page_title="Apple",
                selected_link_text="Banana",
                requested_to_page_title="Banana",
                outcome=StepOutcome.VALIDATION_ERROR,
                rejection_reason_code="wiki.resolve_navigation_missing_target",
                consumed_invalid_budget=True,
                error=ErrorRecord(
                    scope="step",
                    code="wiki.resolve_navigation_missing_target",
                    message="navigation resolution returned no resolved target page",
                ),
            ),
            [
                "could not resolve your selected link 'Banana'",
                "different exact link title from the current page",
            ],
        ),
    ],
)
async def test_provider_participant_formats_actionable_tool_error_feedback(
    provider_response: ProviderResponse,
    step_attempt: StepAttemptRecord,
    expected_substrings: list[str],
) -> None:
    provider_client = FakeProviderClient(
        responses=[provider_response],
    )
    participant = ProviderParticipant(
        provider_client=provider_client,
        model_id="gpt-x",
    )

    await participant.choose_link(
        task=TaskSpec(
            language="en",
            start_page_title="Apple",
            target_page_title="Banana",
        ),
        current_page=PageSnapshot(
            title="Apple",
            language="en",
            links=["Banana"],
        ),
        harness_config=HarnessConfig(
            harness_id="tool_strict_v1",
        ),
    )

    await participant.record_step_feedback(
        step_attempt=step_attempt,
    )

    assert participant._messages[-1].role == ProviderMessageRole.TOOL
    assert participant._messages[-1].content is not None
    assert "Invalid move." in participant._messages[-1].content
    assert "You are still on 'Apple'" in participant._messages[-1].content
    assert "links listed on the current page have not changed" in (
        participant._messages[-1].content
    )
    for substring in expected_substrings:
        assert substring in participant._messages[-1].content
