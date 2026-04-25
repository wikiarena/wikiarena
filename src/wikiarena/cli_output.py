from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console
from rich.text import Text

from wikiarena.protocol.errors import ErrorRecord
from wikiarena.protocol.events import EventEnvelope
from wikiarena.protocol.results import RunResult, StepAttemptRecord
from wikiarena.providers.types import (
    ProviderMessage,
    ProviderMessageRole,
    ProviderResponse,
    ProviderTool,
    ProviderToolCall,
)
from wikiarena.solver.models import PositionSolverFacts

_SYSTEM_STYLE = "magenta"
_TOOLS_STYLE = "bright_black"
_USER_STYLE = "yellow"
_ASSISTANT_STYLE = "bright_blue"
_THINKING_STYLE = "cyan"
_TOOL_CALL_STYLE = "bright_cyan"
_TOOL_RESULT_STYLE = "green"
_SHORTEST_NEXT_HOP_STYLE = "bold black on yellow"
_SUMMARY_STYLE = "bright_black"
_SUCCESS_STYLE = "green"
_ERROR_STYLE = "red"
_WARNING_STYLE = "yellow"
_MISSING_PROVIDER_FIELD_PATTERN = re.compile(
    r"Missing required (?P<field>[a-zA-Z0-9_]+) for provider '(?P<provider>[^']+)'",
)
_PROVIDER_API_KEY_ENV_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openai_compatible": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}
_PROVIDER_FIELD_HINTS = {
    (
        "codex",
        "auth_file",
    ): (
        "Run `codex login` to create ~/.codex/auth.json, or set "
        "CODEX_AUTH_FILE / provider_settings.auth_file in config."
    ),
}


@dataclass
class PageContextTraceMessage:
    message: ProviderMessage
    page_title: str
    target_page_title: str
    links: list[str]


TraceMessage = ProviderMessage | PageContextTraceMessage


