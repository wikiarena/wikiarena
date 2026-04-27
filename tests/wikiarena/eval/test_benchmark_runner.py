from __future__ import annotations

import asyncio
import inspect
import json
from collections import defaultdict
from datetime import datetime

import pytest
from pydantic import ValidationError

from wikiarena.core import RunExecutionArtifact
from wikiarena.eval import (
    BenchmarkConcurrencyConfig,
    BenchmarkResumeConfig,
    BenchmarkRunner,
    BenchmarkRunOptions,
    RunPlan,
    RunResultStore,
    build_race_id,
    build_run_id,
    plan_benchmark_identity,
)
from wikiarena.protocol import (
    BenchmarkRules,
    BenchmarkSpec,
    DriverConfig,
    EventEnvelope,
    HarnessConfig,
    NavigationBackend,
    ParticipantKind,
    ParticipantSpec,
    RunEventType,
    RunResult,
    RunSpec,
    SolverBackend,
    TaskExecutionAnnotation,
    TaskExecutionAnnotationStatus,
    TaskSpec,
    TerminalOutcome,
    TerminationReason,
)
from wikiarena.solver_runtime import SolverRuntimeConfig
from wikiarena.wiki_runtime import NavigationRuntimeConfig


class FakeLiveRunService:
    def __init__(
        self,
        *,
        latency_seconds: float = 0.05,
    ):
        self.latency_seconds = latency_seconds
        self._lock = asyncio.Lock()

        self.active_runs = 0
        self.max_active_runs = 0
        self.active_by_provider: dict[str, int] = defaultdict(int)
        self.max_active_by_provider: dict[str, int] = defaultdict(int)
        self.active_by_participant: dict[str, int] = defaultdict(int)
        self.max_active_by_participant: dict[str, int] = defaultdict(int)
        self.executed_run_ids: list[str] = []

    async def execute_live_run(
        self,
        request,
        event_sink=None,
    ) -> RunExecutionArtifact:
        raise NotImplementedError

    async def plan_run(
        self,
        request,
    ) -> RunPlan:
        participant_id = request.participant_id or "participant_1"
        return RunPlan(
            task_spec=TaskSpec(
                language=request.language,
                start_page_title=request.start_page_title,
                target_page_title=request.target_page_title,
            ),
            participant_spec=ParticipantSpec(
                participant_id=participant_id,
                participant_kind=ParticipantKind.LLM,
                display_name=request.participant_display_name or request.model_id,
                driver_config=DriverConfig(
                    provider=request.provider,
                    model=request.model_id,
                    settings=request.model_settings,
                ),
            ),
            run_spec=RunSpec(
                run_id=request.run_id or "run_1",
                benchmark_id=request.benchmark_id,
                race_id=request.race_id or "race_1",
                task_id="en__apple__banana",
                participant_id=participant_id,
                navigation_rules=request.navigation_rules,
            ),
            harness_config=request.harness_config,
            scoring_rules=request.scoring_rules,
            ruleset_hash=request.ruleset_hash,
            taskset_hash=request.taskset_hash,
            participant_hash=request.participant_hash,
            navigation_runtime=request.navigation_runtime,
            solver_runtime=request.solver_runtime,
            navigation_snapshot_id=request.navigation_snapshot_id,
            solver_snapshot_id=request.solver_snapshot_id,
        )

    async def execute_plan(
        self,
        run_plan,
        event_sink=None,
    ) -> RunExecutionArtifact:
        async with self._lock:
            self.active_runs += 1
            self.executed_run_ids.append(
                run_plan.run_spec.run_id,
            )
            self.max_active_runs = max(
                self.max_active_runs,
                self.active_runs,
            )

            provider = run_plan.participant_spec.driver_config.provider
            participant_id = run_plan.participant_spec.participant_id
            self.active_by_provider[provider] += 1
            self.max_active_by_provider[provider] = max(
                self.max_active_by_provider[provider],
                self.active_by_provider[provider],
            )
            self.active_by_participant[participant_id] += 1
            self.max_active_by_participant[participant_id] = max(
                self.max_active_by_participant[participant_id],
                self.active_by_participant[participant_id],
            )

        if event_sink is not None:
            sink_result = event_sink(
                EventEnvelope(
                    event_id=f"{run_plan.run_spec.run_id}:1",
                    event_type=RunEventType.RUN_STARTED,
                    benchmark_id=run_plan.run_spec.benchmark_id,
                    race_id=run_plan.run_spec.race_id,
                    run_id=run_plan.run_spec.run_id,
                    sequence=1,
                    payload={
                        "participant_id": run_plan.participant_spec.participant_id,
                    },
                ),
            )
            if inspect.isawaitable(
                sink_result,
            ):
                await sink_result

        await asyncio.sleep(
            self.latency_seconds,
        )

        now = datetime.now()
        run_result = RunResult(
            run_id=run_plan.run_spec.run_id,
            race_id=run_plan.run_spec.race_id,
            benchmark_id=run_plan.run_spec.benchmark_id,
            task_id=run_plan.run_spec.task_id,
            participant_id=run_plan.participant_spec.participant_id,
            terminal_outcome=TerminalOutcome.SUCCESS,
            termination_reason=TerminationReason.TASK_COMPLETED,
            step_attempts=[],
            ruleset_hash=run_plan.ruleset_hash,
            taskset_hash=run_plan.taskset_hash,
            participant_hash=run_plan.participant_hash,
            navigation_backend=run_plan.navigation_runtime.backend,
            solver_backend=run_plan.solver_runtime.backend,
            navigation_snapshot_id=run_plan.navigation_snapshot_id,
            solver_snapshot_id=run_plan.solver_snapshot_id,
            started_at=now,
            ended_at=now,
        )

        async with self._lock:
            self.active_runs -= 1
            self.active_by_provider[provider] -= 1
            self.active_by_participant[participant_id] -= 1

        return RunExecutionArtifact(
            run_result=run_result,
            events=[],
        )


