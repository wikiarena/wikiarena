from __future__ import annotations

from datetime import datetime
from io import StringIO

from rich.console import Console

from wikiarena.cli_output import (
    EvalProgressReporter,
    RunTraceRenderer,
    _format_page_context_trace_text,
)
from wikiarena.protocol import (
    ErrorRecord,
    EventEnvelope,
    RunEventType,
    RunResult,
    SolverBackend,
    StepAttemptRecord,
    StepOutcome,
    StepSolverMetrics,
    TerminalOutcome,
    TerminationReason,
)
from wikiarena.providers.types import (
    ProviderMessage,
    ProviderMessageRole,
    ProviderResponse,
    ProviderTool,
    ProviderToolCall,
    ProviderUsage,
)
from wikiarena.solver.models import PositionSolverFacts


def _build_console(buffer: StringIO) -> Console:
    return Console(
        file=buffer,
        force_terminal=False,
        color_system=None,
        width=120,
        soft_wrap=True,
    )


def test_run_trace_renderer_prints_incremental_transcript() -> None:
    buffer = StringIO()
    renderer = RunTraceRenderer(
        console=_build_console(buffer),
    )

    renderer.record_message(
        ProviderMessage(
            role=ProviderMessageRole.SYSTEM,
            content="You are in the Wiki Arena.",
        ),
    )
    renderer.record_message(
        ProviderMessage(
            role=ProviderMessageRole.USER,
            content="Current page: Apple\nLinks: Banana",
        ),
    )
    renderer.before_request(
        model_id="gpt-5.2",
        tools=[
            ProviderTool(
                name="navigate",
                description="Navigate to a linked page title.",
                input_schema={
                    "type": "object",
                },
            ),
        ],
    )
    renderer.record_message(
        ProviderMessage(
            role=ProviderMessageRole.ASSISTANT,
            thinking="I should choose Banana because it reaches the target.",
            content="Navigating now.",
            tool_calls=[
                ProviderToolCall(
                    id="tool-1",
                    name="navigate",
                    arguments={
                        "link_text": "Banana",
                    },
                ),
            ],
        ),
    )
    renderer.after_response(
        ProviderResponse(
            message=ProviderMessage(
                role=ProviderMessageRole.ASSISTANT,
            ),
            usage=ProviderUsage(
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
                input_token_details={
                    "cached_tokens": 8,
                },
                output_token_details={
                    "reasoning_tokens": 3,
                },
                response_time_ms=1234,
            ),
        ),
    )
    renderer.record_message(
        ProviderMessage(
            role=ProviderMessageRole.TOOL,
            content="Successfully navigated to 'Banana'.",
            tool_call_id="tool-1",
        ),
    )
    renderer.after_step_attempt(
        StepAttemptRecord(
            step_index=1,
            move_index=1,
            from_page_title="Apple",
            selected_link_text="Banana",
            requested_to_page_title="Banana",
            resolved_to_page_title="Banana",
            was_redirect=False,
            outcome=StepOutcome.MOVE_COMMITTED,
            consumed_step_budget=True,
            solver_metrics=StepSolverMetrics(
                distance_before=1,
                distance_after=0,
            ),
            occurred_at=datetime(2026, 1, 1, 0, 0, 1),
        ),
    )
    renderer.after_run_result(
        RunResult(
            run_id="run-1",
            race_id="race-1",
            benchmark_id="benchmark-1",
            task_id="en__apple__banana",
            participant_id="gpt_5_2",
            terminal_outcome=TerminalOutcome.SUCCESS,
            termination_reason=TerminationReason.TASK_COMPLETED,
            committed_moves=[],
            solver_backend=SolverBackend.LOCAL,
            started_at=datetime(2026, 1, 1, 0, 0, 0),
            ended_at=datetime(2026, 1, 1, 0, 0, 2),
        ),
    )

    output = buffer.getvalue()
    assert "Model Call 1 | gpt-5.2" in output
    assert "<|system|>" in output
    assert "<|tools|>" in output
    assert "<|user|>" in output
    assert "<|assistant|>" in output
    assert "<|thinking|>" in output
    assert "I should choose Banana because it reaches the target." in output
    assert "<|tool_call|>" in output
    assert "<|tool_result|>" in output
    assert "Outcome: move_committed -> Banana | distance 1 -> 0" in output
    assert "Run Complete | success | task_completed" in output
    assert "input.cached_tokens 8" in output
    assert "output.reasoning_tokens 3" in output


