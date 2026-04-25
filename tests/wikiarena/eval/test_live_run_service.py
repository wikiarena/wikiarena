from __future__ import annotations

import re
from datetime import datetime

import pytest
from pydantic import ValidationError

from wikiarena.core import (
    NavigationResolution,
    PageSnapshot,
    ParticipantDecision,
    RunExecutor,
)
from wikiarena.eval import LiveRunRequest, LiveRunService
from wikiarena.protocol import (
    HarnessConfig,
    NavigationBackend,
    ResponseContract,
    SolverBackend,
    SolverShortestPath,
    TaskExecutionAnnotationStatus,
    TerminalOutcome,
    TerminationReason,
)
from wikiarena.protocol.enums import PathSource
from wikiarena.solver.binary.io import SolverBinaryData, write_solver_binary
from wikiarena.solver_runtime import SolverRuntimeConfig
from wikiarena.wiki_runtime import NavigationRuntimeConfig


class StubParticipant:
    def __init__(
        self,
    ):
        self.last_task = None

    async def choose_link(
        self,
        task,
        current_page,
        harness_config,
    ) -> ParticipantDecision:
        self.last_task = task
        return ParticipantDecision(
            selected_link_text="Banana",
            raw_response="navigate Banana",
            tool_call_name="navigate",
            tool_call_id="call_1",
        )


class StubWikiNavigator:
    async def get_page_snapshot(
        self,
        language,
        page_title,
        link_policy,
    ) -> PageSnapshot:
        if page_title == "Apple":
            return PageSnapshot(
                title="Apple",
                language="en",
                links=["Banana"],
            )
        return PageSnapshot(
            title="Banana",
            language="en",
            links=[],
        )

    async def resolve_navigation(
        self,
        language,
        from_page_title,
        selected_link_text,
    ) -> NavigationResolution:
        return NavigationResolution(
            requested_to_page_title=selected_link_text,
            resolved_to_page_title=selected_link_text,
            was_redirect=False,
        )


def _write_toy_graph(graph_path) -> None:
    write_solver_binary(
        file_path=graph_path,
        data=SolverBinaryData(
            canonical_titles=(
                "Apple",
                "Banana",
                "Cherry",
            ),
            out_offsets=(0, 1, 2, 2),
            out_neighbors=(1, 2),
            in_offsets=(0, 0, 1, 2),
            in_neighbors=(0, 1),
        ),
    )


def _write_graph_without_banana(graph_path) -> None:
    write_solver_binary(
        file_path=graph_path,
        data=SolverBinaryData(
            canonical_titles=(
                "Apple",
                "Cherry",
            ),
            out_offsets=(0, 1, 1),
            out_neighbors=(1,),
            in_offsets=(0, 0, 1),
            in_neighbors=(0,),
        ),
    )


@pytest.mark.asyncio
async def test_live_run_service_executes_with_injected_factories() -> None:
    captured = {}
    participant = StubParticipant()

    def participant_factory(spec):
        captured["participant_spec"] = spec
        return participant

    def wiki_factory(run_plan):
        captured["language"] = run_plan.task_spec.language
        captured["navigation_backend"] = run_plan.navigation_runtime.backend
        return StubWikiNavigator()

    service = LiveRunService(
        participant_factory=participant_factory,
        wiki_navigator_factory=wiki_factory,
        run_executor=RunExecutor(
            engine_commit="abc123",
        ),
    )

    artifact = await service.execute_live_run(
        LiveRunRequest(
            model_id="openai/gpt-4o-mini-2024-07-18",
            start_page_title="Apple",
            target_page_title="Banana",
            benchmark_id="bench_1",
            race_id="race_1",
            run_id="run_1",
            taskset_hash="taskset_hash",
            harness_config=HarnessConfig(
                harness_id="tool_strict_v1",
                response_contract=ResponseContract.TOOL_CALL_ONLY,
            ),
        ),
    )

    assert captured["language"] == "en"
    assert captured["navigation_backend"] == NavigationBackend.LIVE
    assert captured["participant_spec"].driver_config.provider == "openai"
    assert (
        captured["participant_spec"].driver_config.model
        == "openai/gpt-4o-mini-2024-07-18"
    )

    run_result = artifact.run_result
    assert run_result.run_id == "run_1"
    assert run_result.race_id == "race_1"
    assert run_result.task_id == "en__apple__banana"
    assert run_result.terminal_outcome == TerminalOutcome.SUCCESS
    assert run_result.termination_reason == TerminationReason.TASK_COMPLETED
    assert run_result.total_committed_moves == 1
    assert run_result.participant_hash is not None
    assert run_result.ruleset_hash is not None
    assert run_result.taskset_hash == "taskset_hash"


