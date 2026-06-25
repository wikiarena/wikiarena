from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wikiarena.cli import app
from wikiarena.core import RunExecutionArtifact
from wikiarena.eval import (
    BenchmarkExecutionArtifact,
    build_ruleset_hash,
    build_taskset_hash,
)
from wikiarena.graph.info import GraphInfoResult
from wikiarena.graph.install import GraphInstallResult
from wikiarena.protocol import (
    ErrorRecord,
    EventEnvelope,
    HarnessConfig,
    MoveRecord,
    NavigationBackend,
    NavigationRules,
    RaceResult,
    ResponseContract,
    RunEventType,
    RunResult,
    ScoringRules,
    SolverBackend,
    TaskSpec,
    TerminalOutcome,
    TerminationReason,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def _disable_installed_graph_defaults(monkeypatch) -> None:
    def missing_graph(*args, **kwargs):
        del args
        del kwargs
        raise FileNotFoundError("no graph")

    monkeypatch.setattr(
        "wikiarena.cli.resolve_graph_file_path",
        missing_graph,
    )
    monkeypatch.setattr(
        "wikiarena.cli.resolve_solver_graph_file_path",
        missing_graph,
    )


def _build_run_result(
    *,
    run_id: str,
    race_id: str,
    participant_id: str,
    committed_moves: int,
    terminal_outcome: TerminalOutcome = TerminalOutcome.SUCCESS,
    termination_reason: TerminationReason = TerminationReason.TASK_COMPLETED,
    error: ErrorRecord | None = None,
    ruleset_hash: str = "ruleset-1",
    taskset_hash: str = "taskset-1",
) -> RunResult:
    return RunResult(
        run_id=run_id,
        race_id=race_id,
        benchmark_id="benchmark-1",
        task_id="en__apple__banana",
        participant_id=participant_id,
        terminal_outcome=terminal_outcome,
        termination_reason=termination_reason,
        committed_moves=[
            MoveRecord(
                move_index=index,
                source_step_index=index,
                from_page_title=f"page-{index}",
                to_page_title=f"page-{index + 1}",
                occurred_at=datetime(2026, 1, 1, 0, 0, index),
            )
            for index in range(1, committed_moves + 1)
        ],
        ruleset_hash=ruleset_hash,
        taskset_hash=taskset_hash,
        participant_hash=f"participant-{participant_id}",
        error=error,
        solver_backend=SolverBackend.NONE,
        started_at=datetime(2026, 1, 1, 0, 0, 0),
        ended_at=datetime(2026, 1, 1, 0, 0, 1),
        duration_ms=1000.0,
    )


def _single_apple_banana_taskset_hash() -> str:
    return build_taskset_hash(
        [
            TaskSpec(
                language="en",
                start_page_title="Apple",
                target_page_title="Banana",
            ),
        ],
    )


class FakeRunService:
    def __init__(
        self,
    ):
        self.last_request = None

        class FakeRunExecutor:
            protocol_version = "1.0.0-test"

        self.run_executor = FakeRunExecutor()

    async def run(
        self,
        request,
        *,
        event_sink=None,
    ) -> RunExecutionArtifact:
        self.last_request = request
        return RunExecutionArtifact(
            run_result=_build_run_result(
                run_id="run-cli-1",
                race_id="race-cli-1",
                participant_id=request.participant_id or "participant_gpt-x",
                committed_moves=3,
            ),
            events=[],
        )

    async def plan_run(
        self,
        request,
    ):
        self.last_request = request

        class PlannedRun:
            ruleset_hash = "ruleset-1"
            navigation_runtime = request.navigation_runtime
            solver_runtime = request.solver_runtime
            navigation_snapshot_id = request.navigation_snapshot_id
            solver_snapshot_id = request.solver_snapshot_id

        return PlannedRun()

    async def execute_plan(
        self,
        run_plan,
        *,
        event_sink=None,
    ) -> RunExecutionArtifact:
        return RunExecutionArtifact(
            run_result=_build_run_result(
                run_id="run-cli-1",
                race_id="race-cli-1",
                participant_id=(
                    (self.last_request.participant_id or "participant_gpt-x")
                    if self.last_request is not None
                    else "participant_gpt-x"
                ),
                committed_moves=3,
            ),
            events=[],
        )


class FakeBenchmarkRunner:
    def __init__(
        self,
    ):
        self.last_benchmark_spec = None
        self.last_concurrency = None
        self.last_run_options = None
        self.last_resume = None
        self.last_taskset_hash_override = None

        class FakeRunExecutor:
            protocol_version = "1.0.0-test"

        class FakeRunServiceContainer:
            run_executor = FakeRunExecutor()

        self.run_service = FakeRunServiceContainer()

    async def run_benchmark(
        self,
        benchmark_spec,
        *,
        concurrency,
        run_options,
        resume=None,
        taskset_hash_override=None,
        result_store=None,
        event_sink=None,
    ) -> BenchmarkExecutionArtifact:
        self.last_benchmark_spec = benchmark_spec
        self.last_concurrency = concurrency
        self.last_run_options = run_options
        self.last_resume = resume
        self.last_taskset_hash_override = taskset_hash_override

        run_result = _build_run_result(
            run_id="run-benchmark-1",
            race_id="race-benchmark-1",
            participant_id=benchmark_spec.participants[0].participant_id,
            committed_moves=4,
            taskset_hash=taskset_hash_override or "taskset-1",
        )
        result_store.append_artifact(
            RunExecutionArtifact(
                run_result=run_result,
                events=[],
            ),
        )
        if event_sink is not None:
            await event_sink(
                EventEnvelope(
                    event_id="run-benchmark-1:1",
                    event_type=RunEventType.RUN_STARTED,
                    benchmark_id=benchmark_spec.benchmark_id,
                    race_id="race-benchmark-1",
                    run_id="run-benchmark-1",
                    sequence=1,
                    payload={
                        "participant_id": benchmark_spec.participants[0].participant_id,
                    },
                ),
            )

        return BenchmarkExecutionArtifact(
            benchmark_id=benchmark_spec.benchmark_id,
            race_results=[
                RaceResult(
                    race_id="race-benchmark-1",
                    benchmark_id=benchmark_spec.benchmark_id,
                    task_id=benchmark_spec.tasks[0].task_id,
                    run_results=[run_result],
                ),
            ],
            run_results=[run_result],
            started_at=datetime(2026, 1, 1, 0, 0, 0),
            ended_at=datetime(2026, 1, 1, 0, 0, 1),
        )


class FakeCliServices:
    def __init__(
        self,
        *,
        run_service: FakeRunService | None = None,
        benchmark_runner: FakeBenchmarkRunner | None = None,
    ):
        self.run_service = run_service or FakeRunService()
        self.benchmark_runner = benchmark_runner or FakeBenchmarkRunner()

    def create_run_service(
        self,
    ) -> FakeRunService:
        return self.run_service

    def create_benchmark_runner(
        self,
    ) -> FakeBenchmarkRunner:
        return self.benchmark_runner


class FakeFailingRunService(FakeRunService):
    def __init__(
        self,
        *,
        run_result: RunResult,
    ):
        super().__init__()
        self._run_result = run_result

    async def execute_plan(
        self,
        run_plan,
        *,
        event_sink=None,
    ) -> RunExecutionArtifact:
        return RunExecutionArtifact(
            run_result=self._run_result,
            events=[],
        )


def test_run_command_emits_json_and_builds_request(monkeypatch) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-x",
            "--provider",
            "openai",
            "--start",
            "Apple",
            "--target",
            "Banana",
            "--temperature",
            "0.0",
            "--thinking-effort",
            "high",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["run_id"] == "run-cli-1"
    assert fake_services.run_service.last_request is not None
    assert fake_services.run_service.last_request.model_id == "gpt-x"
    assert fake_services.run_service.last_request.model_settings["temperature"] == 0.0
    assert fake_services.run_service.last_request.model_settings["thinking"] == {
        "type": "adaptive",
    }
    assert fake_services.run_service.last_request.model_settings["output_config"] == {
        "effort": "high",
    }
    assert (
        fake_services.run_service.last_request.navigation_runtime.backend
        == NavigationBackend.LIVE
    )


def test_run_command_defaults_openai_reasoning_effort_to_high(monkeypatch) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-x",
            "--provider",
            "openai",
            "--start",
            "Apple",
            "--target",
            "Banana",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert fake_services.run_service.last_request is not None
    assert (
        fake_services.run_service.last_request.model_settings["reasoning_effort"]
        == "high"
    )
    assert fake_services.run_service.last_request.model_settings["openai_api_mode"] == (
        "responses"
    )
    assert (
        fake_services.run_service.last_request.model_settings[
            "openai_use_previous_response_id"
        ]
        is True
    )
    assert (
        "openai_reasoning_summary"
        not in fake_services.run_service.last_request.model_settings
    )


def test_run_command_defaults_codex_reasoning_effort_to_high(monkeypatch) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-5.4",
            "--provider",
            "codex",
            "--start",
            "Apple",
            "--target",
            "Banana",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert fake_services.run_service.last_request is not None
    assert (
        fake_services.run_service.last_request.model_settings["reasoning_effort"]
        == "high"
    )
    assert (
        "openai_api_mode" not in fake_services.run_service.last_request.model_settings
    )


def test_run_command_does_not_default_anthropic_reasoning_effort(monkeypatch) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "claude-test",
            "--provider",
            "anthropic",
            "--start",
            "Apple",
            "--target",
            "Banana",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert fake_services.run_service.last_request is not None
    assert (
        "reasoning_effort" not in fake_services.run_service.last_request.model_settings
    )
    assert "thinking" not in fake_services.run_service.last_request.model_settings
    assert "output_config" not in fake_services.run_service.last_request.model_settings


def test_run_command_trace_does_not_change_anthropic_thinking(monkeypatch) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "claude-test",
            "--provider",
            "anthropic",
            "--start",
            "Apple",
            "--target",
            "Banana",
            "--trace",
        ],
    )

    assert result.exit_code == 0
    assert fake_services.run_service.last_request is not None
    assert "thinking" not in fake_services.run_service.last_request.model_settings
    assert "output_config" not in fake_services.run_service.last_request.model_settings


