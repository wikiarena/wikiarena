from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Protocol

from pydantic import BaseModel, ConfigDict, Field

from wikiarena.adapters.participants import (
    FirstLinkParticipant,
    ProviderParticipant,
    RandomLinkParticipant,
)
from wikiarena.adapters.wiki import GraphWikipediaNavigator, LiveWikipediaNavigator
from wikiarena.core import (
    ParticipantDriver,
    RunExecutionArtifact,
    RunExecutor,
    WikiNavigator,
)
from wikiarena.core.run_executor import EventSink
from wikiarena.eval.planner import build_participant_hash, build_ruleset_hash
from wikiarena.protocol import (
    DriverConfig,
    HarnessConfig,
    NavigationBackend,
    NavigationRules,
    ParticipantKind,
    ParticipantSpec,
    RunSpec,
    ScoringRules,
    SolverBackend,
    TaskSpec,
)
from wikiarena.protocol.enums import PathSource, TaskExecutionAnnotationStatus
from wikiarena.protocol.results import TaskExecutionAnnotation
from wikiarena.protocol.specs import SolverShortestPath
from wikiarena.providers import create_provider_client
from wikiarena.solver import BinarySolverBackend
from wikiarena.solver.binary import MappedBinarySolverGraph
from wikiarena.solver.models import PositionSolverFacts, SolverResponse
from wikiarena.solver_runtime import (
    SolverRuntimeConfig,
    resolve_solver_graph_file_path,
    resolve_solver_snapshot_id,
)
from wikiarena.wiki_runtime import (
    NavigationRuntimeConfig,
    resolve_graph_file_path,
    resolve_graph_snapshot_id,
)
from wikiarena.wikipedia import LiveWikiService

ParticipantFactory = Callable[[ParticipantSpec], ParticipantDriver]
WikiNavigatorFactory = Callable[["RunPlan"], WikiNavigator]


class SolverShortestPathOracle(Protocol):
    async def get_solver_shortest_path(
        self,
        task: TaskSpec,
    ) -> SolverShortestPath | None: ...


@dataclass(frozen=True)
class SolverTaskContext:
    solver_shortest_path: SolverShortestPath | None = None
    task_execution_annotation: TaskExecutionAnnotation | None = None
    position_solver_facts: PositionSolverFacts | None = None


class RunRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    model_id: str
    provider: str = "openai"
    start_page_title: str
    target_page_title: str
    language: str = "en"

    participant_id: str | None = None
    participant_display_name: str | None = None
    model_settings: dict[str, Any] = Field(
        default_factory=dict,
    )

    benchmark_id: str = "adhoc_benchmark"
    race_id: str | None = None
    run_id: str | None = None

    navigation_rules: NavigationRules = Field(
        default_factory=NavigationRules,
    )
    scoring_rules: ScoringRules = Field(
        default_factory=ScoringRules,
    )
    harness_config: HarnessConfig = Field(
        default_factory=lambda: HarnessConfig(
            harness_id="tool_strict_v1",
        ),
    )

    ruleset_hash: str | None = None
    taskset_hash: str | None = None
    participant_hash: str | None = None

    navigation_runtime: NavigationRuntimeConfig = Field(
        default_factory=NavigationRuntimeConfig,
    )
    solver_runtime: SolverRuntimeConfig = Field(
        default_factory=SolverRuntimeConfig,
    )
    navigation_snapshot_id: str | None = None
    solver_snapshot_id: str | None = None