@pytest.mark.asyncio
async def test_live_run_service_generates_ids_when_not_provided() -> None:
    participant = StubParticipant()

    service = LiveRunService(
        participant_factory=lambda spec: participant,
        wiki_navigator_factory=lambda run_plan: StubWikiNavigator(),
        run_executor=RunExecutor(),
    )

    artifact = await service.execute_live_run(
        LiveRunRequest(
            model_id="anthropic/claude-3-5-sonnet-20241022",
            start_page_title="Apple",
            target_page_title="Banana",
            benchmark_id="my benchmark",
        ),
    )

    run_result = artifact.run_result
    assert run_result.race_id.startswith("race_my_benchmark_en_apple_banana_")
    assert run_result.run_id.startswith("run_race_my_benchmark_en_apple_banana_")
    assert re.match(
        r"^run_.+_[0-9a-f]{6}$",
        run_result.run_id,
    )


class StubSolverShortestPathOracle:
    def __init__(
        self,
    ):
        self.called = False

    async def get_solver_shortest_path(
        self,
        task,
    ):
        self.called = True
        return SolverShortestPath(
            page_titles=["Apple", "Banana"],
            computed_at=datetime(2026, 1, 1, 0, 0, 0),
            solver_snapshot_id="snapshot-2026-01-01",
            source=PathSource.REMOTE_SOLVER,
        )


@pytest.mark.asyncio
async def test_live_run_service_attaches_solver_shortest_path_when_enabled() -> None:
    participant = StubParticipant()
    oracle = StubSolverShortestPathOracle()

    service = LiveRunService(
        participant_factory=lambda spec: participant,
        wiki_navigator_factory=lambda run_plan: StubWikiNavigator(),
        solver_shortest_path_oracle=oracle,
        run_executor=RunExecutor(),
    )

    artifact = await service.execute_live_run(
        LiveRunRequest(
            model_id="openai/gpt-4o-mini-2024-07-18",
            start_page_title="Apple",
            target_page_title="Banana",
            solver_runtime=SolverRuntimeConfig(
                backend=SolverBackend.REMOTE,
            ),
        ),
    )

    assert oracle.called is True
    assert participant.last_task is not None
    assert participant.last_task.solver_shortest_path is not None
    assert participant.last_task.solver_shortest_path.page_titles == [
        "Apple",
        "Banana",
    ]
    assert participant.last_task.shortest_path_length == 1
    assert artifact.run_result.solver_backend == SolverBackend.REMOTE
    assert artifact.run_result.solver_snapshot_id == "snapshot-2026-01-01"


@pytest.mark.asyncio
async def test_live_run_service_uses_solver_shortest_path_for_task_execution_annotation() -> (
    None
):
    participant = StubParticipant()

    service = LiveRunService(
        participant_factory=lambda spec: participant,
        wiki_navigator_factory=lambda run_plan: StubWikiNavigator(),
        solver_shortest_path_oracle=StubSolverShortestPathOracle(),
        run_executor=RunExecutor(),
    )

    artifact = await service.execute_live_run(
        LiveRunRequest(
            model_id="openai/gpt-4o-mini-2024-07-18",
            start_page_title="Apple",
            target_page_title="Banana",
            solver_runtime=SolverRuntimeConfig(
                backend=SolverBackend.REMOTE,
            ),
        ),
    )

    assert artifact.run_result.task_execution_annotation is not None
    assert artifact.run_result.task_execution_annotation.status == (
        TaskExecutionAnnotationStatus.OK
    )
    assert artifact.run_result.task_execution_annotation.shortest_path_length == 1