def test_run_trace_renderer_prints_only_new_messages_after_first_request() -> None:
    buffer = StringIO()
    renderer = RunTraceRenderer(
        console=_build_console(buffer),
    )

    tools = [
        ProviderTool(
            name="navigate",
            description="Navigate to a linked page title.",
            input_schema={
                "type": "object",
            },
        ),
    ]

    renderer.record_message(
        ProviderMessage(
            role=ProviderMessageRole.SYSTEM,
            content="You are in the Wiki Arena.",
        ),
    )
    renderer.record_message(
        ProviderMessage(
            role=ProviderMessageRole.USER,
            content="Current page: Apple\nLinks: Banana",
        ),
    )
    renderer.before_request(
        model_id="gpt-5.2",
        tools=tools,
    )
    renderer.record_message(
        ProviderMessage(
            role=ProviderMessageRole.ASSISTANT,
            content="Navigating now.",
            tool_calls=[
                ProviderToolCall(
                    id="tool-1",
                    name="navigate",
                    arguments={
                        "to_page_title": "Banana",
                    },
                ),
            ],
        ),
    )
    renderer.after_response(
        ProviderResponse(
            message=ProviderMessage(
                role=ProviderMessageRole.ASSISTANT,
            ),
            usage=ProviderUsage(
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
                response_time_ms=1234,
            ),
        ),
    )
    renderer.record_message(
        ProviderMessage(
            role=ProviderMessageRole.TOOL,
            content="You are currently on the page 'Banana'.\nHere are the available links:\n['Cherry']",
            tool_call_id="tool-1",
        ),
    )
    renderer.before_request(
        model_id="gpt-5.2",
        tools=tools,
    )

    output = buffer.getvalue()
    assert output.count("Model Call") == 2
    assert output.count("You are in the Wiki Arena.") == 1
    assert output.count("<|tools|>") == 1
    assert output.count("Navigating now.") == 1
    assert output.count("You are currently on the page 'Banana'.") == 1


def test_run_trace_renderer_does_not_force_deferred_page_context_after_response() -> None:
    buffer = StringIO()
    renderer = RunTraceRenderer(
        console=_build_console(buffer),
        defer_page_context_solver_facts=True,
    )

    renderer.record_page_context_message(
        message=ProviderMessage(
            role=ProviderMessageRole.TOOL,
            content="You are currently on the page 'Apple'.",
            tool_call_id="tool-1",
        ),
        page_title="Apple",
        target_page_title="Banana",
        links=[
            "Cherry",
        ],
    )
    renderer.record_message(
        ProviderMessage(
            role=ProviderMessageRole.ASSISTANT,
            content="Choosing Cherry.",
        ),
    )

    renderer.after_response(
        ProviderResponse(
            message=ProviderMessage(
                role=ProviderMessageRole.ASSISTANT,
            ),
            usage=ProviderUsage(
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
                response_time_ms=1234,
            ),
        ),
    )

    output = buffer.getvalue()
    assert "You are currently on the page 'Apple'." not in output
    assert "Choosing Cherry." not in output

    renderer.record_position_solver_facts(
        PositionSolverFacts(
            page_title="Apple",
            target_page_title="Banana",
            shortest_path_length=2,
            shortest_paths=[
                [
                    "Apple",
                    "Cherry",
                    "Banana",
                ],
            ],
            shortest_next_hop_titles=[
                "Cherry",
            ],
        ),
        event_sequence=3,
        step_index=1,
        move_index=1,
    )

    output = buffer.getvalue()
    assert "Solve | step 1 | move 1" in output
    assert "page Apple" in output
    assert "target Banana" in output
    assert "distance 2" in output
    assert "paths 1" in output
    assert "optimal_links 1" in output
    assert output.count("You are currently on the page 'Apple'.") == 1
    assert output.count("Choosing Cherry.") == 1
    assert "'Cherry'" in output


