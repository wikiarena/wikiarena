from __future__ import annotations

import json
from typing import Any, Protocol

from wikiarena.core.interfaces import PageSnapshot, ParticipantDecision
from wikiarena.protocol.enums import ResponseContract
from wikiarena.protocol.results import ModelCallMetrics, StepAttemptRecord
from wikiarena.protocol.rules import HarnessConfig
from wikiarena.protocol.specs import TaskSpec
from wikiarena.providers import (
    ModelProvider,
    ProviderMessage,
    ProviderMessageRole,
    ProviderRequest,
    ProviderResponse,
    ProviderTool,
    ProviderToolCall,
)


class ParticipantTraceSink(Protocol):
    def record_message(
        self,
        message: ProviderMessage,
    ) -> None: ...

    def before_request(
        self,
        *,
        model_id: str,
        tools: list[ProviderTool],
    ) -> None: ...

    def after_response(
        self,
        response: ProviderResponse,
    ) -> None: ...

    def record_page_context_message(
        self,
        *,
        message: ProviderMessage,
        page_title: str,
        target_page_title: str,
        links: list[str],
    ) -> None: ...


class ProviderParticipant:
    """Participant driver backed by the new provider abstraction layer."""

    def __init__(
        self,
        *,
        provider_client: ModelProvider,
        model_id: str,
        model_settings: dict[str, Any] | None = None,
        trace_sink: ParticipantTraceSink | None = None,
    ):
        self.provider_client = provider_client
        self.model_id = model_id
        self.model_settings = dict(
            model_settings or {},
        )
        self.trace_sink = trace_sink

        self._messages: list[ProviderMessage] = []
        self._active_task_id: str | None = None
        self._active_tool_name: str | None = None
        self._last_page_title: str | None = None
        self._pending_tool_call_ids: list[str] = []
        self._pending_tool_call_id: str | None = None
        self._pending_success_tool_call_id: str | None = None

    async def choose_link(
        self,
        task: TaskSpec,
        current_page: PageSnapshot,
        harness_config: HarnessConfig,
    ) -> ParticipantDecision:
        self._active_tool_name = harness_config.tool_name
        self._ensure_messages_for_turn(
            task=task,
            current_page=current_page,
            harness_config=harness_config,
        )

        tools: list[ProviderTool] = []
        if harness_config.response_contract == ResponseContract.TOOL_CALL_ONLY:
            tools = [
                _build_navigate_tool(
                    tool_name=harness_config.tool_name,
                ),
            ]

        if self.trace_sink is not None:
            self.trace_sink.before_request(
                model_id=self.model_id,
                tools=tools,
            )

        response = await self.provider_client.generate(
            ProviderRequest(
                model_id=self.model_id,
                messages=list(self._messages),
                tools=tools,
                settings=self.model_settings,
            ),
        )

        self._append_message(
            response.message,
        )
        if self.trace_sink is not None:
            self.trace_sink.after_response(
                response,
            )

        model_metrics = ModelCallMetrics(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.total_tokens,
            cache_creation_input_tokens=response.usage.cache_creation_input_tokens,
            cache_read_input_tokens=response.usage.cache_read_input_tokens,
            input_token_details=dict(
                response.usage.input_token_details,
            ),
            output_token_details=dict(
                response.usage.output_token_details,
            ),
            estimated_cost_usd=response.usage.estimated_cost_usd,
            response_time_ms=response.usage.response_time_ms,
        )

        if harness_config.response_contract == ResponseContract.TOOL_CALL_ONLY:
            if response.message.tool_calls:
                tool_call_ids = [
                    tool_call.id
                    for tool_call in response.message.tool_calls
                ]
                tool_call_names = [
                    tool_call.name
                    for tool_call in response.message.tool_calls
                ]
                self._pending_tool_call_ids = tool_call_ids
                first_tool_call = response.message.tool_calls[0]
                self._pending_tool_call_id = first_tool_call.id
                if len(
                    response.message.tool_calls,
                ) > 1:
                    return ParticipantDecision(
                        selected_link_text=None,
                        raw_response=response.message.content,
                        tool_call_count=len(
                            response.message.tool_calls,
                        ),
                        tool_call_ids=tool_call_ids,
                        tool_call_names=tool_call_names,
                        model_metrics=model_metrics,
                    )
                selected_link = _extract_link_from_arguments(
                    first_tool_call.arguments,
                )
                return ParticipantDecision(
                    selected_link_text=selected_link,
                    raw_response=response.message.content,
                    tool_call_name=first_tool_call.name,
                    tool_call_id=first_tool_call.id,
                    tool_call_count=1,
                    tool_call_ids=tool_call_ids,
                    tool_call_names=tool_call_names,
                    model_metrics=model_metrics,
                )

        selected_link_from_text = None
        if harness_config.response_contract == ResponseContract.STRUCTURED_OUTPUT_ONLY:
            selected_link_from_text = _extract_link_from_text(
                response.message.content,
            )

        self._pending_tool_call_ids = []
        self._pending_tool_call_id = None
        return ParticipantDecision(
            selected_link_text=selected_link_from_text,
            raw_response=response.message.content,
            tool_call_count=0,
            model_metrics=model_metrics,
        )

    async def record_step_feedback(
        self,
        *,
        step_attempt: StepAttemptRecord,
    ) -> None:
        if step_attempt.outcome.value == "move_committed":
            if len(
                self._pending_tool_call_ids,
            ) == 1:
                self._pending_success_tool_call_id = self._pending_tool_call_ids[0]
            elif self._pending_tool_call_id is not None:
                self._pending_success_tool_call_id = self._pending_tool_call_id
            self._pending_tool_call_ids = []
            self._pending_tool_call_id = None
            return

        feedback_message = _build_step_feedback_message(
            step_attempt=step_attempt,
            expected_tool_name=self._active_tool_name,
        )
        if feedback_message is None:
            self._pending_tool_call_ids = []
            self._pending_tool_call_id = None
            return

        pending_tool_call_ids = _pending_tool_call_ids(
            pending_tool_call_ids=self._pending_tool_call_ids,
            pending_tool_call_id=self._pending_tool_call_id,
        )
        if pending_tool_call_ids:
            for tool_call_id in pending_tool_call_ids:
                self._append_message(
                    ProviderMessage(
                        role=ProviderMessageRole.TOOL,
                        tool_call_id=tool_call_id,
                        content=feedback_message,
                        is_error=True,
                    ),
                )
        else:
            self._append_message(
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content=feedback_message,
                ),
            )

        self._pending_tool_call_ids = []
        self._pending_tool_call_id = None

    def _ensure_messages_for_turn(
        self,
        *,
        task: TaskSpec,
        current_page: PageSnapshot,
        harness_config: HarnessConfig,
    ) -> None:
        if self._active_task_id != task.task_id:
            self._reset_messages(
                task=task,
                current_page=current_page,
                harness_config=harness_config,
            )
            return

        if (
            harness_config.response_contract == ResponseContract.TOOL_CALL_ONLY
            and self._pending_success_tool_call_id is not None
        ):
            self._append_page_context_message(
                task=task,
                current_page=current_page,
                message=ProviderMessage(
                    role=ProviderMessageRole.TOOL,
                    tool_call_id=self._pending_success_tool_call_id,
                    content=_build_current_page_message(
                        current_page,
                    ),
                    is_error=False,
                ),
            )
            self._pending_success_tool_call_id = None
            self._last_page_title = current_page.title
            return

        if self._last_page_title != current_page.title:
            self._append_page_context_message(
                task=task,
                current_page=current_page,
                message=ProviderMessage(
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
        harness_config: HarnessConfig,
    ) -> None:
        self._messages = []
        self._append_message(
            ProviderMessage(
                role=ProviderMessageRole.SYSTEM,
                content=(
                    "You are in the Wiki Arena playing the Wikipedia race game.\n"
                    "Your goal is to navigate from the starting Wikipedia page "
                    "to the target Wikipedia page.\n"
                    "At each step, you may move only by selecting a link that "
                    "appears on the current page.\n"
                    "Use the provided navigation tool for every move.\n"
                    "Call exactly one navigation tool per response; multiple "
                    "tool calls in one response are invalid and no move will be made.\n"
                    "Do not invent links that are not present on the current page."
                ),
            ),
        )
        self._append_message(
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content=(
                    f"Navigate from '{task.start_page_title}' to "
                    f"'{task.target_page_title}'."
                ),
            ),
        )

        if harness_config.response_contract == ResponseContract.TOOL_CALL_ONLY:
            bootstrap_tool_call_id = "bootstrap_navigate_start"
            self._append_message(
                ProviderMessage(
                    role=ProviderMessageRole.ASSISTANT,
                    tool_calls=[
                        ProviderToolCall(
                            id=bootstrap_tool_call_id,
                            name=harness_config.tool_name,
                            arguments={
                                "to_page_title": current_page.title,
                            },
                        ),
                    ],
                ),
            )
            self._append_page_context_message(
                task=task,
                current_page=current_page,
                message=ProviderMessage(
                    role=ProviderMessageRole.TOOL,
                    tool_call_id=bootstrap_tool_call_id,
                    content=_build_current_page_message(
                        current_page,
                    ),
                    is_error=False,
                ),
            )
        else:
            self._append_page_context_message(
                task=task,
                current_page=current_page,
                message=ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content=_build_current_page_message(
                        current_page,
                    ),
                ),
            )

        self._active_task_id = task.task_id
        self._active_tool_name = harness_config.tool_name
        self._last_page_title = current_page.title
        self._pending_tool_call_ids = []
        self._pending_tool_call_id = None
        self._pending_success_tool_call_id = None

    def _append_message(
        self,
        message: ProviderMessage,
    ) -> None:
        self._messages.append(
            message,
        )
        if self.trace_sink is not None:
            self.trace_sink.record_message(
                message,
            )

    def _append_page_context_message(
        self,
        *,
        task: TaskSpec,
        current_page: PageSnapshot,
        message: ProviderMessage,
    ) -> None:
        self._messages.append(
            message,
        )
        if self.trace_sink is None:
            return

        record_page_context_message = getattr(
            self.trace_sink,
            "record_page_context_message",
            None,
        )
        if callable(
            record_page_context_message,
        ):
            record_page_context_message(
                message=message,
                page_title=current_page.title,
                target_page_title=task.target_page_title,
                links=current_page.links,
            )
            return

        self.trace_sink.record_message(
            message,
        )


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