@pytest.mark.asyncio
async def test_live_run_service_infers_snapshot_id_from_dated_graph_file(
    tmp_path,
) -> None:
    participant = StubParticipant()
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    graph_path.write_bytes(b"graph")
    captured = {}

    def wiki_factory(run_plan):
        captured["navigation_runtime"] = run_plan.navigation_runtime
        return StubWikiNavigator()

    service = LiveRunService(
        participant_factory=lambda spec: participant,
        wiki_navigator_factory=wiki_factory,
        run_executor=RunExecutor(),
    )

    artifact = await service.execute_live_run(
        LiveRunRequest(
            model_id="openai/gpt-4o-mini-2024-07-18",
            start_page_title="Apple",
            target_page_title="Banana",
            navigation_runtime=NavigationRuntimeConfig(
                backend=NavigationBackend.GRAPH,
                graph_path=graph_path,
            ),
        ),
    )

    assert captured["navigation_runtime"].graph_path == graph_path.resolve()
    assert artifact.run_result.navigation_snapshot_id == "enwiki-20260301"


@pytest.mark.asyncio
async def test_live_run_service_supports_live_navigation_with_local_graph_solver(
    tmp_path,
) -> None:
    participant = StubParticipant()
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    _write_toy_graph(
        graph_path,
    )

    service = LiveRunService(
        participant_factory=lambda spec: participant,
        wiki_navigator_factory=lambda run_plan: StubWikiNavigator(),
        run_executor=RunExecutor(),
    )

    artifact = await service.execute_live_run(
        LiveRunRequest(
            model_id="openai/gpt-4o-mini-2024-07-18",
            start_page_title="Apple",
            target_page_title="Banana",
            navigation_runtime=NavigationRuntimeConfig(
                backend=NavigationBackend.LIVE,
            ),
            solver_runtime=SolverRuntimeConfig(
                backend=SolverBackend.LOCAL,
                graph_path=graph_path,
            ),
        ),
    )

    assert participant.last_task is not None
    assert participant.last_task.solver_shortest_path is not None
    assert participant.last_task.solver_shortest_path.page_titles == [
        "Apple",
        "Banana",
    ]
    assert participant.last_task.shortest_path_length == 1
    assert artifact.run_result.navigation_backend == NavigationBackend.LIVE
    assert artifact.run_result.solver_backend == SolverBackend.LOCAL
    assert artifact.run_result.navigation_snapshot_id is None
    assert artifact.run_result.solver_snapshot_id == "enwiki-20260301"
    assert artifact.run_result.task_execution_annotation is not None
    assert artifact.run_result.task_execution_annotation.status == (
        TaskExecutionAnnotationStatus.OK
    )
    assert artifact.run_result.task_execution_annotation.shortest_path_length == 1
    assert artifact.run_result.step_attempts[0].solver_metrics is not None
    assert artifact.run_result.step_attempts[0].solver_metrics.distance_before == 1
    assert artifact.run_result.step_attempts[0].solver_metrics.distance_after == 0


