from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime
from pathlib import Path

from wikiarena.eval.run_service import RunRequest, RunService
from wikiarena.protocol import HarnessConfig, NavigationRules, ScoringRules, TaskSpec
from wikiarena.protocol.enums import NavigationBackend, SolverBackend
from wikiarena.server.config import ServerConfig
from wikiarena.server.race_hub import RaceStreamHub
from wikiarena.server.race_models import (
    CreateRaceRequest,
    RaceMetadata,
    RaceParticipantRequest,
    RaceParticipantSummary,
    RaceStateResponse,
)
from wikiarena.server.race_store import LocalRaceArtifactStore
from wikiarena.solver_runtime import SolverRuntimeConfig
from wikiarena.wiki_runtime import NavigationRuntimeConfig, resolve_graph_file_path


class RaceManager:
    def __init__(
        self,
        *,
        config: ServerConfig,
        store: LocalRaceArtifactStore | None = None,
        stream_hub: RaceStreamHub | None = None,
        run_service: RunService | None = None,
    ) -> None:
        self.config = config
        self.store = store or LocalRaceArtifactStore(config.artifact_dir)
        from wikiarena.server.race_hub import race_stream_hub

        self.stream_hub = stream_hub or race_stream_hub
        self.run_service = run_service or RunService()
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._event_lock = asyncio.Lock()

    async def create_race(self, request: CreateRaceRequest) -> RaceMetadata:
        task_spec = TaskSpec(
            start_page_title=request.start_title,
            target_page_title=request.target_title,
        )
        if task_spec.task_id is None:
            raise ValueError("task_id cannot be null after TaskSpec validation")

        race_id = _make_race_id(
            task_id=task_spec.task_id,
        )
        participants = [
            _build_participant_summary(
                race_id=race_id,
                participant_index=participant_index,
                participant_request=participant_request,
            )
            for participant_index, participant_request in enumerate(
                request.participants,
                start=1,
            )
        ]
        metadata = RaceMetadata(
            race_id=race_id,
            benchmark_id=request.benchmark_id,
            task_id=task_spec.task_id,
            start_title=request.start_title,
            target_title=request.target_title,
            participants=participants,
            status="pending",
        )
        self.store.write_metadata(metadata)

        task = asyncio.create_task(
            self._execute_race(
                request=request,
                metadata=metadata,
            )
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return metadata

    def get_race_state(self, race_id: str) -> RaceStateResponse | None:
        metadata = self.store.read_metadata(race_id)
        if metadata is None:
            return None
        return RaceStateResponse(
            metadata=metadata,
            latest_stream_sequence=self.store.latest_stream_sequence(race_id),
            events=self.store.read_events(race_id),
            run_results=self.store.read_run_results(race_id),
        )

    async def _execute_race(
        self,
        *,
        request: CreateRaceRequest,
        metadata: RaceMetadata,
    ) -> None:
        metadata = metadata.model_copy(
            update={
                "status": "running",
                "started_at": datetime.now(),
            }
        )
        self.store.write_metadata(metadata)

        try:
            navigation_runtime, solver_runtime = _resolve_runtime_configs(
                request=request,
                configured_graph_path=self.config.graph_path,
            )
            run_tasks = [
                asyncio.create_task(
                    self._execute_run(
                        request=request,
                        metadata=metadata,
                        participant=participant,
                        navigation_runtime=navigation_runtime,
                        solver_runtime=solver_runtime,
                    )
                )
                for participant in metadata.participants
            ]
            await asyncio.gather(*run_tasks)
            metadata = metadata.model_copy(
                update={
                    "status": "completed",
                    "ended_at": datetime.now(),
                }
            )
        except Exception as error:
            metadata = metadata.model_copy(
                update={
                    "status": "failed",
                    "ended_at": datetime.now(),
                    "error_message": str(error),
                }
            )
        finally:
            self.store.write_metadata(metadata)

    async def _execute_run(
        self,
        *,
        request: CreateRaceRequest,
        metadata: RaceMetadata,
        participant: RaceParticipantSummary,
        navigation_runtime: NavigationRuntimeConfig,
        solver_runtime: SolverRuntimeConfig,
    ) -> None:
        run_request = RunRequest(
            model_id=participant.model,
            provider=participant.provider,
            start_page_title=request.start_title,
            target_page_title=request.target_title,
            participant_id=participant.participant_id,
            participant_display_name=participant.display_name,
            model_settings=_settings_for_participant(
                request.participants,
                participant.participant_id,
            ),
            benchmark_id=metadata.benchmark_id,
            race_id=metadata.race_id,
            run_id=participant.run_id,
            navigation_rules=NavigationRules(max_moves=request.max_moves),
            scoring_rules=ScoringRules(),
            harness_config=HarnessConfig(harness_id="tool_strict_v1"),
            navigation_runtime=navigation_runtime,
            solver_runtime=solver_runtime,
        )

        async def event_sink(event):
            async with self._event_lock:
                stored_event = self.store.append_event(metadata.race_id, event)
            await self.stream_hub.broadcast(metadata.race_id, stored_event)

        artifact = await self.run_service.run(
            run_request,
            event_sink=event_sink,
        )
        self.store.write_artifact(artifact)


def _resolve_runtime_configs(
    *,
    request: CreateRaceRequest,
    configured_graph_path: Path | None,
) -> tuple[NavigationRuntimeConfig, SolverRuntimeConfig]:
    graph_path = _resolve_optional_graph_path(configured_graph_path)

    requested_navigation_backend = (
        NavigationBackend(request.navigation_backend) if request.navigation_backend else None
    )
    requested_solver_backend = SolverBackend(request.solver_backend) if request.solver_backend else None

    navigation_backend = requested_navigation_backend or (
        NavigationBackend.GRAPH if graph_path is not None else NavigationBackend.LIVE
    )
    solver_backend = requested_solver_backend or (
        SolverBackend.LOCAL if graph_path is not None else SolverBackend.NONE
    )

    return (
        NavigationRuntimeConfig(
            backend=navigation_backend,
            graph_path=graph_path if navigation_backend == NavigationBackend.GRAPH else None,
        ),
        SolverRuntimeConfig(
            backend=solver_backend,
            graph_path=graph_path if solver_backend == SolverBackend.LOCAL else None,
        ),
    )


def _resolve_optional_graph_path(configured_graph_path: Path | None) -> Path | None:
    try:
        return resolve_graph_file_path(configured_graph_path)
    except FileNotFoundError:
        return None


def _build_participant_summary(
    *,
    race_id: str,
    participant_index: int,
    participant_request: RaceParticipantRequest,
) -> RaceParticipantSummary:
    participant_id = participant_request.participant_id or _slugify(
        participant_request.model,
        fallback=f"participant_{participant_index}",
    )
    return RaceParticipantSummary(
        participant_id=participant_id,
        display_name=participant_request.display_name or participant_request.model,
        provider=participant_request.provider,
        model=participant_request.model,
        run_id=f"{race_id}__{participant_id}",
    )


def _settings_for_participant(
    participants: list[RaceParticipantRequest],
    participant_id: str,
) -> dict:
    for index, participant in enumerate(participants, start=1):
        candidate_id = participant.participant_id or _slugify(
            participant.model,
            fallback=f"participant_{index}",
        )
        if candidate_id == participant_id:
            return participant.settings
    return {}


def _make_race_id(*, task_id: str) -> str:
    return f"race_{_slugify(task_id, fallback='task')}_{uuid.uuid4().hex[:10]}"


def _slugify(value: str, *, fallback: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_]+", "_", value.strip().replace("/", "_"))
    slug = re.sub(r"_+", "_", slug).strip("_").lower()
    return slug or fallback