def test_run_command_enables_openai_responses_reasoning_options(monkeypatch) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-x",
            "--provider",
            "openai",
            "--start",
            "Apple",
            "--target",
            "Banana",
            "--openai-reasoning-summary",
            "auto",
            "--openai-include-encrypted-reasoning",
            "--openai-no-previous-response-id",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert fake_services.run_service.last_request is not None
    assert fake_services.run_service.last_request.model_settings["openai_api_mode"] == (
        "responses"
    )
    assert (
        fake_services.run_service.last_request.model_settings[
            "openai_reasoning_summary"
        ]
        == "auto"
    )
    assert (
        fake_services.run_service.last_request.model_settings[
            "openai_include_encrypted_reasoning"
        ]
        is True
    )
    assert (
        fake_services.run_service.last_request.model_settings[
            "openai_use_previous_response_id"
        ]
        is False
    )


def test_run_command_trace_does_not_change_openai_reasoning_summary(
    monkeypatch,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-x",
            "--provider",
            "openai",
            "--start",
            "Apple",
            "--target",
            "Banana",
            "--trace",
        ],
    )

    assert result.exit_code == 0
    assert fake_services.run_service.last_request is not None
    assert (
        "openai_reasoning_summary"
        not in fake_services.run_service.last_request.model_settings
    )


