from __future__ import annotations

import json
from typing import Any

from wikiarena.core.interfaces import PageSnapshot
from wikiarena.core.interfaces import ParticipantDecision
from wikiarena.protocol.enums import ResponseContract
from wikiarena.protocol.results import ModelCallMetrics
from wikiarena.protocol.results import StepAttemptRecord
from wikiarena.protocol.rules import HarnessConfig
from wikiarena.protocol.specs import TaskSpec
from wikiarena.providers import ModelProvider
from wikiarena.providers import ProviderMessage
from wikiarena.providers import ProviderMessageRole
from wikiarena.providers import ProviderRequest
from wikiarena.providers import ProviderTool


class ProviderParticipant:
    """Participant driver backed by the new provider abstraction layer."""

    def __init__(
        self,
        *,
        provider_client: ModelProvider,
        model_id: str,
        model_settings: dict[str, Any] | None = None,
    ):
        self.provider_client = provider_client
        self.model_id = model_id
        self.model_settings = dict(
            model_settings or {},
        )

        self._messages: list[ProviderMessage] = []
        self._active_task_id: str | None = None
        self._last_page_title: str | None = None
        self._pending_tool_call_id: str | None = None

    async def choose_link(
        self,
        task: TaskSpec,
        current_page: PageSnapshot,
        harness_config: HarnessConfig,
    ) -> ParticipantDecision:
        self._ensure_messages_for_turn(
            task=task,
            current_page=current_page,
        )

        tools: list[ProviderTool] = []
        if harness_config.response_contract == ResponseContract.TOOL_CALL_ONLY:
            tools = [
                _build_navigate_tool(
                    tool_name=harness_config.tool_name,
                ),
            ]

        response = await self.provider_client.generate(
            ProviderRequest(
                model_id=self.model_id,
                messages=list(self._messages),
                tools=tools,
                settings=self.model_settings,
            ),
        )

        self._messages.append(
            response.message,
        )

        model_metrics = ModelCallMetrics(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.total_tokens,
            cache_creation_input_tokens=response.usage.cache_creation_input_tokens,
            cache_read_input_tokens=response.usage.cache_read_input_tokens,
            estimated_cost_usd=response.usage.estimated_cost_usd,
            response_time_ms=response.usage.response_time_ms,
        )

        if harness_config.response_contract == ResponseContract.TOOL_CALL_ONLY:
            if response.message.tool_calls:
                first_tool_call = response.message.tool_calls[0]
                self._pending_tool_call_id = first_tool_call.id
                selected_link = _extract_link_from_arguments(
                    first_tool_call.arguments,
                )
                return ParticipantDecision(
                    selected_link_text=selected_link,
                    raw_response=response.message.content,
                    tool_call_name=first_tool_call.name,
                    tool_call_id=first_tool_call.id,
                    model_metrics=model_metrics,
                )

            self._pending_tool_call_id = None
            return ParticipantDecision(
                selected_link_text=None,
                raw_response=response.message.content,
                tool_call_name=None,
                tool_call_id=None,
                model_metrics=model_metrics,
            )

        selected_link_from_text = None
        if harness_config.response_contract == ResponseContract.STRUCTURED_OUTPUT_ONLY:
            selected_link_from_text = _extract_link_from_text(
                response.message.content,
            )

        self._pending_tool_call_id = None
        return ParticipantDecision(
            selected_link_text=selected_link_from_text,
            raw_response=response.message.content,
            model_metrics=model_metrics,
        )

    async def record_step_feedback(
        self,
        *,
        step_attempt: StepAttemptRecord,
    ) -> None:
        if step_attempt.outcome.value == "move_committed":
            if self._pending_tool_call_id is not None:
                self._messages.append(
                    ProviderMessage(
                        role=ProviderMessageRole.TOOL,
                        tool_call_id=self._pending_tool_call_id,
                        content=(
                            f"Successfully navigated to '{step_attempt.resolved_to_page_title}'."
                        ),
                        is_error=False,
                    ),
                )
            self._last_page_title = step_attempt.resolved_to_page_title
            self._pending_tool_call_id = None
            return

        rejection_code = step_attempt.rejection_reason_code or "unknown"
        if self._pending_tool_call_id is not None:
            self._messages.append(
                ProviderMessage(
                    role=ProviderMessageRole.TOOL,
                    tool_call_id=self._pending_tool_call_id,
                    content=f"Error: {rejection_code}",
                    is_error=True,
                ),
            )

        self._messages.append(
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="Choose a valid link from the current page.",
            ),
        )

        self._pending_tool_call_id = None

    def _ensure_messages_for_turn(
        self,
        *,
        task: TaskSpec,
        current_page: PageSnapshot,
    ) -> None:
        if self._active_task_id != task.task_id:
            self._reset_messages(
                task=task,
                current_page=current_page,
            )
            return

        if self._last_page_title != current_page.title:
            self._messages.append(
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content=_build_current_page_message(
                        current_page,
                    ),
                ),
            )
            self._last_page_title = current_page.title

    def _reset_messages(
        self,
        *,
        task: TaskSpec,
        current_page: PageSnapshot,
    ) -> None:
        self._messages = [
            ProviderMessage(
                role=ProviderMessageRole.SYSTEM,
                content=(
                    "You are in the Wiki Arena.\n"
                    f"Start Page: '{task.start_page_title}'\n"
                    f"Target Page: '{task.target_page_title}'\n"
                    "Use the provided navigation tool to move one step at a time."
                ),
            ),
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content=_build_current_page_message(
                    current_page,
                ),
            ),
        ]
        self._active_task_id = task.task_id
        self._last_page_title = current_page.title
        self._pending_tool_call_id = None


def _build_navigate_tool(
    *,
    tool_name: str,
) -> ProviderTool:
    return ProviderTool(
        name=tool_name,
        description="Navigate to a linked Wikipedia page title.",
        input_schema={
            "type": "object",
            "properties": {
                "to_page_title": {
                    "type": "string",
                    "description": "Wikipedia page title to navigate to",
                },
            },
            "required": ["to_page_title"],
        },
    )


def _build_current_page_message(
    page_snapshot: PageSnapshot,
) -> str:
    return (
        f"You are currently on the page '{page_snapshot.title}'.\n"
        f"Here are the available links:\n{page_snapshot.links}"
    )


def _extract_link_from_arguments(
    arguments: dict[str, Any],
) -> str | None:
    candidate_keys = [
        "to_page_title",
        "page_title",
        "page",
        "title",
    ]
    for key in candidate_keys:
        value = arguments.get(
            key,
        )
        if (
            isinstance(
                value,
                str,
            )
            and value.strip()
        ):
            return value.strip()
    return None


def _extract_link_from_text(
    model_text: str | None,
) -> str | None:
    if model_text is None:
        return None

    stripped_text = model_text.strip()
    if not stripped_text:
        return None

    try:
        parsed_json = json.loads(
            stripped_text,
        )
    except json.JSONDecodeError:
        parsed_json = None

    if isinstance(
        parsed_json,
        dict,
    ):
        extracted_link = _extract_link_from_arguments(
            parsed_json,
        )
        if extracted_link:
            return extracted_link

    first_line = stripped_text.splitlines()[0].strip()
    if first_line:
        return first_line
    return None