def _build_step_feedback_message(
    *,
    step_attempt: StepAttemptRecord,
    expected_tool_name: str | None,
) -> str | None:
    rejection_code = step_attempt.rejection_reason_code
    if rejection_code is None and step_attempt.error is None:
        return None

    tool_name = _resolve_expected_tool_name(
        step_attempt=step_attempt,
        expected_tool_name=expected_tool_name,
    )
    tool_example = _format_tool_call_example(
        tool_name=tool_name,
    )
    current_page_title = step_attempt.from_page_title
    base_lines = [
        "Invalid move.",
        (
            f"You are still on '{current_page_title}'; the links listed on the current page have not "
            "changed."
        ),
    ]

    if rejection_code == "harness.tool_call_required":
        base_lines.append(
            f"Reason: Only `{tool_name}` is allowed for moves.",
        )
        base_lines.append(
            f"Fix: If you want to move, call {tool_example}.",
        )
        return "\n".join(base_lines)

    if rejection_code == "rule.tool_not_allowed":
        actual_tool = _string_detail(
            step_attempt,
            "actual_tool",
        ) or "a different tool"
        base_lines.append(
            f"Reason: You called `{actual_tool}` but only `{tool_name}` is allowed for moves.",
        )
        base_lines.append(
            f"Fix: If you want to move, call {tool_example}.",
        )
        return "\n".join(base_lines)

    if rejection_code == "harness.missing_link_selection":
        base_lines.append(
            f"Reason: Your `{tool_name}` call did not include a destination page title.",
        )
        base_lines.append(
            (
                "Fix: Call "
                f"{tool_example} using one exact link title from the current page."
            ),
        )
        return "\n".join(base_lines)

    if rejection_code == "harness.multiple_tool_calls":
        tool_call_count = _int_detail(
            step_attempt,
            "tool_call_count",
        )
        count_text = str(
            tool_call_count,
        ) if tool_call_count is not None else "multiple"
        base_lines.append(
            "Reason: You called "
            f"{count_text} tools, but WikiArena allows exactly one navigation tool call per step.",
        )
        base_lines.append(
            "Fix: Call exactly one "
            f"{tool_example} for the single link you want to click next.",
        )
        return "\n".join(base_lines)

    if rejection_code == "rule.link_not_present":
        selected_link = step_attempt.selected_link_text or "that title"
        base_lines.append(
            f"Reason: '{selected_link}' is not one of the links listed on the current page.",
        )
        base_lines.append(
            (
                "Fix: Call "
                f"{tool_example} using one exact title from the links already listed "
                "above. Do not paraphrase or guess."
            ),
        )
        return "\n".join(base_lines)

    if rejection_code == "wiki.resolve_navigation_missing_target":
        selected_link = (
            step_attempt.requested_to_page_title
            or step_attempt.selected_link_text
            or "that link"
        )
        base_lines.append(
            f"Reason: The wiki could not resolve your selected link '{selected_link}'.",
        )
        base_lines.append(
            f"Fix: Call {tool_example} with a different exact link title from the current page.",
        )
        return "\n".join(base_lines)

    error_message = step_attempt.error.message if step_attempt.error is not None else None
    reason_text = error_message or rejection_code or "the move was rejected"
    base_lines.append(
        f"Reason: {reason_text}.",
    )
    base_lines.append(
        f"Fix: Call {tool_example} using one exact link title from the current page.",
    )
    return "\n".join(base_lines)