@dataclass
class RunTraceRenderer:
    console: Console
    pending_messages: list[TraceMessage] = field(
        default_factory=list,
    )
    request_count: int = 0
    last_tools_signature: str | None = None
    defer_page_context_solver_facts: bool = False
    log_solver_facts: bool = True
    position_solver_facts_by_key: dict[tuple[str, str], PositionSolverFacts] = field(
        default_factory=dict,
    )

    def record_message(
        self,
        message: ProviderMessage,
    ) -> None:
        self.pending_messages.append(
            message.model_copy(
                deep=True,
            ),
        )

    def record_page_context_message(
        self,
        *,
        message: ProviderMessage,
        page_title: str,
        target_page_title: str,
        links: list[str],
    ) -> None:
        self.pending_messages.append(
            PageContextTraceMessage(
                message=message.model_copy(
                    deep=True,
                ),
                page_title=page_title,
                target_page_title=target_page_title,
                links=list(
                    links,
                ),
            ),
        )

    def record_position_solver_facts(
        self,
        position_solver_facts: PositionSolverFacts,
        *,
        event_sequence: int | None = None,
        step_index: int | None = None,
        move_index: int | None = None,
    ) -> None:
        self.position_solver_facts_by_key[
            _position_solver_facts_key(
                page_title=position_solver_facts.page_title,
                target_page_title=position_solver_facts.target_page_title,
            )
        ] = position_solver_facts
        if self.log_solver_facts:
            self._print_solver_facts(
                position_solver_facts=position_solver_facts,
                event_sequence=event_sequence,
                step_index=step_index,
                move_index=move_index,
            )
        self.flush_pending_messages()

    def before_request(
        self,
        *,
        model_id: str,
        tools: list[ProviderTool],
    ) -> None:
        self.request_count += 1
        self._print_header(
            f"Model Call {self.request_count} | {model_id}",
        )
        if self.request_count == 1:
            system_messages, remaining_messages = _split_leading_system_messages(
                self.pending_messages,
            )
            self._print_messages(
                system_messages,
            )
            self._print_tools_block_if_changed(
                tools,
            )
            self.pending_messages = remaining_messages
            self.flush_pending_messages()
            return

        self._print_tools_block_if_changed(
            tools,
        )
        self.flush_pending_messages()

    def after_response(
        self,
        response: ProviderResponse,
    ) -> None:
        self.flush_pending_messages()
        usage = response.usage
        usage_segments = [
            "Response",
            f"{usage.response_time_ms:.0f} ms",
            f"input {usage.input_tokens}",
            f"output {usage.output_tokens}",
            f"total {usage.total_tokens}",
        ]
        usage_segments.extend(
            _format_token_detail_segments(
                prefix="input",
                details=usage.input_token_details,
            ),
        )
        usage_segments.extend(
            _format_token_detail_segments(
                prefix="output",
                details=usage.output_token_details,
            ),
        )
        self.console.print(
            Text(
                " | ".join(
                    usage_segments,
                ),
                style=_SUMMARY_STYLE,
            ),
        )
        self.console.print()

    def after_step_attempt(
        self,
        step_attempt: StepAttemptRecord,
    ) -> None:
        self.flush_pending_messages()
        self.console.print(
            _format_step_outcome_text(
                step_attempt,
            ),
        )
        self.console.print()

    def after_run_result(
        self,
        run_result: RunResult,
    ) -> None:
        self.flush_pending_messages()
        self._print_header(
            (
                "Run Complete | "
                f"{run_result.terminal_outcome.value} | "
                f"{run_result.termination_reason.value} | "
                f"moves {run_result.total_committed_moves} | "
                f"invalid {run_result.total_invalid_attempts} | "
                f"duration {run_result.duration_ms:.0f} ms"
            ),
        )
        for label, value in build_error_summary_lines(
            run_result.error,
        ):
            self.console.print(
                Text(
                    f"{label}: {value}",
                    style=(
                        _WARNING_STYLE
                        if label == "Hint"
                        else _ERROR_STYLE
                    ),
                ),
            )
        self.console.print()

    def flush_pending_messages(
        self,
        *,
        force_deferred: bool = False,
    ) -> None:
        if not self.pending_messages:
            return
        remaining_messages: list[TraceMessage] = []
        blocked = False
        for message in self.pending_messages:
            if blocked:
                remaining_messages.append(
                    message,
                )
                continue

            if (
                isinstance(
                    message,
                    PageContextTraceMessage,
                )
                and self.defer_page_context_solver_facts
                and not force_deferred
                and self._get_position_solver_facts_for_page_context(message) is None
            ):
                remaining_messages.append(
                    message,
                )
                blocked = True
                continue

            self._print_message(
                message,
            )

        self.pending_messages = remaining_messages

    def _print_header(
        self,
        text: str,
    ) -> None:
        self.console.print(
            Text(
                text,
                style="bold",
            ),
        )

    def _print_tools_block_if_changed(
        self,
        tools: list[ProviderTool],
    ) -> None:
        if not tools:
            return
        serialized_tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in tools
        ]
        tools_signature = json.dumps(
            serialized_tools,
            ensure_ascii=False,
            sort_keys=True,
        )
        if tools_signature == self.last_tools_signature:
            return
        self.last_tools_signature = tools_signature
        self._print_tagged_block(
            tag_name="tools",
            content=json.dumps(
                serialized_tools,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            style=_TOOLS_STYLE,
        )

    def _print_messages(
        self,
        messages: list[TraceMessage],
    ) -> None:
        for message in messages:
            self._print_message(
                message,
            )

    def _print_message(
        self,
        message: TraceMessage,
    ) -> None:
        if isinstance(
            message,
            PageContextTraceMessage,
        ):
            self._print_page_context_message(
                message,
            )
            return

        if message.role == ProviderMessageRole.SYSTEM:
            self._print_tagged_block(
                tag_name="system",
                content=message.content or "",
                style=_SYSTEM_STYLE,
            )
            return

        if message.role == ProviderMessageRole.USER:
            self._print_tagged_block(
                tag_name="user",
                content=message.content or "",
                style=_USER_STYLE,
            )
            return

        if message.role == ProviderMessageRole.TOOL:
            self._print_tagged_block(
                tag_name="tool_result",
                content=message.content or "",
                style=_ERROR_STYLE if message.is_error else _TOOL_RESULT_STYLE,
            )
            return

        self._print_assistant_message(
            message,
        )

    def _print_page_context_message(
        self,
        page_context_message: PageContextTraceMessage,
    ) -> None:
        position_solver_facts = self._get_position_solver_facts_for_page_context(
            page_context_message,
        )
        highlighted_links = set()
        if position_solver_facts is not None:
            highlighted_links = set(
                position_solver_facts.shortest_next_hop_titles,
            )
        base_style = _USER_STYLE
        if page_context_message.message.role == ProviderMessageRole.TOOL:
            base_style = _TOOL_RESULT_STYLE
        if page_context_message.message.is_error:
            base_style = _ERROR_STYLE
        content = _format_page_context_trace_text(
            page_title=page_context_message.page_title,
            links=page_context_message.links,
            highlighted_links=highlighted_links,
            base_style=base_style,
        )
        if page_context_message.message.role == ProviderMessageRole.TOOL:
            self._print_tagged_text_block(
                tag_name="tool_result",
                content=content,
                style=(
                    _ERROR_STYLE
                    if page_context_message.message.is_error
                    else _TOOL_RESULT_STYLE
                ),
            )
            return

        self._print_tagged_text_block(
            tag_name="user",
            content=content,
            style=_USER_STYLE,
        )

    def _get_position_solver_facts_for_page_context(
        self,
        page_context_message: PageContextTraceMessage,
    ) -> PositionSolverFacts | None:
        return self.position_solver_facts_by_key.get(
            _position_solver_facts_key(
                page_title=page_context_message.page_title,
                target_page_title=page_context_message.target_page_title,
            ),
        )

    def _print_solver_facts(
        self,
        *,
        position_solver_facts: PositionSolverFacts,
        event_sequence: int | None,
        step_index: int | None,
        move_index: int | None,
    ) -> None:
        del event_sequence

        segments = [
            "Solve",
            f"step {step_index if step_index is not None else '?'}",
            f"move {move_index if move_index is not None else '?'}",
            f"page {position_solver_facts.page_title}",
            f"target {position_solver_facts.target_page_title}",
            f"distance {_format_optional_int(position_solver_facts.shortest_path_length)}",
            f"paths {len(position_solver_facts.shortest_paths)}",
            f"optimal_links {len(position_solver_facts.shortest_next_hop_titles)}",
            f"compute {position_solver_facts.computation_time_ms:.1f} ms",
        ]
        if position_solver_facts.solver_snapshot_id is not None:
            segments.append(
                f"snapshot {position_solver_facts.solver_snapshot_id}",
            )
        self.console.print(
            " | ".join(
                segments,
            ),
        )

    def _print_assistant_message(
        self,
        message: ProviderMessage,
    ) -> None:
        self.console.print(
            Text(
                "<|assistant|>",
                style=_ASSISTANT_STYLE,
            ),
        )
        if message.thinking:
            self._print_tagged_block(
                tag_name="thinking",
                content=message.thinking,
                style=_THINKING_STYLE,
            )
        if message.content:
            self.console.print(
                Text(
                    message.content,
                    style=_ASSISTANT_STYLE,
                ),
            )
        for tool_call in message.tool_calls:
            self._print_tool_call(
                tool_call,
            )
        self.console.print(
            Text(
                "</|assistant|>",
                style=_ASSISTANT_STYLE,
            ),
        )

    def _print_tool_call(
        self,
        tool_call: ProviderToolCall,
    ) -> None:
        payload = {
            "id": tool_call.id,
            "name": tool_call.name,
            "arguments": tool_call.arguments,
        }
        self.console.print(
            Text(
                "<|tool_call|>",
                style=_TOOL_CALL_STYLE,
            ),
        )
        self.console.print(
            Text(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                style=_TOOL_CALL_STYLE,
            ),
        )
        self.console.print(
            Text(
                "</|tool_call|>",
                style=_TOOL_CALL_STYLE,
            ),
        )

    def _print_tagged_block(
        self,
        *,
        tag_name: str,
        content: str,
        style: str,
    ) -> None:
        self.console.print(
            Text(
                f"<|{tag_name}|>",
                style=style,
            ),
        )
        if content:
            self.console.print(
                Text(
                    content,
                    style=style,
                ),
            )
        self.console.print(
            Text(
                f"</|{tag_name}|>",
                style=style,
            ),
        )

    def _print_tagged_text_block(
        self,
        *,
        tag_name: str,
        content: Text,
        style: str,
    ) -> None:
        self.console.print(
            Text(
                f"<|{tag_name}|>",
                style=style,
            ),
        )
        if content.plain:
            self.console.print(
                content,
            )
        self.console.print(
            Text(
                f"</|{tag_name}|>",
                style=style,
            ),
        )


def _split_leading_system_messages(
    messages: list[TraceMessage],
) -> tuple[list[TraceMessage], list[TraceMessage]]:
    system_messages: list[TraceMessage] = []
    remaining_messages: list[TraceMessage] = []
    seen_non_system = False
    for message in messages:
        if (
            not seen_non_system
            and isinstance(
                message,
                ProviderMessage,
            )
            and message.role == ProviderMessageRole.SYSTEM
        ):
            system_messages.append(
                message,
            )
            continue
        seen_non_system = True
        remaining_messages.append(
            message,
        )
    return system_messages, remaining_messages


def _position_solver_facts_key(
    *,
    page_title: str,
    target_page_title: str,
) -> tuple[str, str]:
    return (
        page_title,
        target_page_title,
    )


def _format_optional_int(
    value: int | None,
) -> str:
    if value is None:
        return "?"
    return str(
        value,
    )


def _format_page_context_trace_text(
    *,
    page_title: str,
    links: list[str],
    highlighted_links: set[str],
    base_style: str,
) -> Text:
    normalized_highlighted_links = {
        _normalize_title_for_trace_matching(
            link,
        )
        for link in highlighted_links
    }
    text = Text(
        f"You are currently on the page '{page_title}'.\n"
        "Here are the available links:\n",
        style=base_style,
    )
    text.append(
        "[",
        style=base_style,
    )
    for index, link in enumerate(
        links,
    ):
        if index > 0:
            text.append(
                ", ",
                style=base_style,
            )
        text.append(
            repr(
                link,
            ),
            style=(
                _SHORTEST_NEXT_HOP_STYLE
                if _normalize_title_for_trace_matching(
                    link,
                )
                in normalized_highlighted_links
                else base_style
            ),
        )
    text.append(
        "]",
        style=base_style,
    )
    return text


def _normalize_title_for_trace_matching(
    title: str,
) -> str:
    return title.strip().replace(
        "_",
        " ",
    ).casefold()


def _format_token_detail_segments(
    *,
    prefix: str,
    details: dict[str, int],
) -> list[str]:
    return [
        f"{prefix}.{detail_name} {detail_value}"
        for detail_name, detail_value in sorted(
            details.items(),
        )
        if detail_value != 0
    ]


def build_error_summary_lines(
    error: ErrorRecord | None,
) -> list[tuple[str, str]]:
    if error is None:
        return []

    lines: list[tuple[str, str]] = [
        (
            "Error code",
            error.code,
        ),
        (
            "Error",
            error.message,
        ),
    ]
    exception_type = error.details.get(
        "exception_type",
    )
    exception_message = error.details.get(
        "exception_message",
    )
    if isinstance(
        exception_type,
        str,
    ) and isinstance(
        exception_message,
        str,
    ):
        lines.append(
            (
                "Exception",
                f"{exception_type}: {exception_message}",
            ),
        )
    elif isinstance(
        exception_type,
        str,
    ):
        lines.append(
            (
                "Exception type",
                exception_type,
            ),
        )
    elif isinstance(
        exception_message,
        str,
    ):
        lines.append(
            (
                "Exception",
                exception_message,
            ),
        )

    hint = _build_error_hint(
        error,
    )
    if hint is not None:
        lines.append(
            (
                "Hint",
                hint,
            ),
        )
    return lines


def _build_error_hint(
    error: ErrorRecord,
) -> str | None:
    exception_message = error.details.get(
        "exception_message",
    )
    if not isinstance(
        exception_message,
        str,
    ):
        return None

    missing_field_match = _MISSING_PROVIDER_FIELD_PATTERN.fullmatch(
        exception_message,
    )
    if missing_field_match is not None:
        field_name = missing_field_match.group(
            "field",
        ).strip()
        provider_name = missing_field_match.group(
            "provider",
        ).strip().lower()
        field_hint = _PROVIDER_FIELD_HINTS.get(
            (
                provider_name,
                field_name,
            ),
        )
        if field_hint is not None:
            return field_hint
        if field_name == "api_key":
            env_var_name = _PROVIDER_API_KEY_ENV_VARS.get(
                provider_name,
            )
            if env_var_name is not None:
                return (
                    f"Set {env_var_name} in your environment, or provide "
                    "provider_settings.api_key in config."
                )

    if exception_message.startswith(
        "Unsupported provider ",
    ):
        return "Check --provider and the participant provider configuration."
    if exception_message.endswith(
        "provider request failed",
    ):
        return "Check provider credentials, base URL, and network access."
    if exception_message.endswith(
        "provider timed out",
    ):
        return "Check network access or increase the provider timeout."
    if exception_message.endswith(
        "provider rate limit exceeded",
    ):
        return "Retry later or switch credentials."

    return None


@dataclass
class EvalProgressReporter:
    console: Console
    total_runs: int
    total_races: int
    participant_count: int
    started_runs: dict[str, dict[str, str]] = field(
        default_factory=dict,
    )
    race_results: dict[str, list[dict[str, Any]]] = field(
        default_factory=dict,
    )
    completed_runs: int = 0
    completed_races: int = 0

    def print_start(
        self,
        *,
        benchmark_id: str,
        participant_ids: list[str],
        navigation_backend: str,
        solver_backend: str,
    ) -> None:
        self.console.print(
            Text(
                (
                    f"Starting benchmark {benchmark_id} | "
                    f"runs {self.total_runs} | races {self.total_races} | "
                    f"participants {', '.join(participant_ids)} | "
                    f"navigation {navigation_backend} | solver {solver_backend}"
                ),
                style="bold",
            ),
        )

    def handle_event(
        self,
        event: EventEnvelope,
    ) -> None:
        if event.event_type.value == "run_started":
            self.started_runs[event.run_id] = {
                "participant_id": str(
                    event.payload.get(
                        "participant_id",
                        "unknown",
                    ),
                ),
                "task_id": str(
                    event.payload.get(
                        "task_id",
                        "unknown",
                    ),
                ),
            }
            return

        if event.event_type.value != "run_terminated":
            return

        self.completed_runs += 1
        run_context = self.started_runs.get(
            event.run_id,
            {
                "participant_id": "unknown",
                "task_id": "unknown",
            },
        )
        run_summary = {
            "participant_id": run_context["participant_id"],
            "task_id": run_context["task_id"],
            "terminal_outcome": str(event.payload.get("terminal_outcome", "unknown")),
            "termination_reason": str(
                event.payload.get(
                    "termination_reason",
                    "unknown",
                ),
            ),
            "total_committed_moves": int(
                event.payload.get(
                    "total_committed_moves",
                    0,
                ),
            ),
            "total_invalid_attempts": int(
                event.payload.get(
                    "total_invalid_attempts",
                    0,
                ),
            ),
            "error_code": event.error.code if event.error is not None else None,
            "error_message": (
                event.error.details.get("exception_message")
                if event.error is not None and event.error.details is not None
                else None
            ),
        }
        self._print_run_line(
            run_summary,
        )

        race_runs = self.race_results.setdefault(
            event.race_id,
            [],
        )
        race_runs.append(
            run_summary,
        )
        if len(race_runs) == self.participant_count:
            self.completed_races += 1
            self._print_race_line(
                race_id=event.race_id,
                race_runs=race_runs,
            )

    def _print_run_line(
        self,
        run_summary: dict[str, Any],
    ) -> None:
        outcome_style = _SUCCESS_STYLE
        if run_summary["terminal_outcome"] != "success":
            outcome_style = _ERROR_STYLE
        line = Text()
        line.append(
            f"[run {self.completed_runs}/{self.total_runs}] ",
            style="bold",
        )
        line.append(
            str(run_summary["participant_id"]),
        )
        line.append(" | ")
        line.append(
            str(run_summary["task_id"]),
            style=_SUMMARY_STYLE,
        )
        line.append(" | ")
        line.append(
            str(run_summary["terminal_outcome"]),
            style=outcome_style,
        )
        line.append(
            f" ({run_summary['termination_reason']})",
            style=_SUMMARY_STYLE,
        )
        line.append(
            f" | moves {run_summary['total_committed_moves']} | invalid {run_summary['total_invalid_attempts']}",
            style=_SUMMARY_STYLE,
        )
        if run_summary["error_code"] is not None:
            line.append(
                f" | {run_summary['error_code']}",
                style=_WARNING_STYLE,
            )
            if run_summary["error_message"]:
                line.append(
                    f": {run_summary['error_message']}",
                    style=_WARNING_STYLE,
                )
        self.console.print(
            line,
        )

    def _print_race_line(
        self,
        *,
        race_id: str,
        race_runs: list[dict[str, Any]],
    ) -> None:
        task_id = str(
            race_runs[0]["task_id"],
        )
        segments = [
            (
                f"{run['participant_id']}={run['terminal_outcome']}/moves:{run['total_committed_moves']}",
                _SUCCESS_STYLE
                if run["terminal_outcome"] == "success"
                else _ERROR_STYLE,
            )
            for run in race_runs
        ]
        line = Text()
        line.append(
            f"[race {self.completed_races}/{self.total_races}] ",
            style="bold",
        )
        line.append(
            task_id,
            style=_SUMMARY_STYLE,
        )
        line.append(" | ")
        for index, (segment, style) in enumerate(segments):
            if index > 0:
                line.append(" | ")
            line.append(
                segment,
                style=style,
            )
        line.append(
            f" | {race_id}",
            style=_SUMMARY_STYLE,
        )
        self.console.print(
            line,
        )


def build_stderr_console() -> Console:
    return Console(
        stderr=True,
        soft_wrap=True,
    )
def _format_step_outcome_text(
    step_attempt: StepAttemptRecord,
) -> Text:
    if step_attempt.outcome.value == "move_committed":
        distance_transition = ""
        if step_attempt.solver_metrics is not None:
            distance_transition = (
                f" | distance {step_attempt.solver_metrics.distance_before}"
                f" -> {step_attempt.solver_metrics.distance_after}"
            )
        text = Text()
        text.append(
            "Outcome",
            style=f"bold {_SUCCESS_STYLE}",
        )
        text.append(
            ": move_committed -> ",
        )
        text.append(
            str(step_attempt.resolved_to_page_title),
            style=_SUCCESS_STYLE,
        )
        if distance_transition:
            text.append(
                distance_transition,
                style=_SUMMARY_STYLE,
            )
        return text

    if step_attempt.error is not None:
        text = Text()
        text.append(
            "Outcome",
            style=f"bold {_WARNING_STYLE}",
        )
        text.append(
            f": {step_attempt.outcome.value} ({step_attempt.error.code})",
            style=_WARNING_STYLE,
        )
        return text

    text = Text()
    text.append(
        "Outcome",
        style=f"bold {_WARNING_STYLE}",
    )
    text.append(
        f": {step_attempt.outcome.value}",
        style=_WARNING_STYLE,
    )
    return text