@pytest.mark.asyncio
async def test_live_run_service_prefers_local_solver_over_injected_reference_oracle(
    tmp_path,
) -> None:
    participant = StubParticipant()
    oracle = StubSolverShortestPathOracle()
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    _write_toy_graph(
        graph_path,
    )

    service = LiveRunService(
        participant_factory=lambda spec: participant,
        wiki_navigator_factory=lambda run_plan: StubWikiNavigator(),
        solver_shortest_path_oracle=oracle,
        run_executor=RunExecutor(),
    )

    artifact = await service.execute_live_run(
        LiveRunRequest(
            model_id="openai/gpt-4o-mini-2024-07-18",
            start_page_title="Apple",
            target_page_title="Banana",
            navigation_runtime=NavigationRuntimeConfig(
                backend=NavigationBackend.LIVE,
            ),
            solver_runtime=SolverRuntimeConfig(
                backend=SolverBackend.LOCAL,
                graph_path=graph_path,
            ),
        ),
    )

    assert participant.last_task is not None
    assert oracle.called is False
    assert participant.last_task.solver_shortest_path is not None
    assert participant.last_task.solver_shortest_path.hop_count == 1
    assert participant.last_task.shortest_path_length == 1
    assert artifact.run_result.task_execution_annotation is not None
    assert artifact.run_result.task_execution_annotation.shortest_path_length == 1
    assert artifact.run_result.step_attempts[0].solver_metrics is not None
    assert artifact.run_result.step_attempts[0].solver_metrics.distance_before == 1
    assert artifact.run_result.step_attempts[0].solver_metrics.distance_after == 0


@pytest.mark.asyncio
async def test_live_run_service_defaults_solver_graph_to_navigation_graph(
    tmp_path,
) -> None:
    participant = StubParticipant()
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    _write_toy_graph(
        graph_path,
    )

    service = LiveRunService(
        participant_factory=lambda spec: participant,
        wiki_navigator_factory=lambda run_plan: StubWikiNavigator(),
        run_executor=RunExecutor(),
    )

    artifact = await service.execute_live_run(
        LiveRunRequest(
            model_id="openai/gpt-4o-mini-2024-07-18",
            start_page_title="Apple",
            target_page_title="Banana",
            navigation_runtime=NavigationRuntimeConfig(
                backend=NavigationBackend.GRAPH,
                graph_path=graph_path,
            ),
            solver_runtime=SolverRuntimeConfig(
                backend=SolverBackend.LOCAL,
            ),
        ),
    )

    assert artifact.run_result.navigation_snapshot_id == "enwiki-20260301"
    assert artifact.run_result.solver_snapshot_id == "enwiki-20260301"


@pytest.mark.asyncio
async def test_live_run_service_marks_missing_solver_target_in_task_execution_annotation(
    tmp_path,
) -> None:
    participant = StubParticipant()
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    _write_graph_without_banana(
        graph_path,
    )

    service = LiveRunService(
        participant_factory=lambda spec: participant,
        wiki_navigator_factory=lambda run_plan: StubWikiNavigator(),
        run_executor=RunExecutor(),
    )

    artifact = await service.execute_live_run(
        LiveRunRequest(
            model_id="openai/gpt-4o-mini-2024-07-18",
            start_page_title="Apple",
            target_page_title="Banana",
            navigation_runtime=NavigationRuntimeConfig(
                backend=NavigationBackend.LIVE,
            ),
            solver_runtime=SolverRuntimeConfig(
                backend=SolverBackend.LOCAL,
                graph_path=graph_path,
            ),
        ),
    )

    assert artifact.run_result.terminal_outcome == TerminalOutcome.SUCCESS
    assert participant.last_task is not None
    assert participant.last_task.solver_shortest_path is None
    assert participant.last_task.shortest_path_length is None
    assert artifact.run_result.task_execution_annotation is not None
    assert artifact.run_result.task_execution_annotation.status == (
        TaskExecutionAnnotationStatus.TARGET_MISSING_IN_SOLVER
    )
    assert artifact.run_result.task_execution_annotation.shortest_path_length is None
    assert artifact.run_result.step_attempts[0].solver_metrics is None


def test_live_run_request_rejects_legacy_runtime_aliases() -> None:
    with pytest.raises(
        ValidationError,
        match="wiki_snapshot_id",
    ):
        LiveRunRequest.model_validate(
            {
                "model_id": "openai/gpt-4o-mini-2024-07-18",
                "start_page_title": "Apple",
                "target_page_title": "Banana",
                "wiki_snapshot_id": "enwiki-20260301",
            },
        )