def test_run_command_openai_compatible_only_uses_responses_when_requested(
    monkeypatch,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-x",
            "--provider",
            "openai-compatible",
            "--start",
            "Apple",
            "--target",
            "Banana",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert fake_services.run_service.last_request is not None
    assert (
        "openai_api_mode" not in fake_services.run_service.last_request.model_settings
    )


def test_run_command_rejects_openai_responses_flags_for_anthropic(monkeypatch) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "claude-test",
            "--provider",
            "anthropic",
            "--start",
            "Apple",
            "--target",
            "Banana",
            "--openai-reasoning-summary",
            "auto",
        ],
    )

    assert result.exit_code != 0
    assert "OpenAI Responses API options require" in result.stdout


def test_run_command_defaults_to_random_titles_when_omitted(monkeypatch) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )
    monkeypatch.setattr(
        "wikiarena.cli._resolve_run_titles",
        lambda **_: ("Random Start", "Random Target", True),
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-x",
            "--provider",
            "openai",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert fake_services.run_service.last_request is not None
    assert fake_services.run_service.last_request.start_page_title == "Random Start"
    assert fake_services.run_service.last_request.target_page_title == "Random Target"


def test_run_command_rejects_only_one_missing_title(monkeypatch) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-x",
            "--provider",
            "openai",
            "--start",
            "Apple",
        ],
    )

    assert result.exit_code != 0
    assert "provide both --start and --target" in result.stdout


def test_run_command_prints_terminal_error_details(monkeypatch) -> None:
    fake_services = FakeCliServices(
        run_service=FakeFailingRunService(
            run_result=_build_run_result(
                run_id="run-cli-error-1",
                race_id="race-cli-error-1",
                participant_id="participant_gpt-x",
                committed_moves=0,
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
            ),
        ),
    )
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-x",
            "--provider",
            "openai",
            "--start",
            "Apple",
            "--target",
            "Banana",
        ],
    )

    assert result.exit_code == 0
    assert "Reason: infrastructure_error" in result.stdout
    assert "Error code: infrastructure.dependency_call_failed" in result.stdout
    assert (
        "Exception: ProviderConfigurationError: Missing required api_key for provider 'openai'"
        in result.stdout
    )
    assert "hint: set openai_api_key" in result.stdout.lower()


def test_run_command_supports_offline_graph_mode(monkeypatch, tmp_path: Path) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    graph_path.write_bytes(
        b"graph",
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-x",
            "--provider",
            "openai",
            "--start",
            "Apple",
            "--target",
            "Banana",
            "--offline",
            "--navigation-graph-path",
            str(graph_path),
            "--navigation-snapshot-id",
            "snapshot-1",
        ],
    )

    assert result.exit_code == 0
    assert fake_services.run_service.last_request is not None
    assert (
        fake_services.run_service.last_request.navigation_runtime.backend
        == NavigationBackend.GRAPH
    )
    assert (
        fake_services.run_service.last_request.navigation_runtime.graph_path
        == graph_path
    )
    assert fake_services.run_service.last_request.navigation_snapshot_id == "snapshot-1"


def test_run_command_graph_path_implies_graph_backend(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    graph_path.write_bytes(
        b"graph",
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-x",
            "--provider",
            "openai",
            "--start",
            "Apple",
            "--target",
            "Banana",
            "--navigation-graph-path",
            str(graph_path),
        ],
    )

    assert result.exit_code == 0
    assert fake_services.run_service.last_request is not None
    assert (
        fake_services.run_service.last_request.navigation_runtime.backend
        == NavigationBackend.GRAPH
    )
    assert (
        fake_services.run_service.last_request.navigation_runtime.graph_path
        == graph_path
    )


def test_run_command_rejects_live_navigation_with_graph_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    graph_path.write_bytes(
        b"graph",
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-x",
            "--provider",
            "openai",
            "--start",
            "Apple",
            "--target",
            "Banana",
            "--navigation-backend",
            "live",
            "--navigation-graph-path",
            str(graph_path),
        ],
    )

    assert result.exit_code != 0
    assert "--navigation-backend graph" in result.stdout