def test_run_trace_renderer_defers_page_context_until_solver_facts() -> None:
    buffer = StringIO()
    renderer = RunTraceRenderer(
        console=_build_console(buffer),
        defer_page_context_solver_facts=True,
    )

    renderer.record_page_context_message(
        message=ProviderMessage(
            role=ProviderMessageRole.TOOL,
            content="You are currently on the page 'Apple'.",
            tool_call_id="tool-1",
        ),
        page_title="Apple",
        target_page_title="Banana",
        links=[
            "Cherry",
            "Date palm",
        ],
    )
    renderer.before_request(
        model_id="gpt-5.2",
        tools=[],
    )

    assert "You are currently on the page 'Apple'." not in buffer.getvalue()

    renderer.record_position_solver_facts(
        PositionSolverFacts(
            page_title="Apple",
            target_page_title="Banana",
            shortest_path_length=2,
            shortest_paths=[
                [
                    "Apple",
                    "Cherry",
                    "Banana",
                ],
            ],
            shortest_next_hop_titles=[
                "Cherry",
            ],
        ),
    )

    output = buffer.getvalue()
    assert "Solve |" in output
    assert output.count("You are currently on the page 'Apple'.") == 1
    assert "'Cherry'" in output
    assert "'Date palm'" in output


def test_page_context_trace_text_highlights_shortest_next_hops_with_background() -> None:
    text = _format_page_context_trace_text(
        page_title="Apple",
        links=[
            "Cherry",
            "Date palm",
        ],
        highlighted_links={
            "Cherry",
        },
        base_style="green",
    )

    highlighted_link_start = text.plain.index(
        "'Cherry'",
    )
    highlighted_span = next(
        span
        for span in text.spans
        if span.start <= highlighted_link_start < span.end
    )

    assert str(highlighted_span.style) == "bold black on yellow"


def test_page_context_trace_text_highlights_normalized_next_hop_titles() -> None:
    text = _format_page_context_trace_text(
        page_title="Apple",
        links=[
            "1-butanol",
            "Date palm",
        ],
        highlighted_links={
            "1-Butanol",
        },
        base_style="green",
    )

    highlighted_link_start = text.plain.index(
        "'1-butanol'",
    )
    highlighted_span = next(
        span
        for span in text.spans
        if span.start <= highlighted_link_start < span.end
    )

    assert str(highlighted_span.style) == "bold black on yellow"


def test_run_trace_renderer_prints_terminal_error_details() -> None:
    buffer = StringIO()
    renderer = RunTraceRenderer(
        console=_build_console(buffer),
    )

    renderer.after_run_result(
        RunResult(
            run_id="run-1",
            race_id="race-1",
            benchmark_id="benchmark-1",
            task_id="en__apple__banana",
            participant_id="gpt_5_2",
            terminal_outcome=TerminalOutcome.SYSTEM_FAILURE,
            termination_reason=TerminationReason.INFRASTRUCTURE_ERROR,
            error=ErrorRecord(
                scope="run",
                code="infrastructure.dependency_call_failed",
                message="participant or wiki dependency failed while executing run",
                retryable=False,
                details={
                    "exception_type": "ProviderConfigurationError",
                    "exception_message": (
                        "Missing required api_key for provider 'openai'"
                    ),
                },
            ),
            committed_moves=[],
            solver_backend=SolverBackend.LOCAL,
            started_at=datetime(2026, 1, 1, 0, 0, 0),
            ended_at=datetime(2026, 1, 1, 0, 0, 2),
        ),
    )

    output = buffer.getvalue()
    assert "Run Complete | system_failure | infrastructure_error" in output
    assert "Error code: infrastructure.dependency_call_failed" in output
    assert (
        "Exception: ProviderConfigurationError: Missing required api_key for provider 'openai'"
        in output
    )
    assert "Hint: Set OPENAI_API_KEY" in output