def _build_benchmark_spec(
    *,
    task_count: int,
    participants: list[tuple[str, str, str]],
) -> BenchmarkSpec:
    return BenchmarkSpec(
        benchmark_id="benchmark_vnext",
        taskset_id="taskset_v1",
        rules=BenchmarkRules(
            harness=HarnessConfig(
                harness_id="tool_strict_v1",
            ),
        ),
        participants=[
            ParticipantSpec(
                participant_id=participant_id,
                participant_kind=ParticipantKind.LLM,
                display_name=participant_id,
                driver_config=DriverConfig(
                    provider=provider,
                    model=model,
                ),
            )
            for participant_id, provider, model in participants
        ],
        tasks=[
            TaskSpec(
                language="en",
                start_page_title=f"Start {task_index}",
                target_page_title=f"Target {task_index}",
            )
            for task_index in range(1, task_count + 1)
        ],
    )


@pytest.mark.asyncio
async def test_benchmark_runner_resume_skips_existing_non_system_failures() -> None:
    benchmark_spec = _build_benchmark_spec(
        task_count=1,
        participants=[
            ("p1", "provider_a", "m1"),
            ("p2", "provider_b", "m2"),
        ],
    )
    fake_service = FakeLiveRunService(
        latency_seconds=0.01,
    )
    runner = BenchmarkRunner(
        live_run_service=fake_service,
    )
    identity = plan_benchmark_identity(
        benchmark_spec,
        protocol_version="1.0.0-draft",
    )
    task = benchmark_spec.tasks[0]
    assert task.task_id is not None
    race_id = build_race_id(
        benchmark_id=benchmark_spec.benchmark_id,
        task_id=task.task_id,
        task_index=1,
    )
    now = datetime.now()
    existing_run_result = RunResult(
        run_id=build_run_id(
            race_id=race_id,
            participant_id="p1",
        ),
        race_id=race_id,
        benchmark_id=benchmark_spec.benchmark_id,
        task_id=task.task_id,
        participant_id="p1",
        terminal_outcome=TerminalOutcome.SUCCESS,
        termination_reason=TerminationReason.TASK_COMPLETED,
        ruleset_hash=identity.ruleset_hash,
        taskset_hash=identity.taskset_hash,
        participant_hash=identity.participant_hashes["p1"],
        navigation_backend=NavigationBackend.LIVE,
        solver_backend=SolverBackend.NONE,
        started_at=now,
        ended_at=now,
    )

    artifact = await runner.run_benchmark(
        benchmark_spec,
        resume=BenchmarkResumeConfig(
            existing_run_results=[existing_run_result],
        ),
    )

    assert artifact.total_runs == 2
    assert existing_run_result.run_id not in fake_service.executed_run_ids
    assert (
        build_run_id(
            race_id=race_id,
            participant_id="p2",
        )
        in fake_service.executed_run_ids
    )


