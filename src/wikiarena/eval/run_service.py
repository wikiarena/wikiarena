from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Callable, Protocol

from pydantic import BaseModel, Field

from wikiarena.adapters.participants import ProviderParticipant
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
    NavigationRules,
    ParticipantKind,
    ParticipantSpec,
    RunSpec,
    ScoringRules,
    SolverMode,
    TaskSpec,
    WikiBackend,
)
from wikiarena.protocol.specs import ReferencePath
from wikiarena.providers import create_provider_client
from wikiarena.solver.binary import MappedBinarySolverGraph
from wikiarena.wiki_runtime import (
    WikiRuntimeConfig,
    resolve_graph_file_path,
    resolve_graph_snapshot_id,
)
from wikiarena.wikipedia import LiveWikiService

ParticipantFactory = Callable[[ParticipantSpec], ParticipantDriver]
WikiNavigatorFactory = Callable[["RunPlan"], WikiNavigator]


class ReferencePathOracle(Protocol):
    async def get_reference_paths(
        self,
        task: TaskSpec,
    ) -> list[ReferencePath]: ...


class RunRequest(BaseModel):
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

    solver_mode: SolverMode = SolverMode.NONE
    wiki_runtime: WikiRuntimeConfig = Field(
        default_factory=WikiRuntimeConfig,
    )
    wiki_snapshot_id: str | None = None


class RunPlan(BaseModel):
    task_spec: TaskSpec
    participant_spec: ParticipantSpec
    run_spec: RunSpec
    harness_config: HarnessConfig
    scoring_rules: ScoringRules
    ruleset_hash: str | None = None
    taskset_hash: str | None = None
    participant_hash: str | None = None
    solver_mode: SolverMode = SolverMode.NONE
    wiki_runtime: WikiRuntimeConfig = Field(
        default_factory=WikiRuntimeConfig,
    )
    wiki_snapshot_id: str | None = None


class RunService:
    def __init__(
        self,
        *,
        participant_factory: ParticipantFactory | None = None,
        wiki_navigator_factory: WikiNavigatorFactory | None = None,
        reference_path_oracle: ReferencePathOracle | None = None,
        run_executor: RunExecutor | None = None,
    ):
        self.participant_factory = participant_factory or _default_participant_factory
        self.wiki_navigator_factory = (
            wiki_navigator_factory or _default_wiki_navigator_factory
        )
        self.reference_path_oracle = reference_path_oracle
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

        resolved_wiki_snapshot_id = request.wiki_snapshot_id
        resolved_wiki_runtime = request.wiki_runtime
        if request.wiki_runtime.backend == WikiBackend.GRAPH:
            resolved_graph_path = resolve_graph_file_path(
                request.wiki_runtime.graph_path,
            )
            resolved_wiki_runtime = request.wiki_runtime.model_copy(
                update={
                    "graph_path": resolved_graph_path,
                },
            )
            resolved_wiki_snapshot_id = resolve_graph_snapshot_id(
                resolved_graph_path,
                resolved_wiki_snapshot_id,
            )

        if (
            self.reference_path_oracle is not None
            and request.solver_mode != SolverMode.NONE
        ):
            reference_paths = await self.reference_path_oracle.get_reference_paths(
                task_spec,
            )
            task_spec = task_spec.model_copy(
                update={
                    "reference_paths": reference_paths,
                },
            )

            if resolved_wiki_snapshot_id is None:
                snapshot_ids = {
                    reference_path.valid_for_snapshot_id
                    for reference_path in reference_paths
                    if reference_path.valid_for_snapshot_id
                }
                if len(snapshot_ids) == 1:
                    resolved_wiki_snapshot_id = next(
                        iter(snapshot_ids),
                    )

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
            solver_mode=request.solver_mode,
            wiki_runtime=resolved_wiki_runtime,
            wiki_snapshot_id=resolved_wiki_snapshot_id,
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
            solver_mode=run_plan.solver_mode,
            wiki_backend=run_plan.wiki_runtime.backend,
            wiki_snapshot_id=run_plan.wiki_snapshot_id,
            event_sink=event_sink,
        )

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
    if run_plan.wiki_runtime.backend == WikiBackend.GRAPH:
        graph_path = resolve_graph_file_path(
            run_plan.wiki_runtime.graph_path,
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