def test_run_trace_renderer_prints_codex_auth_hint() -> None:
    buffer = StringIO()
    renderer = RunTraceRenderer(
        console=_build_console(buffer),
    )

    renderer.after_run_result(
        RunResult(
            run_id="run-2",
            race_id="race-2",
            benchmark_id="benchmark-1",
            task_id="en__apple__banana",
            participant_id="gpt_5_4",
            terminal_outcome=TerminalOutcome.SYSTEM_FAILURE,
            termination_reason=TerminationReason.INFRASTRUCTURE_ERROR,
            error=ErrorRecord(
                scope="run",
                code="infrastructure.dependency_call_failed",
                message="participant or wiki dependency failed while executing run",
                retryable=False,
                details={
                    "exception_type": "ProviderConfigurationError",
                    "exception_message": (
                        "Missing required auth_file for provider 'codex'"
                    ),
                },
            ),
            committed_moves=[],
            solver_backend=SolverBackend.LOCAL,
            started_at=datetime(2026, 1, 1, 0, 0, 0),
            ended_at=datetime(2026, 1, 1, 0, 0, 2),
        ),
    )

    output = buffer.getvalue()
    assert "Missing required auth_file for provider 'codex'" in output
    assert "Hint: Run `codex login`" in output
    assert "CODEX_AUTH_FILE" in output


def test_eval_progress_reporter_prints_run_and_race_lines() -> None:
    buffer = StringIO()
    reporter = EvalProgressReporter(
        console=_build_console(buffer),
        total_runs=2,
        total_races=1,
        participant_count=2,
    )

    reporter.print_start(
        benchmark_id="benchmark-1",
        participant_ids=["gpt_5_2", "claude_sonnet_4_6"],
        navigation_backend="live",
        solver_backend="local",
    )
    reporter.handle_event(
        EventEnvelope(
            event_id="run-1:1",
            event_type=RunEventType.RUN_STARTED,
            benchmark_id="benchmark-1",
            race_id="race-1",
            run_id="run-1",
            sequence=1,
            payload={
                "participant_id": "gpt_5_2",
                "task_id": "en__apple__banana",
            },
        ),
    )
    reporter.handle_event(
        EventEnvelope(
            event_id="run-2:1",
            event_type=RunEventType.RUN_STARTED,
            benchmark_id="benchmark-1",
            race_id="race-1",
            run_id="run-2",
            sequence=1,
            payload={
                "participant_id": "claude_sonnet_4_6",
                "task_id": "en__apple__banana",
            },
        ),
    )
    reporter.handle_event(
        EventEnvelope(
            event_id="run-1:2",
            event_type=RunEventType.RUN_TERMINATED,
            benchmark_id="benchmark-1",
            race_id="race-1",
            run_id="run-1",
            sequence=2,
            payload={
                "terminal_outcome": "success",
                "termination_reason": "task_completed",
                "total_committed_moves": 4,
                "total_invalid_attempts": 1,
            },
        ),
    )
    reporter.handle_event(
        EventEnvelope(
            event_id="run-2:2",
            event_type=RunEventType.RUN_TERMINATED,
            benchmark_id="benchmark-1",
            race_id="race-1",
            run_id="run-2",
            sequence=2,
            payload={
                "terminal_outcome": "model_failure",
                "termination_reason": "dead_end",
                "total_committed_moves": 3,
                "total_invalid_attempts": 0,
            },
        ),
    )

    output = buffer.getvalue()
    assert "Starting benchmark benchmark-1" in output
    assert (
        "[run 1/2] gpt_5_2 | en__apple__banana | success (task_completed) | moves 4 | invalid 1"
        in output
    )
    assert (
        "[run 2/2] claude_sonnet_4_6 | en__apple__banana | model_failure (dead_end) | moves 3 | invalid 0"
        in output
    )
    assert (
        "[race 1/1] en__apple__banana | gpt_5_2=success/moves:4 | claude_sonnet_4_6=model_failure/moves:3 | race-1"
        in output
    )