class RunPlan(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    task_spec: TaskSpec
    participant_spec: ParticipantSpec
    run_spec: RunSpec
    harness_config: HarnessConfig
    scoring_rules: ScoringRules
    ruleset_hash: str | None = None
    taskset_hash: str | None = None
    participant_hash: str | None = None
    navigation_runtime: NavigationRuntimeConfig = Field(
        default_factory=NavigationRuntimeConfig,
    )
    solver_runtime: SolverRuntimeConfig = Field(
        default_factory=SolverRuntimeConfig,
    )
    navigation_snapshot_id: str | None = None
    solver_snapshot_id: str | None = None
    task_execution_annotation: TaskExecutionAnnotation | None = None
    initial_position_solver_facts: PositionSolverFacts | None = None


class RunService:
    def __init__(
        self,
        *,
        participant_factory: ParticipantFactory | None = None,
        wiki_navigator_factory: WikiNavigatorFactory | None = None,
        solver_shortest_path_oracle: SolverShortestPathOracle | None = None,
        run_executor: RunExecutor | None = None,
    ):
        self.participant_factory = participant_factory or _default_participant_factory
        self.wiki_navigator_factory = (
            wiki_navigator_factory or _default_wiki_navigator_factory
        )
        self.solver_shortest_path_oracle = solver_shortest_path_oracle
        self.run_executor = run_executor or RunExecutor()

    async def plan_run(
        self,
        request: RunRequest,
    ) -> RunPlan:
        task_spec = TaskSpec(
            language=request.language,
            start_page_title=request.start_page_title,
            target_page_title=request.target_page_title,
        )
        if task_spec.task_id is None:
            raise ValueError(
                "task_id cannot be null after TaskSpec validation",
            )

        resolved_navigation_snapshot_id = (
            request.navigation_snapshot_id or request.navigation_runtime.snapshot_id
        )
        resolved_navigation_runtime = request.navigation_runtime
        if request.navigation_runtime.backend == NavigationBackend.GRAPH:
            resolved_graph_path = resolve_graph_file_path(
                request.navigation_runtime.graph_path,
            )
            resolved_navigation_runtime = request.navigation_runtime.model_copy(
                update={
                    "graph_path": resolved_graph_path,
                },
            )
            resolved_navigation_snapshot_id = resolve_graph_snapshot_id(
                resolved_graph_path,
                resolved_navigation_snapshot_id,
            )

        resolved_solver_runtime = request.solver_runtime
        resolved_solver_snapshot_id = (
            request.solver_snapshot_id or request.solver_runtime.snapshot_id
        )
        solver_backend = request.solver_runtime.backend
        if solver_backend == SolverBackend.LOCAL:
            fallback_navigation_graph_path = None
            if resolved_navigation_runtime.backend == NavigationBackend.GRAPH:
                fallback_navigation_graph_path = resolved_navigation_runtime.graph_path
            resolved_solver_graph_path = resolve_solver_graph_file_path(
                request.solver_runtime.graph_path,
                fallback_graph_path=fallback_navigation_graph_path,
            )
            resolved_solver_runtime = request.solver_runtime.model_copy(
                update={
                    "graph_path": resolved_solver_graph_path,
                },
            )
            resolved_solver_snapshot_id = resolve_solver_snapshot_id(
                resolved_solver_graph_path,
                resolved_solver_snapshot_id,
            )

        solver_shortest_path: SolverShortestPath | None = None
        task_execution_annotation: TaskExecutionAnnotation | None = None
        initial_position_solver_facts: PositionSolverFacts | None = None
        if solver_backend != SolverBackend.NONE:
            solver_task_context = await _resolve_solver_task_context(
                task_spec=task_spec,
                solver_runtime=resolved_solver_runtime,
                solver_snapshot_id=resolved_solver_snapshot_id,
                injected_solver_shortest_path_oracle=self.solver_shortest_path_oracle,
            )
            solver_shortest_path = solver_task_context.solver_shortest_path
            task_execution_annotation = solver_task_context.task_execution_annotation
            initial_position_solver_facts = solver_task_context.position_solver_facts
            if (
                solver_shortest_path is not None
                and solver_shortest_path.solver_snapshot_id is None
                and resolved_solver_snapshot_id is not None
            ):
                solver_shortest_path = solver_shortest_path.model_copy(
                    update={
                        "solver_snapshot_id": resolved_solver_snapshot_id,
                    },
                )

            task_spec_update: dict[str, object] = {}
            if solver_shortest_path is not None:
                task_spec_update["solver_shortest_path"] = solver_shortest_path
            if (
                task_execution_annotation is not None
                and task_execution_annotation.shortest_path_length is not None
            ):
                task_spec_update["shortest_path_length"] = (
                    task_execution_annotation.shortest_path_length
                )
            if task_spec_update:
                task_spec = TaskSpec.model_validate(
                    task_spec.model_dump()
                    | task_spec_update,
                )

            if (
                resolved_solver_snapshot_id is None
                and solver_shortest_path is not None
                and solver_shortest_path.solver_snapshot_id is not None
            ):
                resolved_solver_snapshot_id = solver_shortest_path.solver_snapshot_id

        task_id = task_spec.task_id
        if task_id is None:
            raise ValueError(
                "task_id cannot be null after TaskSpec enrichment",
            )

        participant_spec = ParticipantSpec(
            participant_id=request.participant_id
            or _default_participant_id(
                request.model_id,
            ),
            participant_kind=ParticipantKind.LLM,
            display_name=request.participant_display_name or request.model_id,
            driver_config=DriverConfig(
                provider=request.provider,
                model=request.model_id,
                settings=request.model_settings,
            ),
        )

        race_id = request.race_id or _default_race_id(
            benchmark_id=request.benchmark_id,
            task_id=task_id,
        )
        run_id = request.run_id or _default_run_id(
            race_id=race_id,
            participant_id=participant_spec.participant_id,
        )

        run_spec = RunSpec(
            run_id=run_id,
            benchmark_id=request.benchmark_id,
            race_id=race_id,
            task_id=task_id,
            participant_id=participant_spec.participant_id,
            navigation_rules=request.navigation_rules,
        )

        resolved_ruleset_hash = request.ruleset_hash or build_ruleset_hash(
            protocol_version=self.run_executor.protocol_version,
            navigation_rules=request.navigation_rules,
            harness_config=request.harness_config,
            scoring_rules=request.scoring_rules,
        )
        resolved_participant_hash = request.participant_hash or build_participant_hash(
            participant_spec,
        )

        return RunPlan(
            task_spec=task_spec,
            participant_spec=participant_spec,
            run_spec=run_spec,
            harness_config=request.harness_config,
            scoring_rules=request.scoring_rules,
            ruleset_hash=resolved_ruleset_hash,
            taskset_hash=request.taskset_hash,
            participant_hash=resolved_participant_hash,
            navigation_runtime=resolved_navigation_runtime,
            solver_runtime=resolved_solver_runtime,
            navigation_snapshot_id=resolved_navigation_snapshot_id,
            solver_snapshot_id=resolved_solver_snapshot_id,
            task_execution_annotation=task_execution_annotation,
            initial_position_solver_facts=initial_position_solver_facts,
        )

    async def execute_plan(
        self,
        run_plan: RunPlan,
        *,
        event_sink: EventSink | None = None,
    ) -> RunExecutionArtifact:
        participant_driver = self.participant_factory(
            run_plan.participant_spec,
        )
        wiki_navigator = self.wiki_navigator_factory(
            run_plan,
        )
        local_solver_backend = None
        solver_target_session = None
        if run_plan.solver_runtime.backend == SolverBackend.LOCAL:
            solver_graph_path = resolve_solver_graph_file_path(
                run_plan.solver_runtime.graph_path,
            )
            local_solver_backend = BinarySolverBackend.from_file_path(
                solver_graph_path,
                snapshot_id=run_plan.solver_snapshot_id,
                path_mode="all_shortest",
            )
            solver_target_session = await local_solver_backend.create_target_session(
                run_plan.task_spec.target_page_title,
            )

        try:
            return await self.run_executor.execute_run(
                run_spec=run_plan.run_spec,
                task_spec=run_plan.task_spec,
                participant=participant_driver,
                wiki_navigator=wiki_navigator,
                harness_id=run_plan.harness_config.harness_id,
                harness_config=run_plan.harness_config,
                scoring_rules=run_plan.scoring_rules,
                ruleset_hash=run_plan.ruleset_hash,
                taskset_hash=run_plan.taskset_hash,
                participant_hash=run_plan.participant_hash,
                solver_backend=run_plan.solver_runtime.backend,
                navigation_backend=run_plan.navigation_runtime.backend,
                navigation_snapshot_id=run_plan.navigation_snapshot_id,
                solver_snapshot_id=run_plan.solver_snapshot_id,
                task_execution_annotation=run_plan.task_execution_annotation,
                initial_position_solver_facts=run_plan.initial_position_solver_facts,
                solver_target_session=solver_target_session,
                event_sink=event_sink,
            )
        finally:
            if local_solver_backend is not None:
                await local_solver_backend.shutdown()

    async def run(
        self,
        request: RunRequest,
        *,
        event_sink: EventSink | None = None,
    ) -> RunExecutionArtifact:
        run_plan = await self.plan_run(
            request,
        )
        return await self.execute_plan(
            run_plan,
            event_sink=event_sink,
        )

    async def execute_live_run(
        self,
        request: RunRequest,
        event_sink: EventSink | None = None,
    ) -> RunExecutionArtifact:
        return await self.run(
            request,
            event_sink=event_sink,
        )


def _default_participant_factory(
    participant_spec: ParticipantSpec,
) -> ParticipantDriver:
    if _is_wikiarena_random_participant(participant_spec):
        seed = participant_spec.driver_config.settings.get("seed")
        move_delay_s = participant_spec.driver_config.settings.get(
            "move_delay_s",
            1.0,
        )
        return RandomLinkParticipant(
            seed=seed if isinstance(seed, int) else None,
            move_delay_s=move_delay_s if isinstance(move_delay_s, (int, float)) else 1.0,
        )

    if _is_wikiarena_first_link_participant(participant_spec):
        move_delay_s = participant_spec.driver_config.settings.get(
            "move_delay_s",
            1.0,
        )
        return FirstLinkParticipant(
            move_delay_s=move_delay_s if isinstance(move_delay_s, (int, float)) else 1.0,
        )

    provider_settings, model_settings = _split_driver_settings(
        participant_spec.driver_config.settings,
    )
    provider_client = create_provider_client(
        participant_spec.driver_config.provider,
        provider_settings=provider_settings,
    )

    return ProviderParticipant(
        provider_client=provider_client,
        model_id=participant_spec.driver_config.model,
        model_settings=model_settings,
    )


def _is_wikiarena_random_participant(participant_spec: ParticipantSpec) -> bool:
    return (
        participant_spec.driver_config.provider == "wikiarena"
        and participant_spec.driver_config.model == "random"
    ) or (
        participant_spec.driver_config.provider == "random"
        and participant_spec.driver_config.model == "random"
    )


def _is_wikiarena_first_link_participant(participant_spec: ParticipantSpec) -> bool:
    return (
        participant_spec.driver_config.provider == "wikiarena"
        and participant_spec.driver_config.model == "first"
    )


def _split_driver_settings(
    settings: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    merged_settings = dict(
        settings,
    )
    provider_settings = dict(
        merged_settings.pop(
            "provider_settings",
            {},
        ),
    )

    provider_setting_aliases = [
        "auth_file",
        "base_url",
        "api_key",
        "extra_headers",
        "timeout_s",
    ]
    for key in provider_setting_aliases:
        if key not in merged_settings:
            continue
        if key in provider_settings:
            merged_settings.pop(
                key,
            )
            continue
        provider_settings[key] = merged_settings.pop(
            key,
        )

    return provider_settings, merged_settings


def _default_wiki_navigator_factory(
    run_plan: RunPlan,
) -> WikiNavigator:
    if run_plan.navigation_runtime.backend == NavigationBackend.GRAPH:
        graph_path = resolve_graph_file_path(
            run_plan.navigation_runtime.graph_path,
        )
        return GraphWikipediaNavigator(
            graph=MappedBinarySolverGraph(
                file_path=graph_path,
            ),
        )

    return LiveWikipediaNavigator(
        wiki_service=LiveWikiService(
            language=run_plan.task_spec.language,
        ),
    )


async def _resolve_solver_task_context(
    *,
    task_spec: TaskSpec,
    solver_runtime: SolverRuntimeConfig,
    solver_snapshot_id: str | None,
    injected_solver_shortest_path_oracle: SolverShortestPathOracle | None,
) -> SolverTaskContext:
    if solver_runtime.backend == SolverBackend.LOCAL:
        solver_graph_path = resolve_solver_graph_file_path(
            solver_runtime.graph_path,
        )
        local_backend = BinarySolverBackend.from_file_path(
            solver_graph_path,
            snapshot_id=solver_snapshot_id,
            path_mode="all_shortest",
        )
        try:
            start_node_id = local_backend.graph.find_node_id(
                task_spec.start_page_title,
            )
            if start_node_id is None:
                return SolverTaskContext(
                    solver_shortest_path=None,
                    task_execution_annotation=TaskExecutionAnnotation(
                        status=TaskExecutionAnnotationStatus.START_MISSING_IN_SOLVER,
                    ),
                )

            target_node_id = local_backend.graph.find_node_id(
                task_spec.target_page_title,
            )
            if target_node_id is None:
                return SolverTaskContext(
                    solver_shortest_path=None,
                    task_execution_annotation=TaskExecutionAnnotation(
                        status=TaskExecutionAnnotationStatus.TARGET_MISSING_IN_SOLVER,
                    ),
                )

            solver_response = await local_backend.find_shortest_path(
                task_spec.start_page_title,
                task_spec.target_page_title,
            )
            if solver_response.path_length < 0 or not solver_response.paths:
                return SolverTaskContext(
                    solver_shortest_path=None,
                    task_execution_annotation=TaskExecutionAnnotation(
                        status=TaskExecutionAnnotationStatus.UNREACHABLE_IN_SOLVER,
                    ),
                )

            return SolverTaskContext(
                solver_shortest_path=_solver_shortest_path_from_solver_response(
                    solver_response=solver_response,
                    solver_snapshot_id=solver_snapshot_id,
                ),
                task_execution_annotation=TaskExecutionAnnotation(
                    status=TaskExecutionAnnotationStatus.OK,
                    shortest_path_length=solver_response.path_length,
                ),
                position_solver_facts=PositionSolverFacts.from_solver_response(
                    page_title=task_spec.start_page_title,
                    target_page_title=task_spec.target_page_title,
                    solver_response=solver_response,
                    solver_snapshot_id=solver_snapshot_id,
                ),
            )
        finally:
            await local_backend.shutdown()

    if solver_runtime.backend == SolverBackend.REMOTE:
        if injected_solver_shortest_path_oracle is None:
            raise ValueError(
                "solver backend remote requires a configured solver_shortest_path_oracle",
            )

        solver_shortest_path = (
            await injected_solver_shortest_path_oracle.get_solver_shortest_path(
                task_spec,
            )
        )
        task_execution_annotation = _annotation_from_solver_shortest_path(
            solver_shortest_path,
        )
        return SolverTaskContext(
            solver_shortest_path=solver_shortest_path,
            task_execution_annotation=task_execution_annotation,
        )

    return SolverTaskContext(
        solver_shortest_path=None,
        task_execution_annotation=None,
    )


def _solver_shortest_path_from_solver_response(
    *,
    solver_response: SolverResponse,
    solver_snapshot_id: str | None,
) -> SolverShortestPath:
    return SolverShortestPath(
        page_titles=solver_response.paths[0],
        computed_at=datetime.now(),
        solver_snapshot_id=solver_snapshot_id,
        source=PathSource.LOCAL_GRAPH,
    )


def _annotation_from_solver_shortest_path(
    solver_shortest_path: SolverShortestPath | None,
) -> TaskExecutionAnnotation | None:
    if solver_shortest_path is None:
        return None
    return TaskExecutionAnnotation(
        status=TaskExecutionAnnotationStatus.OK,
        shortest_path_length=solver_shortest_path.hop_count,
    )


def _slugify(value: str) -> str:
    slug = re.sub(
        r"[^0-9A-Za-z_\-]+",
        "_",
        value.strip(),
    )
    slug = re.sub(
        r"_+",
        "_",
        slug,
    )
    return slug.strip("_").lower()


def _default_participant_id(
    model_id: str,
) -> str:
    return f"participant_{_slugify(model_id)}"


def _default_race_id(
    *,
    benchmark_id: str,
    task_id: str,
) -> str:
    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S",
    )
    return f"race_{_slugify(benchmark_id)}_{_slugify(task_id)}_{timestamp}"


def _default_run_id(
    *,
    race_id: str,
    participant_id: str,
) -> str:
    run_suffix = uuid.uuid4().hex[:6]
    return f"run_{_slugify(race_id)}_{_slugify(participant_id)}_{run_suffix}"
