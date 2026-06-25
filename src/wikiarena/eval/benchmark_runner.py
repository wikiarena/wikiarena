from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field

from wikiarena.adapters.wiki import (
    CachedWikiNavigator,
    GraphWikipediaNavigator,
    LiveWikipediaNavigator,
)
from wikiarena.core.run_executor import EventSink
from wikiarena.eval.planner import (
    BenchmarkIdentityPlan,
    build_race_id,
    build_run_id,
    plan_benchmark_identity,
)
from wikiarena.eval.run_result_store import RunResultStore
from wikiarena.eval.run_service import RunPlan, RunRequest, RunService
from wikiarena.protocol import (
    BenchmarkSpec,
    NavigationBackend,
    NavigationRules,
    RaceResult,
    RunResult,
    RunSpec,
    TaskSpec,
    TerminalOutcome,
)
from wikiarena.protocol.results import TaskExecutionAnnotation
from wikiarena.protocol.specs import ParticipantSpec
from wikiarena.protocol.version import DEFAULT_PROTOCOL_VERSION
from wikiarena.solver.binary import MappedBinarySolverGraph
from wikiarena.solver_runtime import SolverRuntimeConfig
from wikiarena.wiki_runtime import NavigationRuntimeConfig, resolve_graph_file_path
from wikiarena.wikipedia import LiveWikiService

_MISSING_TASK_EXECUTION_ANNOTATION = object()


class BenchmarkConcurrencyConfig(BaseModel):
    max_concurrent_tasks: int = Field(
        default=2,
        ge=1,
    )
    max_concurrent_runs: int = Field(
        default=8,
        ge=1,
    )
    max_concurrent_runs_per_race: int | None = Field(
        default=None,
        ge=1,
    )
    provider_max_concurrency: dict[str, int] = Field(
        default_factory=dict,
    )
    participant_max_concurrency: dict[str, int] = Field(
        default_factory=dict,
    )