@pytest.mark.asyncio
async def test_benchmark_runner_resume_reruns_existing_system_failures() -> None:
    benchmark_spec = _build_benchmark_spec(
        task_count=1,
        participants=[
            ("p1", "provider_a", "m1"),
        ],
    )
    fake_service = FakeLiveRunService(
        latency_seconds=0.01,
    )
    runner = BenchmarkRunner(
        live_run_service=fake_service,
    )
    identity = plan_benchmark_identity(
        benchmark_spec,
        protocol_version="1.0.0-draft",
    )
    task = benchmark_spec.tasks[0]
    assert task.task_id is not None
    race_id = build_race_id(
        benchmark_id=benchmark_spec.benchmark_id,
        task_id=task.task_id,
        task_index=1,
    )
    run_id = build_run_id(
        race_id=race_id,
        participant_id="p1",
    )
    now = datetime.now()
    existing_run_result = RunResult(
        run_id=run_id,
        race_id=race_id,
        benchmark_id=benchmark_spec.benchmark_id,
        task_id=task.task_id,
        participant_id="p1",
        terminal_outcome=TerminalOutcome.SYSTEM_FAILURE,
        termination_reason=TerminationReason.HARNESS_ERROR,
        ruleset_hash=identity.ruleset_hash,
        taskset_hash=identity.taskset_hash,
        participant_hash=identity.participant_hashes["p1"],
        navigation_backend=NavigationBackend.LIVE,
        solver_backend=SolverBackend.NONE,
        started_at=now,
        ended_at=now,
    )

    await runner.run_benchmark(
        benchmark_spec,
        resume=BenchmarkResumeConfig(
            existing_run_results=[existing_run_result],
        ),
    )

    assert fake_service.executed_run_ids == [run_id]


@pytest.mark.asyncio
async def test_benchmark_runner_parallelizes_runs_within_race() -> None:
    benchmark_spec = _build_benchmark_spec(
        task_count=1,
        participants=[
            ("p1", "openrouter", "m1"),
            ("p2", "openrouter", "m2"),
            ("p3", "openrouter", "m3"),
        ],
    )
    fake_service = FakeLiveRunService()
    runner = BenchmarkRunner(
        live_run_service=fake_service,
    )

    artifact = await runner.run_benchmark(
        benchmark_spec,
        concurrency=BenchmarkConcurrencyConfig(
            max_concurrent_tasks=1,
            max_concurrent_runs=3,
        ),
    )

    assert artifact.total_runs == 3
    assert len(artifact.race_results) == 1
    assert fake_service.max_active_runs >= 2
    assert fake_service.max_active_by_participant["p1"] == 1
    assert fake_service.max_active_by_participant["p2"] == 1


@pytest.mark.asyncio
async def test_benchmark_runner_respects_provider_concurrency_limits() -> None:
    benchmark_spec = _build_benchmark_spec(
        task_count=1,
        participants=[
            ("p1", "provider_a", "m1"),
            ("p2", "provider_a", "m2"),
            ("p3", "provider_b", "m3"),
        ],
    )
    fake_service = FakeLiveRunService()
    runner = BenchmarkRunner(
        live_run_service=fake_service,
    )

    await runner.run_benchmark(
        benchmark_spec,
        concurrency=BenchmarkConcurrencyConfig(
            max_concurrent_tasks=1,
            max_concurrent_runs=3,
            provider_max_concurrency={"provider_a": 1},
        ),
    )

    assert fake_service.max_active_by_provider["provider_a"] == 1
    assert fake_service.max_active_runs >= 2


@pytest.mark.asyncio
async def test_benchmark_runner_respects_participant_concurrency_limits() -> None:
    benchmark_spec = _build_benchmark_spec(
        task_count=3,
        participants=[
            ("p1", "provider_a", "m1"),
            ("p2", "provider_a", "m2"),
        ],
    )
    fake_service = FakeLiveRunService()
    runner = BenchmarkRunner(
        live_run_service=fake_service,
    )

    await runner.run_benchmark(
        benchmark_spec,
        concurrency=BenchmarkConcurrencyConfig(
            max_concurrent_tasks=3,
            max_concurrent_runs=6,
            participant_max_concurrency={"p1": 1, "p2": 1},
        ),
    )

    assert fake_service.max_active_runs >= 2


@pytest.mark.asyncio
async def test_benchmark_runner_persists_results_to_jsonl_store(
    tmp_path,
) -> None:
    benchmark_spec = _build_benchmark_spec(
        task_count=2,
        participants=[
            ("p1", "openrouter", "m1"),
            ("p2", "openrouter", "m2"),
        ],
    )
    fake_service = FakeLiveRunService(
        latency_seconds=0.01,
    )
    runner = BenchmarkRunner(
        live_run_service=fake_service,
    )

    results_path = tmp_path / "results.jsonl"
    result_store = RunResultStore(
        output_path=results_path,
    )

    artifact = await runner.run_benchmark(
        benchmark_spec,
        concurrency=BenchmarkConcurrencyConfig(
            max_concurrent_tasks=2,
            max_concurrent_runs=4,
        ),
        result_store=result_store,
    )

    assert artifact.total_runs == 4

    lines = results_path.read_text(
        encoding="utf-8",
    ).splitlines()
    assert len(lines) == 4

    parsed_records = [json.loads(line) for line in lines]
    assert {record["participant_id"] for record in parsed_records} == {"p1", "p2"}