def test_eval_run_command_loads_config_and_writes_results(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    taskset_path = tmp_path / "tasks.jsonl"
    taskset_path.write_text(
        json.dumps(
            {
                "language": "en",
                "start_page_title": "Apple",
                "target_page_title": "Banana",
            },
        )
        + "\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "benchmark.toml"
    config_path.write_text(
        "\n".join(
            [
                'benchmark_id = "benchmark_cli"',
                'taskset_id = "taskset_cli"',
                'taskset_path = "tasks.jsonl"',
                "",
                "[rules.harness]",
                'harness_id = "tool_v1"',
                'response_contract = "tool_call_only"',
                'tool_name = "navigate"',
                "",
                "[[participants]]",
                'participant_id = "model_a"',
                'display_name = "Model A"',
                "[participants.driver_config]",
                'provider = "openai"',
                'model = "gpt-x"',
            ],
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "results.jsonl"

    result = runner.invoke(
        app,
        [
            "eval",
            "run",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["benchmark_id"] == "benchmark_cli"
    assert output_path.exists()
    assert fake_services.benchmark_runner.last_benchmark_spec is not None
    assert (
        fake_services.benchmark_runner.last_benchmark_spec.taskset_id == "taskset_cli"
    )


def test_eval_run_command_allows_cli_wiki_backend_override(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    taskset_path = tmp_path / "tasks.jsonl"
    taskset_path.write_text(
        json.dumps(
            {
                "language": "en",
                "start_page_title": "Apple",
                "target_page_title": "Banana",
            },
        )
        + "\n",
        encoding="utf-8",
    )
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    graph_path.write_bytes(
        b"graph",
    )
    config_path = tmp_path / "benchmark.toml"
    config_path.write_text(
        "\n".join(
            [
                'benchmark_id = "benchmark_cli"',
                'taskset_id = "taskset_cli"',
                'taskset_path = "tasks.jsonl"',
                "",
                "[rules.harness]",
                'harness_id = "tool_v1"',
                'response_contract = "tool_call_only"',
                'tool_name = "navigate"',
                "",
                "[[participants]]",
                'participant_id = "model_a"',
                'display_name = "Model A"',
                "[participants.driver_config]",
                'provider = "openai"',
                'model = "gpt-x"',
            ],
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "results.jsonl"

    result = runner.invoke(
        app,
        [
            "eval",
            "run",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
            "--offline",
            "--navigation-graph-path",
            str(graph_path),
            "--navigation-snapshot-id",
            "snapshot-1",
        ],
    )

    assert result.exit_code == 0
    assert fake_services.benchmark_runner.last_run_options is not None
    assert (
        fake_services.benchmark_runner.last_run_options.navigation_runtime.backend
        == NavigationBackend.GRAPH
    )
    assert (
        fake_services.benchmark_runner.last_run_options.navigation_runtime.graph_path
        == graph_path
    )
    assert (
        fake_services.benchmark_runner.last_run_options.navigation_snapshot_id
        == "snapshot-1"
    )


def test_eval_run_command_graph_path_implies_graph_backend(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    taskset_path = tmp_path / "tasks.jsonl"
    taskset_path.write_text(
        json.dumps(
            {
                "language": "en",
                "start_page_title": "Apple",
                "target_page_title": "Banana",
            },
        )
        + "\n",
        encoding="utf-8",
    )
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    graph_path.write_bytes(
        b"graph",
    )
    config_path = tmp_path / "benchmark.toml"
    config_path.write_text(
        "\n".join(
            [
                'benchmark_id = "benchmark_cli"',
                'taskset_id = "taskset_cli"',
                'taskset_path = "tasks.jsonl"',
                "",
                "[rules.harness]",
                'harness_id = "tool_v1"',
                'response_contract = "tool_call_only"',
                'tool_name = "navigate"',
                "",
                "[[participants]]",
                'participant_id = "model_a"',
                'display_name = "Model A"',
                "[participants.driver_config]",
                'provider = "openai"',
                'model = "gpt-x"',
            ],
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "results.jsonl"

    result = runner.invoke(
        app,
        [
            "eval",
            "run",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
            "--navigation-graph-path",
            str(graph_path),
        ],
    )

    assert result.exit_code == 0
    assert fake_services.benchmark_runner.last_run_options is not None
    assert (
        fake_services.benchmark_runner.last_run_options.navigation_runtime.backend
        == NavigationBackend.GRAPH
    )
    assert (
        fake_services.benchmark_runner.last_run_options.navigation_runtime.graph_path
        == graph_path
    )


def test_eval_run_command_rejects_live_navigation_with_graph_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    taskset_path = tmp_path / "tasks.jsonl"
    taskset_path.write_text(
        json.dumps(
            {
                "language": "en",
                "start_page_title": "Apple",
                "target_page_title": "Banana",
            },
        )
        + "\n",
        encoding="utf-8",
    )
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    graph_path.write_bytes(
        b"graph",
    )
    config_path = tmp_path / "benchmark.toml"
    config_path.write_text(
        "\n".join(
            [
                'benchmark_id = "benchmark_cli"',
                'taskset_id = "taskset_cli"',
                'taskset_path = "tasks.jsonl"',
                "",
                "[rules.harness]",
                'harness_id = "tool_v1"',
                'response_contract = "tool_call_only"',
                'tool_name = "navigate"',
                "",
                "[[participants]]",
                'participant_id = "model_a"',
                'display_name = "Model A"',
                "[participants.driver_config]",
                'provider = "openai"',
                'model = "gpt-x"',
            ],
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "results.jsonl"

    result = runner.invoke(
        app,
        [
            "eval",
            "run",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
            "--navigation-backend",
            "live",
            "--navigation-graph-path",
            str(graph_path),
        ],
    )

    assert result.exit_code != 0
    assert "--navigation-backend graph" in result.stdout


def test_eval_run_command_defaults_to_graph_navigation_and_local_solver(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    taskset_path = tmp_path / "tasks.jsonl"
    taskset_path.write_text(
        json.dumps(
            {
                "language": "en",
                "start_page_title": "Apple",
                "target_page_title": "Banana",
            },
        )
        + "\n",
        encoding="utf-8",
    )
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    graph_path.write_bytes(
        b"graph",
    )
    monkeypatch.setattr(
        "wikiarena.cli.resolve_graph_file_path",
        lambda graph_path_arg: graph_path,
    )
    monkeypatch.setattr(
        "wikiarena.cli.resolve_solver_graph_file_path",
        lambda graph_path_arg: graph_path,
    )

    config_path = tmp_path / "benchmark.toml"
    config_path.write_text(
        "\n".join(
            [
                'benchmark_id = "benchmark_cli"',
                'taskset_id = "taskset_cli"',
                'taskset_path = "tasks.jsonl"',
                "",
                "[rules.harness]",
                'harness_id = "tool_v1"',
                'response_contract = "tool_call_only"',
                'tool_name = "navigate"',
                "",
                "[[participants]]",
                'participant_id = "model_a"',
                'display_name = "Model A"',
                "[participants.driver_config]",
                'provider = "openai"',
                'model = "gpt-x"',
            ],
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "results.jsonl"

    result = runner.invoke(
        app,
        [
            "eval",
            "run",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    assert fake_services.benchmark_runner.last_run_options is not None
    assert (
        fake_services.benchmark_runner.last_run_options.navigation_runtime.backend
        == NavigationBackend.GRAPH
    )
    assert (
        fake_services.benchmark_runner.last_run_options.solver_runtime.backend
        == SolverBackend.LOCAL
    )


def test_eval_run_command_preserves_configured_live_navigation_and_no_solver(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    taskset_path = tmp_path / "tasks.jsonl"
    taskset_path.write_text(
        json.dumps(
            {
                "language": "en",
                "start_page_title": "Apple",
                "target_page_title": "Banana",
            },
        )
        + "\n",
        encoding="utf-8",
    )
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    graph_path.write_bytes(
        b"graph",
    )
    monkeypatch.setattr(
        "wikiarena.cli.resolve_graph_file_path",
        lambda graph_path_arg: graph_path,
    )
    monkeypatch.setattr(
        "wikiarena.cli.resolve_solver_graph_file_path",
        lambda graph_path_arg: graph_path,
    )

    config_path = tmp_path / "benchmark.toml"
    config_path.write_text(
        "\n".join(
            [
                'benchmark_id = "benchmark_cli"',
                'taskset_id = "taskset_cli"',
                'taskset_path = "tasks.jsonl"',
                "",
                "[run_options.navigation_runtime]",
                'backend = "live"',
                "",
                "[run_options.solver_runtime]",
                'backend = "none"',
                "",
                "[rules.harness]",
                'harness_id = "tool_v1"',
                'response_contract = "tool_call_only"',
                'tool_name = "navigate"',
                "",
                "[[participants]]",
                'participant_id = "model_a"',
                'display_name = "Model A"',
                "[participants.driver_config]",
                'provider = "openai"',
                'model = "gpt-x"',
            ],
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "results.jsonl"

    result = runner.invoke(
        app,
        [
            "eval",
            "run",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    assert fake_services.benchmark_runner.last_run_options is not None
    assert (
        fake_services.benchmark_runner.last_run_options.navigation_runtime.backend
        == NavigationBackend.LIVE
    )
    assert (
        fake_services.benchmark_runner.last_run_options.solver_runtime.backend
        == SolverBackend.NONE
    )


def test_run_command_supports_live_navigation_with_local_graph_solver(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    graph_path.write_bytes(
        b"graph",
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-x",
            "--provider",
            "openai",
            "--start",
            "Apple",
            "--target",
            "Banana",
            "--solver-backend",
            "local",
            "--solver-graph-path",
            str(graph_path),
        ],
    )

    assert result.exit_code == 0
    assert fake_services.run_service.last_request is not None
    assert (
        fake_services.run_service.last_request.navigation_runtime.backend
        == NavigationBackend.LIVE
    )
    assert (
        fake_services.run_service.last_request.solver_runtime.backend
        == SolverBackend.LOCAL
    )
    assert (
        fake_services.run_service.last_request.solver_runtime.graph_path == graph_path
    )


def test_run_command_defaults_to_graph_navigation_when_graph_is_installed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    graph_path.write_bytes(
        b"graph",
    )
    monkeypatch.setattr(
        "wikiarena.cli.resolve_graph_file_path",
        lambda graph_path_arg: graph_path,
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-x",
            "--provider",
            "openai",
            "--start",
            "Apple",
            "--target",
            "Banana",
        ],
    )

    assert result.exit_code == 0
    assert fake_services.run_service.last_request is not None
    assert (
        fake_services.run_service.last_request.navigation_runtime.backend
        == NavigationBackend.GRAPH
    )


def test_run_command_preserves_explicit_live_navigation_when_graph_is_installed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    graph_path.write_bytes(
        b"graph",
    )
    monkeypatch.setattr(
        "wikiarena.cli.resolve_graph_file_path",
        lambda graph_path_arg: graph_path,
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-x",
            "--provider",
            "openai",
            "--start",
            "Apple",
            "--target",
            "Banana",
            "--navigation-backend",
            "live",
        ],
    )

    assert result.exit_code == 0
    assert fake_services.run_service.last_request is not None
    assert (
        fake_services.run_service.last_request.navigation_runtime.backend
        == NavigationBackend.LIVE
    )


def test_run_command_defaults_to_local_solver_when_graph_is_installed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    graph_path.write_bytes(
        b"graph",
    )
    monkeypatch.setattr(
        "wikiarena.cli.resolve_solver_graph_file_path",
        lambda graph_path_arg: graph_path,
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-x",
            "--provider",
            "openai",
            "--start",
            "Apple",
            "--target",
            "Banana",
        ],
    )

    assert result.exit_code == 0
    assert fake_services.run_service.last_request is not None
    assert (
        fake_services.run_service.last_request.solver_runtime.backend
        == SolverBackend.LOCAL
    )


def test_run_command_defaults_to_no_solver_when_graph_is_not_installed(
    monkeypatch,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    def missing_solver_graph(graph_path_arg):
        raise FileNotFoundError("no graph")

    monkeypatch.setattr(
        "wikiarena.cli.resolve_solver_graph_file_path",
        missing_solver_graph,
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-x",
            "--provider",
            "openai",
            "--start",
            "Apple",
            "--target",
            "Banana",
        ],
    )

    assert result.exit_code == 0
    assert fake_services.run_service.last_request is not None
    assert (
        fake_services.run_service.last_request.solver_runtime.backend
        == SolverBackend.NONE
    )


def test_run_command_can_disable_auto_solver_backend(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    graph_path.write_bytes(
        b"graph",
    )
    monkeypatch.setattr(
        "wikiarena.cli.resolve_solver_graph_file_path",
        lambda graph_path_arg: graph_path,
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-x",
            "--provider",
            "openai",
            "--start",
            "Apple",
            "--target",
            "Banana",
            "--solver-backend",
            "none",
        ],
    )

    assert result.exit_code == 0
    assert fake_services.run_service.last_request is not None
    assert (
        fake_services.run_service.last_request.solver_runtime.backend
        == SolverBackend.NONE
    )


def test_run_command_rejects_remote_solver_backend(
    monkeypatch,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-x",
            "--provider",
            "openai",
            "--start",
            "Apple",
            "--target",
            "Banana",
            "--solver-backend",
            "remote",
        ],
    )

    assert result.exit_code != 0
    assert "not yet supported in the CLI" in result.stdout


def test_graph_install_command_installs_release(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured_kwargs: dict[str, object] = {}
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    metadata_path = tmp_path / "wikiarena_graph_enwiki_20260301.metadata.json"

    def fake_install_graph_release(**kwargs) -> GraphInstallResult:
        captured_kwargs.update(kwargs)
        return GraphInstallResult(
            release_tag="graph-enwiki-20260301",
            graph_path=graph_path,
            metadata_path=metadata_path,
            snapshot_id="enwiki-20260301",
            node_count=6,
            edge_count=5,
            already_installed=False,
        )

    monkeypatch.setattr(
        "wikiarena.cli.install_graph_release",
        fake_install_graph_release,
    )

    result = runner.invoke(
        app,
        [
            "graph",
            "install",
            "--tag",
            "graph-enwiki-20260301",
            "--install-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert captured_kwargs == {
        "repo": "wikiarena/wikiarena",
        "tag": "graph-enwiki-20260301",
        "install_dir": tmp_path,
        "force": False,
    }
    assert "Installed graph: " in result.stdout
    assert "Snapshot id: enwiki-20260301" in result.stdout


def test_graph_info_command_reports_active_graph(
    monkeypatch,
    tmp_path: Path,
) -> None:
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    metadata_path = tmp_path / "wikiarena_graph_enwiki_20260301.metadata.json"

    def fake_load_graph_info(**kwargs) -> GraphInfoResult:
        assert kwargs == {
            "graph_path": None,
            "verify": False,
        }
        return GraphInfoResult(
            graph_path=graph_path,
            metadata_path=metadata_path,
            metadata_present=True,
            selected_via="installed_latest",
            snapshot_id="enwiki-20260301",
            wiki="enwiki",
            dump_date="20260301",
            release_tag="graph-enwiki-20260301",
            node_count=6,
            edge_count=5,
            file_size_bytes=123,
            graph_sha256=None,
            metadata_generated_at_utc="2026-03-24T00:00:00+00:00",
            metadata_git_sha="abc123",
            verified=False,
        )

    monkeypatch.setattr(
        "wikiarena.cli.load_graph_info",
        fake_load_graph_info,
    )

    result = runner.invoke(
        app,
        [
            "graph",
            "info",
        ],
    )

    assert result.exit_code == 0
    assert "Active graph: " in result.stdout
    assert "Selected via: installed_latest" in result.stdout
    assert "Snapshot id: enwiki-20260301" in result.stdout
    assert "Nodes: 6" in result.stdout


def test_eval_summarize_command_outputs_json_summary(
    tmp_path: Path,
) -> None:
    results_path = tmp_path / "results.jsonl"
    results_path.write_text(
        "\n".join(
            [
                json.dumps(
                    _build_run_result(
                        run_id="run-a",
                        race_id="race-1",
                        participant_id="model_a",
                        committed_moves=3,
                    ).model_dump(mode="json"),
                ),
                json.dumps(
                    _build_run_result(
                        run_id="run-b",
                        race_id="race-1",
                        participant_id="model_b",
                        committed_moves=5,
                    ).model_dump(mode="json"),
                ),
            ],
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "eval",
            "summarize",
            "--input",
            str(results_path),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["total_runs"] == 2
    assert payload["participants"][0]["participant_id"] == "model_a"


def test_run_command_rejects_conflicting_thinking_flags(monkeypatch) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--model",
            "gpt-x",
            "--provider",
            "openai",
            "--start",
            "Apple",
            "--target",
            "Banana",
            "--thinking-effort",
            "high",
            "--thinking-budget-tokens",
            "2048",
        ],
    )

    assert result.exit_code != 0
    assert "thinking-effort" in result.stdout
    assert "thinking-budget-tokens" in result.stdout


def test_eval_run_defaults_to_resume_for_existing_output(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    taskset_path = tmp_path / "tasks.jsonl"
    taskset_path.write_text(
        json.dumps(
            {
                "language": "en",
                "start_page_title": "Apple",
                "target_page_title": "Banana",
            },
        )
        + "\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "eval.toml"
    config_path.write_text(
        "\n".join(
            [
                'benchmark_id = "benchmark_cli"',
                'taskset_id = "taskset_cli"',
                'taskset_path = "tasks.jsonl"',
                "",
                "[rules.harness]",
                'harness_id = "tool_v1"',
                'response_contract = "tool_call_only"',
                'tool_name = "navigate"',
                "",
                "[[participants]]",
                'participant_id = "model_a"',
                'display_name = "Model A"',
                "[participants.driver_config]",
                'provider = "openai"',
                'model = "gpt-x"',
            ],
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "results.jsonl"
    matching_ruleset_hash = build_ruleset_hash(
        protocol_version="1.0.0-test",
        navigation_rules=NavigationRules(),
        harness_config=HarnessConfig(
            harness_id="tool_v1",
            response_contract=ResponseContract.TOOL_CALL_ONLY,
            tool_name="navigate",
        ),
        scoring_rules=ScoringRules(),
    )
    output_path.write_text(
        json.dumps(
            _build_run_result(
                run_id="existing-run",
                race_id="existing-race",
                participant_id="model_a",
                committed_moves=4,
                ruleset_hash=matching_ruleset_hash,
                taskset_hash=_single_apple_banana_taskset_hash(),
            ).model_dump(mode="json"),
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "eval",
            "run",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    lines = output_path.read_text(
        encoding="utf-8",
    ).splitlines()
    assert json.loads(lines[0])["run_id"] == "existing-run"
    assert len(lines) == 2


def test_eval_run_overwrite_replaces_existing_output(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    taskset_path = tmp_path / "tasks.jsonl"
    taskset_path.write_text(
        json.dumps(
            {
                "language": "en",
                "start_page_title": "Apple",
                "target_page_title": "Banana",
            },
        )
        + "\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "eval.toml"
    config_path.write_text(
        "\n".join(
            [
                'benchmark_id = "benchmark_cli"',
                'taskset_id = "taskset_cli"',
                'taskset_path = "tasks.jsonl"',
                "",
                "[rules.harness]",
                'harness_id = "tool_v1"',
                'response_contract = "tool_call_only"',
                'tool_name = "navigate"',
                "",
                "[[participants]]",
                'participant_id = "model_a"',
                'display_name = "Model A"',
                "[participants.driver_config]",
                'provider = "openai"',
                'model = "gpt-x"',
            ],
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "results.jsonl"
    matching_ruleset_hash = build_ruleset_hash(
        protocol_version="1.0.0-test",
        navigation_rules=NavigationRules(),
        harness_config=HarnessConfig(
            harness_id="tool_v1",
            response_contract=ResponseContract.TOOL_CALL_ONLY,
            tool_name="navigate",
        ),
        scoring_rules=ScoringRules(),
    )
    output_path.write_text(
        json.dumps(
            _build_run_result(
                run_id="existing-run",
                race_id="existing-race",
                participant_id="model_a",
                committed_moves=4,
                ruleset_hash=matching_ruleset_hash,
                taskset_hash=_single_apple_banana_taskset_hash(),
            ).model_dump(mode="json"),
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "eval",
            "run",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
            "--overwrite",
        ],
    )

    assert result.exit_code == 0
    lines = output_path.read_text(
        encoding="utf-8",
    ).splitlines()
    assert lines == [
        json.dumps(
            _build_run_result(
                run_id="run-benchmark-1",
                race_id="race-benchmark-1",
                participant_id="model_a",
                committed_moves=4,
                taskset_hash=_single_apple_banana_taskset_hash(),
            ).model_dump(mode="json"),
        ),
    ]


def test_eval_run_rejects_append_option(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    taskset_path = tmp_path / "tasks.jsonl"
    taskset_path.write_text(
        json.dumps(
            {
                "language": "en",
                "start_page_title": "Apple",
                "target_page_title": "Banana",
            },
        )
        + "\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "eval.toml"
    config_path.write_text(
        "\n".join(
            [
                'benchmark_id = "benchmark_cli"',
                'taskset_id = "taskset_cli"',
                'taskset_path = "tasks.jsonl"',
                "",
                "[rules.harness]",
                'harness_id = "tool_v1"',
                'response_contract = "tool_call_only"',
                'tool_name = "navigate"',
                "",
                "[[participants]]",
                'participant_id = "model_a"',
                'display_name = "Model A"',
                "[participants.driver_config]",
                'provider = "openai"',
                'model = "gpt-x"',
            ],
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "results.jsonl"

    result = runner.invoke(
        app,
        [
            "eval",
            "run",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
            "--append",
        ],
    )

    assert result.exit_code != 0
    assert "No such option" in result.stdout


def test_eval_run_resume_passes_existing_results_to_runner(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    taskset_path = tmp_path / "tasks.jsonl"
    taskset_path.write_text(
        json.dumps(
            {
                "language": "en",
                "start_page_title": "Apple",
                "target_page_title": "Banana",
            },
        )
        + "\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "eval.toml"
    config_path.write_text(
        "\n".join(
            [
                'benchmark_id = "benchmark_cli"',
                'taskset_id = "taskset_cli"',
                'taskset_path = "tasks.jsonl"',
                "",
                "[rules.harness]",
                'harness_id = "tool_v1"',
                'response_contract = "tool_call_only"',
                'tool_name = "navigate"',
                "",
                "[[participants]]",
                'participant_id = "model_a"',
                'display_name = "Model A"',
                "[participants.driver_config]",
                'provider = "openai"',
                'model = "gpt-x"',
            ],
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "results.jsonl"
    output_path.write_text(
        json.dumps(
            _build_run_result(
                run_id="existing-run",
                race_id="existing-race",
                participant_id="model_a",
                committed_moves=4,
                ruleset_hash=build_ruleset_hash(
                    protocol_version="1.0.0-test",
                    navigation_rules=NavigationRules(),
                    harness_config=HarnessConfig(
                        harness_id="tool_v1",
                        response_contract=ResponseContract.TOOL_CALL_ONLY,
                        tool_name="navigate",
                    ),
                    scoring_rules=ScoringRules(),
                ),
                taskset_hash=_single_apple_banana_taskset_hash(),
            ).model_dump(mode="json"),
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "eval",
            "run",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
            "--resume",
        ],
    )

    assert result.exit_code == 0
    assert fake_services.benchmark_runner.last_resume is not None
    assert len(fake_services.benchmark_runner.last_resume.existing_run_results) == 1


def test_eval_run_persists_frontend_race_artifacts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    taskset_path = tmp_path / "tasks.jsonl"
    taskset_path.write_text(
        json.dumps(
            {
                "language": "en",
                "start_page_title": "Apple",
                "target_page_title": "Banana",
            },
        )
        + "\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "eval.toml"
    config_path.write_text(
        "\n".join(
            [
                'benchmark_id = "benchmark_cli"',
                'taskset_id = "taskset_cli"',
                'taskset_path = "tasks.jsonl"',
                "",
                "[rules.harness]",
                'harness_id = "tool_v1"',
                'response_contract = "tool_call_only"',
                'tool_name = "navigate"',
                "",
                "[[participants]]",
                'participant_id = "model_a"',
                'display_name = "Model A"',
                "[participants.driver_config]",
                'provider = "openai"',
                'model = "gpt-x"',
            ],
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "results.jsonl"
    artifact_dir = tmp_path / "artifacts"

    result = runner.invoke(
        app,
        [
            "eval",
            "run",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
            "--artifact-dir",
            str(artifact_dir),
        ],
    )

    assert result.exit_code == 0
    race_dir = artifact_dir / "races" / "race-benchmark-1"
    assert (race_dir / "race.json").exists()
    assert (race_dir / "events.jsonl").exists()
    assert (race_dir / "runs" / "run-benchmark-1.events.jsonl").exists()
    assert (race_dir / "runs" / "run-benchmark-1.result.json").exists()
    metadata = json.loads((race_dir / "race.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "completed"
    assert metadata["participants"][0]["run_id"] == "run-benchmark-1"


def test_eval_run_race_limit_preserves_full_taskset_hash(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    tasks = [
        {
            "language": "en",
            "start_page_title": "Apple",
            "target_page_title": "Banana",
        },
        {
            "language": "en",
            "start_page_title": "Carrot",
            "target_page_title": "Daikon",
        },
    ]
    taskset_path = tmp_path / "tasks.jsonl"
    taskset_path.write_text(
        "".join(
            json.dumps(
                task,
            )
            + "\n"
            for task in tasks
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "eval.toml"
    config_path.write_text(
        "\n".join(
            [
                'benchmark_id = "benchmark_cli"',
                'taskset_id = "taskset_cli"',
                'taskset_path = "tasks.jsonl"',
                "",
                "[rules.harness]",
                'harness_id = "tool_v1"',
                'response_contract = "tool_call_only"',
                'tool_name = "navigate"',
                "",
                "[[participants]]",
                'participant_id = "model_a"',
                'display_name = "Model A"',
                "[participants.driver_config]",
                'provider = "openai"',
                'model = "gpt-x"',
            ],
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "results.jsonl"

    result = runner.invoke(
        app,
        [
            "eval",
            "run",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
            "--race-limit",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert fake_services.benchmark_runner.last_benchmark_spec is not None
    assert len(fake_services.benchmark_runner.last_benchmark_spec.tasks) == 1
    assert (
        fake_services.benchmark_runner.last_taskset_hash_override
        == build_taskset_hash(
            [TaskSpec.model_validate(task) for task in tasks],
        )
    )


def test_eval_run_rejects_different_ruleset_hash_by_default(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_services = FakeCliServices()
    monkeypatch.setattr(
        "wikiarena.cli.get_cli_services",
        lambda: fake_services,
    )

    taskset_path = tmp_path / "tasks.jsonl"
    taskset_path.write_text(
        json.dumps(
            {
                "language": "en",
                "start_page_title": "Apple",
                "target_page_title": "Banana",
            },
        )
        + "\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "eval.toml"
    config_path.write_text(
        "\n".join(
            [
                'benchmark_id = "benchmark_cli"',
                'taskset_id = "taskset_cli"',
                'taskset_path = "tasks.jsonl"',
                "",
                "[rules.harness]",
                'harness_id = "different_tool_v1"',
                'response_contract = "tool_call_only"',
                'tool_name = "navigate"',
                "",
                "[[participants]]",
                'participant_id = "model_a"',
                'display_name = "Model A"',
                "[participants.driver_config]",
                'provider = "openai"',
                'model = "gpt-x"',
            ],
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "results.jsonl"
    output_path.write_text(
        json.dumps(
            _build_run_result(
                run_id="existing-run",
                race_id="existing-race",
                participant_id="model_a",
                committed_moves=4,
                ruleset_hash="ruleset-1",
            ).model_dump(mode="json"),
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "eval",
            "run",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code != 0
    assert "different ruleset_hash" in result.stdout