class BenchmarkRunOptions(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    navigation_runtime: NavigationRuntimeConfig = Field(
        default_factory=NavigationRuntimeConfig,
    )
    solver_runtime: SolverRuntimeConfig = Field(
        default_factory=SolverRuntimeConfig,
    )
    navigation_snapshot_id: str | None = None
    solver_snapshot_id: str | None = None


class BenchmarkResumeConfig(BaseModel):
    existing_run_results: list[RunResult] = Field(
        default_factory=list,
    )
    rerun_system_failures: bool = True


class BenchmarkExecutionArtifact(BaseModel):
    benchmark_id: str
    race_results: list[RaceResult]
    run_results: list[RunResult]
    started_at: datetime
    ended_at: datetime

    @property
    def total_runs(self) -> int:
        return len(
            self.run_results,
        )


class BenchmarkRunner:
    def __init__(
        self,
        *,
        run_service: RunService | None = None,
        live_run_service: RunService | None = None,
        enable_shared_wiki_cache: bool = True,
    ):
        injected_run_service = run_service or live_run_service
        if injected_run_service is not None:
            self.run_service = injected_run_service
            return

        self.run_service = _create_default_run_service(
            enable_shared_wiki_cache=enable_shared_wiki_cache,
        )

    async def run_benchmark(
        self,
        benchmark_spec: BenchmarkSpec,
        *,
        concurrency: BenchmarkConcurrencyConfig | None = None,
        run_options: BenchmarkRunOptions | None = None,
        resume: BenchmarkResumeConfig | None = None,
        taskset_hash_override: str | None = None,
        result_store: RunResultStore | None = None,
        event_sink: EventSink | None = None,
    ) -> BenchmarkExecutionArtifact:
        started_at = datetime.now()

        resolved_concurrency = _resolve_concurrency(
            benchmark_spec=benchmark_spec,
            concurrency=concurrency,
        )
        resolved_run_options = run_options or BenchmarkRunOptions()
        protocol_version = _resolve_protocol_version(
            self.run_service,
        )
        benchmark_identity = plan_benchmark_identity(
            benchmark_spec,
            protocol_version=protocol_version,
        )
        if taskset_hash_override is not None:
            benchmark_identity = benchmark_identity.model_copy(
                update={
                    "taskset_hash": taskset_hash_override,
                },
            )
        resume_index = _build_resume_index(
            resume,
        )

        task_semaphore = asyncio.Semaphore(
            resolved_concurrency.max_concurrent_tasks,
        )
        run_semaphore = asyncio.Semaphore(
            resolved_concurrency.max_concurrent_runs,
        )
        provider_semaphores = {
            provider: asyncio.Semaphore(
                limit,
            )
            for provider, limit in resolved_concurrency.provider_max_concurrency.items()
            if limit > 0
        }
        participant_semaphores = {
            participant_id: asyncio.Semaphore(
                limit,
            )
            for participant_id, limit in resolved_concurrency.participant_max_concurrency.items()
            if limit > 0
        }
        store_lock = asyncio.Lock()

        race_tasks = [
            asyncio.create_task(
                self._execute_race(
                    benchmark_spec=benchmark_spec,
                    benchmark_identity=benchmark_identity,
                    task_index=task_index,
                    task_spec=task_spec,
                    run_options=resolved_run_options,
                    resume=resume,
                    resume_index=resume_index,
                    concurrency=resolved_concurrency,
                    task_semaphore=task_semaphore,
                    run_semaphore=run_semaphore,
                    provider_semaphores=provider_semaphores,
                    participant_semaphores=participant_semaphores,
                    result_store=result_store,
                    store_lock=store_lock,
                    event_sink=event_sink,
                ),
            )
            for task_index, task_spec in enumerate(
                benchmark_spec.tasks,
                start=1,
            )
        ]
        race_results = await asyncio.gather(
            *race_tasks,
        )

        run_results: list[RunResult] = []
        for race_result in race_results:
            run_results.extend(
                race_result.run_results,
            )

        return BenchmarkExecutionArtifact(
            benchmark_id=benchmark_spec.benchmark_id,
            race_results=race_results,
            run_results=run_results,
            started_at=started_at,
            ended_at=datetime.now(),
        )

    async def _execute_race(
        self,
        *,
        benchmark_spec: BenchmarkSpec,
        benchmark_identity: BenchmarkIdentityPlan,
        task_index: int,
        task_spec: TaskSpec,
        run_options: BenchmarkRunOptions,
        resume: BenchmarkResumeConfig | None,
        resume_index: dict[str, RunResult],
        concurrency: BenchmarkConcurrencyConfig,
        task_semaphore: asyncio.Semaphore,
        run_semaphore: asyncio.Semaphore,
        provider_semaphores: dict[str, asyncio.Semaphore],
        participant_semaphores: dict[str, asyncio.Semaphore],
        result_store: RunResultStore | None,
        store_lock: asyncio.Lock,
        event_sink: EventSink | None,
    ) -> RaceResult:
        async with task_semaphore:
            if task_spec.task_id is None:
                raise ValueError(
                    "task_id cannot be null when executing benchmark race",
                )
            task_id = task_spec.task_id

            race_id = build_race_id(
                benchmark_id=benchmark_spec.benchmark_id,
                task_id=task_id,
                task_index=task_index,
                start_page_title=task_spec.start_page_title,
                target_page_title=task_spec.target_page_title,
            )

            race_run_semaphore = None
            if concurrency.max_concurrent_runs_per_race is not None:
                race_run_semaphore = asyncio.Semaphore(
                    concurrency.max_concurrent_runs_per_race,
                )

            run_tasks_by_participant_id = {}
            run_results_by_participant_id: dict[str, RunResult] = {}
            for participant_spec in benchmark_spec.participants:
                run_id = build_run_id(
                    race_id=race_id,
                    participant_id=participant_spec.participant_id,
                )
                resumable_run_result = _lookup_resumable_run_result(
                    run_id=run_id,
                    participant_spec=participant_spec,
                    benchmark_identity=benchmark_identity,
                    run_options=run_options,
                    resume=resume,
                    resume_index=resume_index,
                )
                if resumable_run_result is not None:
                    run_results_by_participant_id[participant_spec.participant_id] = (
                        resumable_run_result
                    )
                    continue

                run_tasks_by_participant_id[participant_spec.participant_id] = (
                    asyncio.create_task(
                        self._execute_single_run(
                            benchmark_spec=benchmark_spec,
                            benchmark_identity=benchmark_identity,
                            task_spec=task_spec,
                            race_id=race_id,
                            participant_spec=participant_spec,
                            run_options=run_options,
                            run_semaphore=run_semaphore,
                            race_run_semaphore=race_run_semaphore,
                            provider_semaphores=provider_semaphores,
                            participant_semaphores=participant_semaphores,
                            result_store=result_store,
                            store_lock=store_lock,
                            event_sink=event_sink,
                        ),
                    )
                )

            if run_tasks_by_participant_id:
                executed_run_results = await asyncio.gather(
                    *run_tasks_by_participant_id.values(),
                )
                for participant_id, run_result in zip(
                    run_tasks_by_participant_id,
                    executed_run_results,
                    strict=True,
                ):
                    run_results_by_participant_id[participant_id] = run_result

            run_results = [
                run_results_by_participant_id[participant_spec.participant_id]
                for participant_spec in benchmark_spec.participants
                if participant_spec.participant_id in run_results_by_participant_id
            ]
            race_task_execution_annotation = _resolve_shared_task_execution_annotation(
                run_results,
            )

            return RaceResult(
                race_id=race_id,
                benchmark_id=benchmark_spec.benchmark_id,
                task_id=task_id,
                task_execution_annotation=race_task_execution_annotation,
                run_results=run_results,
            )

    async def _execute_single_run(
        self,
        *,
        benchmark_spec: BenchmarkSpec,
        benchmark_identity: BenchmarkIdentityPlan,
        task_spec: TaskSpec,
        race_id: str,
        participant_spec: ParticipantSpec,
        run_options: BenchmarkRunOptions,
        run_semaphore: asyncio.Semaphore,
        race_run_semaphore: asyncio.Semaphore | None,
        provider_semaphores: dict[str, asyncio.Semaphore],
        participant_semaphores: dict[str, asyncio.Semaphore],
        result_store: RunResultStore | None,
        store_lock: asyncio.Lock,
        event_sink: EventSink | None,
    ) -> RunResult:
        if task_spec.task_id is None:
            raise ValueError(
                "task_id cannot be null when creating run request",
            )

        run_id = build_run_id(
            race_id=race_id,
            participant_id=participant_spec.participant_id,
        )
        participant_hash = benchmark_identity.participant_hashes.get(
            participant_spec.participant_id,
        )
        if participant_hash is None:
            raise ValueError(
                f"Missing participant_hash for participant_id '{participant_spec.participant_id}'",
            )

        run_request = RunRequest(
            model_id=participant_spec.driver_config.model,
            provider=participant_spec.driver_config.provider,
            start_page_title=task_spec.start_page_title,
            target_page_title=task_spec.target_page_title,
            language=task_spec.language,
            participant_id=participant_spec.participant_id,
            participant_display_name=participant_spec.display_name,
            model_settings=participant_spec.driver_config.settings,
            benchmark_id=benchmark_spec.benchmark_id,
            race_id=race_id,
            run_id=run_id,
            navigation_rules=benchmark_spec.rules.navigation,
            scoring_rules=benchmark_spec.rules.scoring,
            harness_config=benchmark_spec.rules.harness,
            ruleset_hash=benchmark_identity.ruleset_hash,
            taskset_hash=benchmark_identity.taskset_hash,
            participant_hash=participant_hash,
            navigation_runtime=run_options.navigation_runtime,
            solver_runtime=run_options.solver_runtime,
            navigation_snapshot_id=run_options.navigation_snapshot_id,
            solver_snapshot_id=run_options.solver_snapshot_id,
        )
        run_plan = await self.run_service.plan_run(
            run_request,
        )

        provider_semaphore = provider_semaphores.get(
            participant_spec.driver_config.provider,
        )
        participant_semaphore = participant_semaphores.get(
            participant_spec.participant_id,
        )

        artifact = await _execute_with_semaphore_limits(
            run_plan=run_plan,
            run_service=self.run_service,
            run_semaphore=run_semaphore,
            race_run_semaphore=race_run_semaphore,
            provider_semaphore=provider_semaphore,
            participant_semaphore=participant_semaphore,
            event_sink=event_sink,
        )

        if result_store is not None:
            async with store_lock:
                await asyncio.to_thread(
                    result_store.append_artifact,
                    artifact,
                )

        return artifact.run_result


async def _execute_with_semaphore_limits(
    *,
    run_plan: RunPlan,
    run_service: RunService,
    run_semaphore: asyncio.Semaphore,
    race_run_semaphore: asyncio.Semaphore | None,
    provider_semaphore: asyncio.Semaphore | None,
    participant_semaphore: asyncio.Semaphore | None,
    event_sink: EventSink | None,
):
    async with run_semaphore:
        if race_run_semaphore is not None:
            async with race_run_semaphore:
                return await _execute_with_optional_limiters(
                    run_plan,
                    event_sink=event_sink,
                    run_service=run_service,
                    provider_semaphore=provider_semaphore,
                    participant_semaphore=participant_semaphore,
                )

        return await _execute_with_optional_limiters(
            run_plan,
            event_sink=event_sink,
            run_service=run_service,
            provider_semaphore=provider_semaphore,
            participant_semaphore=participant_semaphore,
        )


async def _execute_with_optional_limiters(
    run_plan: RunPlan,
    *,
    run_service: RunService,
    provider_semaphore: asyncio.Semaphore | None,
    participant_semaphore: asyncio.Semaphore | None,
    event_sink: EventSink | None,
):
    if provider_semaphore is not None:
        async with provider_semaphore:
            if participant_semaphore is not None:
                async with participant_semaphore:
                    return await run_service.execute_plan(
                        run_plan,
                        event_sink=event_sink,
                    )
            return await run_service.execute_plan(
                run_plan,
                event_sink=event_sink,
            )

    if participant_semaphore is not None:
        async with participant_semaphore:
            return await run_service.execute_plan(
                run_plan,
                event_sink=event_sink,
            )

    return await run_service.execute_plan(
        run_plan,
        event_sink=event_sink,
    )


def _resolve_concurrency(
    *,
    benchmark_spec: BenchmarkSpec,
    concurrency: BenchmarkConcurrencyConfig | None,
) -> BenchmarkConcurrencyConfig:
    if concurrency is not None:
        return concurrency

    default_max_runs = benchmark_spec.rules.execution.max_concurrency or 8
    return BenchmarkConcurrencyConfig(
        max_concurrent_tasks=2,
        max_concurrent_runs=default_max_runs,
    )


def _build_resume_index(
    resume: BenchmarkResumeConfig | None,
) -> dict[str, RunResult]:
    if resume is None:
        return {}

    return {run_result.run_id: run_result for run_result in resume.existing_run_results}


def _lookup_resumable_run_result(
    *,
    run_id: str,
    participant_spec: ParticipantSpec,
    benchmark_identity: BenchmarkIdentityPlan,
    run_options: BenchmarkRunOptions,
    resume: BenchmarkResumeConfig | None,
    resume_index: dict[str, RunResult],
) -> RunResult | None:
    if resume is None:
        return None

    run_result = resume_index.get(
        run_id,
    )
    if run_result is None:
        return None

    if (
        resume.rerun_system_failures
        and run_result.terminal_outcome == TerminalOutcome.SYSTEM_FAILURE
    ):
        return None

    participant_hash = benchmark_identity.participant_hashes.get(
        participant_spec.participant_id,
    )
    if participant_hash is None:
        return None

    if run_result.ruleset_hash != benchmark_identity.ruleset_hash:
        return None
    if run_result.taskset_hash != benchmark_identity.taskset_hash:
        return None
    if run_result.participant_hash != participant_hash:
        return None
    if run_result.navigation_backend != run_options.navigation_runtime.backend:
        return None
    if run_result.solver_backend != run_options.solver_runtime.backend:
        return None
    if (
        run_options.navigation_snapshot_id is not None
        and run_result.navigation_snapshot_id != run_options.navigation_snapshot_id
    ):
        return None
    if (
        run_options.solver_snapshot_id is not None
        and run_result.solver_snapshot_id != run_options.solver_snapshot_id
    ):
        return None

    return run_result


def _resolve_shared_task_execution_annotation(
    run_results: list[RunResult],
) -> TaskExecutionAnnotation | None:
    shared_annotation = _MISSING_TASK_EXECUTION_ANNOTATION
    for run_result in run_results:
        annotation = run_result.task_execution_annotation
        if shared_annotation is _MISSING_TASK_EXECUTION_ANNOTATION:
            shared_annotation = annotation
            continue
        if annotation != shared_annotation:
            raise ValueError(
                "run results in the same race produced different task_execution_annotation values",
            )
    if shared_annotation is _MISSING_TASK_EXECUTION_ANNOTATION:
        return None
    return cast(
        TaskExecutionAnnotation | None,
        shared_annotation,
    )


def _resolve_protocol_version(
    run_service: RunService,
) -> str:
    run_executor = getattr(
        run_service,
        "run_executor",
        None,
    )
    if run_executor is None:
        return DEFAULT_PROTOCOL_VERSION

    protocol_version = getattr(
        run_executor,
        "protocol_version",
        None,
    )
    if (
        isinstance(
            protocol_version,
            str,
        )
        and protocol_version
    ):
        return protocol_version

    return DEFAULT_PROTOCOL_VERSION


def _create_default_run_service(
    *,
    enable_shared_wiki_cache: bool,
) -> RunService:
    if not enable_shared_wiki_cache:
        return RunService()

    per_language_navigators: dict[str, CachedWikiNavigator] = {}
    graph_navigators: dict[str, GraphWikipediaNavigator] = {}

    def wiki_navigator_factory(
        run_plan: RunPlan,
    ):
        navigation_runtime = run_plan.navigation_runtime
        if navigation_runtime.backend == NavigationBackend.GRAPH:
            graph_path = str(
                resolve_graph_file_path(
                    navigation_runtime.graph_path,
                ),
            )
            cached_graph_navigator = graph_navigators.get(
                graph_path,
            )
            if cached_graph_navigator is not None:
                return cached_graph_navigator

            graph_navigator = GraphWikipediaNavigator(
                graph=MappedBinarySolverGraph(
                    file_path=Path(
                        graph_path,
                    ),
                ),
            )
            graph_navigators[graph_path] = graph_navigator
            return graph_navigator

        language = run_plan.task_spec.language
        cached_navigator = per_language_navigators.get(
            language,
        )
        if cached_navigator is not None:
            return cached_navigator

        base_navigator = LiveWikipediaNavigator(
            wiki_service=LiveWikiService(
                language=language,
            ),
        )
        cached_navigator = CachedWikiNavigator(
            base_navigator,
        )
        per_language_navigators[language] = cached_navigator
        return cached_navigator

    return RunService(
        wiki_navigator_factory=wiki_navigator_factory,
    )


def benchmark_spec_run_spec(
    *,
    benchmark_id: str,
    race_id: str,
    run_id: str,
    task_id: str | None,
    participant_id: str,
    navigation_rules: NavigationRules,
) -> RunSpec:
    if task_id is None:
        raise ValueError(
            "task_id cannot be null when building RunSpec for benchmark execution",
        )
    return RunSpec(
        run_id=run_id,
        benchmark_id=benchmark_id,
        race_id=race_id,
        task_id=task_id,
        participant_id=participant_id,
        navigation_rules=navigation_rules,
    )