@pytest.mark.asyncio
async def test_benchmark_runner_forwards_event_sink_to_run_service() -> None:
    benchmark_spec = _build_benchmark_spec(
        task_count=1,
        participants=[
            ("p1", "openrouter", "m1"),
            ("p2", "openrouter", "m2"),
        ],
    )
    fake_service = FakeLiveRunService(
        latency_seconds=0.01,
    )
    runner = BenchmarkRunner(
        live_run_service=fake_service,
    )

    observed_events = []

    async def sink(event) -> None:
        observed_events.append(
            event,
        )

    artifact = await runner.run_benchmark(
        benchmark_spec,
        concurrency=BenchmarkConcurrencyConfig(
            max_concurrent_tasks=1,
            max_concurrent_runs=2,
        ),
        event_sink=sink,
    )

    assert artifact.total_runs == 2
    assert len(observed_events) == 2


@pytest.mark.asyncio
async def test_benchmark_runner_uses_plan_run_for_runtime_resolution() -> None:
    class PlanningRunService:
        def __init__(self) -> None:
            self.plan_called = False

            class FakeRunExecutor:
                protocol_version = "1.0.0-test"

            self.run_executor = FakeRunExecutor()

        async def plan_run(self, request):
            self.plan_called = True
            return RunPlan(
                task_spec=TaskSpec(
                    language=request.language,
                    start_page_title=request.start_page_title,
                    target_page_title=request.target_page_title,
                ),
                participant_spec=ParticipantSpec(
                    participant_id=request.participant_id or "participant_1",
                    participant_kind=ParticipantKind.LLM,
                    display_name=request.participant_display_name or request.model_id,
                    driver_config=DriverConfig(
                        provider=request.provider,
                        model=request.model_id,
                        settings=request.model_settings,
                    ),
                ),
                run_spec=RunSpec(
                    run_id=request.run_id or "run_1",
                    benchmark_id=request.benchmark_id,
                    race_id=request.race_id or "race_1",
                    task_id="en__apple__banana",
                    participant_id=request.participant_id or "participant_1",
                    navigation_rules=request.navigation_rules,
                ),
                harness_config=request.harness_config,
                scoring_rules=request.scoring_rules,
                ruleset_hash=request.ruleset_hash,
                taskset_hash=request.taskset_hash,
                participant_hash=request.participant_hash,
                navigation_runtime=request.navigation_runtime,
                solver_runtime=request.solver_runtime,
                navigation_snapshot_id="enwiki-20260301",
                solver_snapshot_id="enwiki-20260301",
            )

        async def execute_plan(self, run_plan, event_sink=None):
            now = datetime.now()

            return RunExecutionArtifact(
                run_result=RunResult(
                    run_id=run_plan.run_spec.run_id,
                    race_id=run_plan.run_spec.race_id,
                    benchmark_id=run_plan.run_spec.benchmark_id,
                    task_id=run_plan.run_spec.task_id,
                    participant_id=run_plan.participant_spec.participant_id,
                    terminal_outcome=TerminalOutcome.SUCCESS,
                    termination_reason=TerminationReason.TASK_COMPLETED,
                    step_attempts=[],
                    ruleset_hash=run_plan.ruleset_hash,
                    taskset_hash=run_plan.taskset_hash,
                    participant_hash=run_plan.participant_hash,
                    navigation_backend=run_plan.navigation_runtime.backend,
                    solver_backend=run_plan.solver_runtime.backend,
                    navigation_snapshot_id=run_plan.navigation_snapshot_id,
                    solver_snapshot_id=run_plan.solver_snapshot_id,
                    task_execution_annotation=TaskExecutionAnnotation(
                        status=TaskExecutionAnnotationStatus.OK,
                        shortest_path_length=1,
                    ),
                    started_at=now,
                    ended_at=now,
                ),
                events=[],
            )

    benchmark_spec = _build_benchmark_spec(
        task_count=1,
        participants=[
            ("p1", "openai", "m1"),
        ],
    )
    fake_service = PlanningRunService()
    runner = BenchmarkRunner(
        live_run_service=fake_service,
    )

    artifact = await runner.run_benchmark(
        benchmark_spec,
        run_options=BenchmarkRunOptions(
            navigation_runtime=NavigationRuntimeConfig(
                backend=NavigationBackend.LIVE,
            ),
            solver_runtime=SolverRuntimeConfig(
                backend=SolverBackend.LOCAL,
            ),
        ),
    )

    assert fake_service.plan_called is True
    assert artifact.run_results[0].solver_snapshot_id == "enwiki-20260301"
    assert artifact.race_results[0].task_execution_annotation is not None
    assert artifact.race_results[0].task_execution_annotation.status == (
        TaskExecutionAnnotationStatus.OK
    )


def test_benchmark_run_options_reject_legacy_runtime_aliases() -> None:
    with pytest.raises(
        ValidationError,
        match="solver_mode",
    ):
        BenchmarkRunOptions.model_validate(
            {
                "solver_mode": "local",
            },
        )