def _pending_tool_call_ids(
    *,
    pending_tool_call_ids: list[str],
    pending_tool_call_id: str | None,
) -> list[str]:
    if pending_tool_call_ids:
        return list(
            pending_tool_call_ids,
        )
    if pending_tool_call_id is not None:
        return [pending_tool_call_id]
    return []


def _resolve_expected_tool_name(
    *,
    step_attempt: StepAttemptRecord,
    expected_tool_name: str | None,
) -> str:
    error_tool_name = _string_detail(
        step_attempt,
        "expected_tool",
    )
    if error_tool_name is not None:
        return error_tool_name
    if expected_tool_name is not None and expected_tool_name.strip():
        return expected_tool_name.strip()
    return "navigate"


def _string_detail(
    step_attempt: StepAttemptRecord,
    key: str,
) -> str | None:
    if step_attempt.error is None:
        return None
    value = step_attempt.error.details.get(
        key,
    )
    if isinstance(
        value,
        str,
    ) and value.strip():
        return value.strip()
    return None


def _int_detail(
    step_attempt: StepAttemptRecord,
    key: str,
) -> int | None:
    if step_attempt.error is None:
        return None
    value = step_attempt.error.details.get(
        key,
    )
    if isinstance(
        value,
        int,
    ):
        return value
    return None


def _format_tool_call_example(
    *,
    tool_name: str,
) -> str:
    return f'`{tool_name}({{"to_page_title": "<exact link title from the current page>"}})`'


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
