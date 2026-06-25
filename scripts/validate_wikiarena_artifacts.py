#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from wikiarena.protocol.enums import RunEventType, TerminalOutcome, TerminationReason
from wikiarena.protocol.results import RunResult, StepAttemptRecord
from wikiarena.server.race_models import RaceMetadata, StoredRaceEvent
from wikiarena.solver.models import PositionSolverFacts


class RunStartedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_id: str
    task_id: str
    harness_id: str


class PositionSolverFactsRecordedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_index: int = Field(ge=0)
    move_index: int = Field(ge=0)
    solver_facts: PositionSolverFacts


class MoveCommittedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    move_index: int = Field(ge=1)
    from_page_title: str
    to_page_title: str
    step_index: int = Field(ge=1)


class RunTerminatedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terminal_outcome: TerminalOutcome
    termination_reason: TerminationReason
    total_step_attempts: int = Field(ge=0)
    total_committed_moves: int = Field(ge=0)
    total_invalid_attempts: int = Field(ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0.0)
    ranking_eligible: bool
    total_model_tokens: int = Field(ge=0)


class LeaderboardParticipant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participantId: str
    displayName: str
    runs: int = Field(ge=0)
    rankingEligibleRuns: int = Field(ge=0)
    successes: int = Field(ge=0)
    modelFailures: int = Field(ge=0)
    systemFailures: int = Field(ge=0)
    totalEstimatedCostUsd: float = Field(ge=0.0)
    estimatedCostUsdPerSuccess: float | None = Field(default=None, ge=0.0)
    totalStepAttempts: int = Field(ge=0)
    totalInvalidAttempts: int = Field(ge=0)
    stepErrorRate: float | None = Field(default=None, ge=0.0)
    totalModelResponseTimeMs: float | None = Field(default=None, ge=0.0)
    pairwiseWins: int = Field(ge=0)
    pairwiseLosses: int = Field(ge=0)
    pairwiseDraws: int = Field(ge=0)
    pairwiseSkipped: int = Field(ge=0)
    elo: float | None = None


class LeaderboardData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    benchmarkId: str
    snapshotId: str
    sourcePath: str
    artifactDir: str
    generatedFromRuns: int = Field(ge=0)
    rankedFromRuns: int = Field(ge=0)
    totalRaces: int = Field(ge=0)
    excludedParticipants: list[str]
    scoringPolicy: dict[str, str]
    pairwiseComparisons: int = Field(ge=0)
    pairwiseSkippedComparisons: int = Field(ge=0)
    rulesetHashes: list[str]
    tasksetHashes: list[str]
    participants: list[LeaderboardParticipant]


class ReplayParticipant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participantId: str
    displayName: str
    runId: str
    terminalOutcome: str
    committedMoves: int = Field(ge=0)
    scoreMoves: int = Field(ge=0)
    scoreLabel: str
    invalidAttempts: int = Field(ge=0)
    estimatedCostUsd: float = Field(ge=0.0)
    elo: float | None = None


class ReplayRace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raceId: str
    taskId: str
    startTitle: str
    targetTitle: str
    optimalMoves: int | None = Field(default=None, ge=0)
    winnerParticipantId: str | None = None
    victoryMarginMoves: int | None = None
    participants: list[ReplayParticipant]


class ReplayManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sourcePath: str
    artifactDir: str
    generatedFromRuns: int = Field(ge=0)
    rankedFromRuns: int = Field(ge=0)
    excludedParticipants: list[str]
    scoringPolicy: dict[str, str]
    totalRaces: int = Field(ge=0)
    races: list[ReplayRace]


class HomePreviewRace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pathLength: int = Field(ge=0)
    paths: list[list[str]]
    startTitle: str
    targetTitle: str


class HomePreviewData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generatedAt: str
    snapshotId: str
    races: list[HomePreviewRace]


class ArtifactValidator:
    def __init__(
        self,
        *,
        artifact_dir: Path,
        frontend_data_dir: Path | None,
        expected_benchmark_id: str | None,
        max_errors: int,
    ) -> None:
        self.artifact_dir = artifact_dir
        self.frontend_data_dir = frontend_data_dir
        self.expected_benchmark_id = expected_benchmark_id
        self.max_errors = max_errors
        self.errors: list[str] = []
        self.total_error_count = 0
        self.results_by_run_id: dict[str, dict[str, Any]] = {}
        self.result_token_totals_by_run_id: dict[str, int] = {}
        self.run_results_by_race_id: dict[str, list[RunResult]] = defaultdict(list)
        self.race_ids: set[str] = set()
        self.run_ids: set[str] = set()
        self.race_dir_ids: set[str] = set()
        self.run_file_ids: set[str] = set()
        self.event_ids_by_race_id: dict[str, set[str]] = defaultdict(set)
        self.event_ids_by_run_id: dict[str, set[str]] = defaultdict(set)
        self.event_type_counts: Counter[str] = Counter()

    def validate(self) -> dict[str, Any]:
        if not self.artifact_dir.exists():
            self._error(self.artifact_dir, "artifact directory does not exist")
            return self._summary()
        if not self.artifact_dir.is_dir():
            self._error(self.artifact_dir, "artifact path is not a directory")
            return self._summary()

        self._validate_results_jsonl()
        self._validate_race_tree()
        self._validate_frontend_data()
        self._validate_global_consistency()
        return self._summary()

    def _validate_results_jsonl(self) -> None:
        path = self.artifact_dir / "results.jsonl"
        rows = self._read_jsonl(path)
        seen_run_ids: set[str] = set()
        for line_number, payload in rows:
            path_label = f"{path}:{line_number}"
            run_result = self._validate_model(RunResult, payload, path_label)
            if run_result is None:
                continue
            if run_result.run_id in seen_run_ids:
                self._error(path_label, f"duplicate run_id {run_result.run_id!r}")
            seen_run_ids.add(run_result.run_id)
            self.results_by_run_id[run_result.run_id] = payload
            self.result_token_totals_by_run_id[run_result.run_id] = (
                _run_result_total_model_tokens(payload)
            )
            self.run_results_by_race_id[run_result.race_id].append(run_result)
            self.race_ids.add(run_result.race_id)
            self.run_ids.add(run_result.run_id)
            self._validate_run_result_raw_invariants(payload, path_label)
            if self.expected_benchmark_id is not None:
                self._expect_equal(
                    path_label,
                    "benchmark_id",
                    run_result.benchmark_id,
                    self.expected_benchmark_id,
                )

    def _validate_race_tree(self) -> None:
        races_dir = self.artifact_dir / "races"
        if not races_dir.exists():
            self._error(races_dir, "races directory does not exist")
            return
        if not races_dir.is_dir():
            self._error(races_dir, "races path is not a directory")
            return

        for race_dir in sorted(path for path in races_dir.iterdir() if path.is_dir()):
            self._validate_race_dir(race_dir)

    def _validate_race_dir(self, race_dir: Path) -> None:
        race_id = race_dir.name
        self.race_dir_ids.add(race_id)

        metadata_payload = self._read_json(race_dir / "race.json")
        metadata = self._validate_model(RaceMetadata, metadata_payload, race_dir / "race.json")
        if metadata is None:
            return

        self._expect_equal(race_dir / "race.json", "race_id", metadata.race_id, race_id)
        if self.expected_benchmark_id is not None:
            self._expect_equal(
                race_dir / "race.json",
                "benchmark_id",
                metadata.benchmark_id,
                self.expected_benchmark_id,
            )

        participant_run_ids = {participant.run_id for participant in metadata.participants}
        if len(participant_run_ids) != len(metadata.participants):
            self._error(race_dir / "race.json", "duplicate participant run_id values")

        run_result_ids = {
            run_result.run_id for run_result in self.run_results_by_race_id.get(race_id, [])
        }
        missing_results = sorted(participant_run_ids - run_result_ids)
        extra_results = sorted(run_result_ids - participant_run_ids)
        if missing_results:
            self._error(
                race_dir / "race.json",
                f"metadata participants missing from results.jsonl: {missing_results[:5]}",
            )
        if extra_results:
            self._error(
                self.artifact_dir / "results.jsonl",
                f"results.jsonl contains runs not listed in metadata for {race_id}: {extra_results[:5]}",
            )

        race_events = self._validate_event_file(
            race_dir / "events.jsonl",
            expected_race_id=race_id,
            expected_run_id=None,
            expected_participant_run_ids=participant_run_ids,
        )
        self.event_ids_by_race_id[race_id].update(
            stored_event.event.event_id for stored_event in race_events
        )

        runs_dir = race_dir / "runs"
        if not runs_dir.exists():
            self._error(runs_dir, "runs directory does not exist")
            return
        if not runs_dir.is_dir():
            self._error(runs_dir, "runs path is not a directory")
            return

        for participant in metadata.participants:
            self._validate_run_artifacts(
                race_dir=race_dir,
                expected_race_id=race_id,
                expected_run_id=participant.run_id,
                expected_participant_id=participant.participant_id,
            )

    def _validate_run_artifacts(
        self,
        *,
        race_dir: Path,
        expected_race_id: str,
        expected_run_id: str,
        expected_participant_id: str,
    ) -> None:
        runs_dir = race_dir / "runs"
        result_path = runs_dir / f"{expected_run_id}.result.json"
        event_path = runs_dir / f"{expected_run_id}.events.jsonl"

        result_payload = self._read_json(result_path)
        run_result = self._validate_model(RunResult, result_payload, result_path)
        if run_result is not None:
            self.run_file_ids.add(run_result.run_id)
            self._expect_equal(result_path, "run_id", run_result.run_id, expected_run_id)
            self._expect_equal(result_path, "race_id", run_result.race_id, expected_race_id)
            self._expect_equal(
                result_path,
                "participant_id",
                run_result.participant_id,
                expected_participant_id,
            )
            self._validate_run_result_raw_invariants(result_payload, result_path)
            top_level_payload = self.results_by_run_id.get(run_result.run_id)
            if top_level_payload is None:
                self._error(result_path, "run result file is missing from results.jsonl")
            elif top_level_payload != result_payload:
                self._error(
                    result_path,
                    "run result file differs from results.jsonl payload for same run_id",
                )

        run_events = self._validate_event_file(
            event_path,
            expected_race_id=expected_race_id,
            expected_run_id=expected_run_id,
            expected_participant_run_ids={expected_run_id},
        )
        event_ids = {stored_event.event.event_id for stored_event in run_events}
        self.event_ids_by_run_id[expected_run_id].update(event_ids)

    def _validate_event_file(
        self,
        path: Path,
        *,
        expected_race_id: str,
        expected_run_id: str | None,
        expected_participant_run_ids: set[str],
    ) -> list[StoredRaceEvent]:
        rows = self._read_jsonl(path)
        stored_events: list[StoredRaceEvent] = []
        sequences_by_run_id: dict[str, list[int]] = defaultdict(list)
        event_ids: set[str] = set()

        for expected_stream_sequence, (line_number, payload) in enumerate(rows, start=1):
            path_label = f"{path}:{line_number}"
            stored_event = self._validate_model(StoredRaceEvent, payload, path_label)
            if stored_event is None:
                continue

            stored_events.append(stored_event)
            event = stored_event.event
            self.event_type_counts[event.event_type.value] += 1
            sequences_by_run_id[event.run_id].append(event.sequence)

            self._expect_equal(
                path_label,
                "stream_sequence",
                stored_event.stream_sequence,
                expected_stream_sequence,
            )
            self._expect_equal(path_label, "event.race_id", event.race_id, expected_race_id)
            if expected_run_id is not None:
                self._expect_equal(path_label, "event.run_id", event.run_id, expected_run_id)
            if event.run_id not in expected_participant_run_ids:
                self._error(
                    path_label,
                    f"event.run_id {event.run_id!r} is not a metadata participant run",
                )

            expected_event_id = f"{event.run_id}:{event.sequence}"
            self._expect_equal(path_label, "event.event_id", event.event_id, expected_event_id)
            if event.event_id in event_ids:
                self._error(path_label, f"duplicate event_id {event.event_id!r}")
            event_ids.add(event.event_id)
            self._validate_event_payload(stored_event, path_label)

        for run_id, sequences in sequences_by_run_id.items():
            expected_sequences = list(range(1, len(sequences) + 1))
            if sequences != expected_sequences:
                self._error(
                    path,
                    f"event.sequence values for {run_id!r} are not contiguous from 1",
                )

        return stored_events

    def _validate_event_payload(
        self,
        stored_event: StoredRaceEvent,
        path_label: str,
    ) -> None:
        event = stored_event.event
        payload = event.payload
        if event.event_type == RunEventType.RUN_STARTED:
            model = self._validate_model(RunStartedPayload, payload, path_label)
            if model is not None:
                run_result = self.results_by_run_id.get(event.run_id)
                if run_result is not None:
                    self._expect_equal(
                        path_label,
                        "payload.participant_id",
                        model.participant_id,
                        run_result.get("participant_id"),
                    )
                    self._expect_equal(
                        path_label,
                        "payload.task_id",
                        model.task_id,
                        run_result.get("task_id"),
                    )
            return

        if event.event_type == RunEventType.POSITION_SOLVER_FACTS_RECORDED:
            self._validate_model(PositionSolverFactsRecordedPayload, payload, path_label)
            return

        if event.event_type == RunEventType.STEP_ATTEMPT_RECORDED:
            self._validate_model(StepAttemptRecord, payload, path_label)
            participant_id = self._participant_id_for_run_id(event.run_id)
            self._validate_model_metrics_raw(
                payload,
                path_label,
                participant_id=participant_id,
            )
            return

        if event.event_type == RunEventType.MOVE_COMMITTED:
            self._validate_model(MoveCommittedPayload, payload, path_label)
            return

        if event.event_type == RunEventType.RUN_TERMINATED:
            model = self._validate_model(RunTerminatedPayload, payload, path_label)
            if model is not None:
                expected_tokens = self.result_token_totals_by_run_id.get(event.run_id)
                if expected_tokens is not None:
                    self._expect_equal(
                        path_label,
                        "payload.total_model_tokens",
                        model.total_model_tokens,
                        expected_tokens,
                    )
            return

        self._error(path_label, f"unhandled event type {event.event_type!r}")

    def _validate_frontend_data(self) -> None:
        if self.frontend_data_dir is None:
            return
        if not self.frontend_data_dir.exists():
            self._error(self.frontend_data_dir, "frontend data directory does not exist")
            return

        leaderboard = self._validate_json_file(
            self.frontend_data_dir / "leaderboard.json",
            LeaderboardData,
        )
        if leaderboard is not None:
            self._expect_equal(
                self.frontend_data_dir / "leaderboard.json",
                "generatedFromRuns",
                leaderboard.generatedFromRuns,
                len(self.run_ids),
            )
            self._expect_equal(
                self.frontend_data_dir / "leaderboard.json",
                "totalRaces",
                leaderboard.totalRaces,
                len(self.race_ids),
            )
            if self.expected_benchmark_id is not None:
                self._expect_equal(
                    self.frontend_data_dir / "leaderboard.json",
                    "benchmarkId",
                    leaderboard.benchmarkId,
                    self.expected_benchmark_id,
                )
            self._validate_artifact_dir_reference(
                self.frontend_data_dir / "leaderboard.json",
                leaderboard.artifactDir,
            )

        replay_manifest = self._validate_json_file(
            self.frontend_data_dir / "benchmark-races.json",
            ReplayManifest,
        )
        if replay_manifest is not None:
            self._expect_equal(
                self.frontend_data_dir / "benchmark-races.json",
                "totalRaces",
                replay_manifest.totalRaces,
                len(self.race_ids),
            )
            manifest_race_ids = {race.raceId for race in replay_manifest.races}
            if manifest_race_ids != self.race_ids:
                self._error(
                    self.frontend_data_dir / "benchmark-races.json",
                    "race IDs differ from artifact results.jsonl",
                )
            for race in replay_manifest.races:
                for participant in race.participants:
                    if participant.runId not in self.run_ids:
                        self._error(
                            self.frontend_data_dir / "benchmark-races.json",
                            f"manifest references unknown runId {participant.runId!r}",
                        )
            self._validate_artifact_dir_reference(
                self.frontend_data_dir / "benchmark-races.json",
                replay_manifest.artifactDir,
            )

        home_preview_path = self.frontend_data_dir / "home-preview-races.json"
        if home_preview_path.exists():
            self._validate_json_file(home_preview_path, HomePreviewData)

    def _validate_global_consistency(self) -> None:
        if self.race_dir_ids != self.race_ids:
            missing_dirs = sorted(self.race_ids - self.race_dir_ids)
            extra_dirs = sorted(self.race_dir_ids - self.race_ids)
            if missing_dirs:
                self._error(
                    self.artifact_dir / "races",
                    f"missing race dirs for results.jsonl races: {missing_dirs[:5]}",
                )
            if extra_dirs:
                self._error(
                    self.artifact_dir / "races",
                    f"race dirs not present in results.jsonl: {extra_dirs[:5]}",
                )

        if self.run_file_ids != self.run_ids:
            missing_files = sorted(self.run_ids - self.run_file_ids)
            extra_files = sorted(self.run_file_ids - self.run_ids)
            if missing_files:
                self._error(
                    self.artifact_dir / "races",
                    f"missing run result files for results.jsonl runs: {missing_files[:5]}",
                )
            if extra_files:
                self._error(
                    self.artifact_dir / "races",
                    f"run result files not present in results.jsonl: {extra_files[:5]}",
                )

        for race_id, race_event_ids in self.event_ids_by_race_id.items():
            run_event_ids: set[str] = set()
            for run_result in self.run_results_by_race_id.get(race_id, []):
                run_event_ids.update(self.event_ids_by_run_id.get(run_result.run_id, set()))
            if race_event_ids != run_event_ids:
                missing = sorted(run_event_ids - race_event_ids)
                extra = sorted(race_event_ids - run_event_ids)
                self._error(
                    self.artifact_dir / "races" / race_id / "events.jsonl",
                    "race event stream does not match per-run event streams "
                    f"(missing={missing[:3]}, extra={extra[:3]})",
                )

    def _validate_run_result_raw_invariants(
        self,
        payload: dict[str, Any],
        path_label: str | Path,
    ) -> None:
        step_attempts = payload.get("step_attempts")
        if not isinstance(step_attempts, list):
            return

        committed_count = 0
        invalid_count = 0
        estimated_cost = 0.0
        for index, step_attempt in enumerate(step_attempts, start=1):
            if not isinstance(step_attempt, dict):
                continue
            if step_attempt.get("outcome") == "move_committed":
                committed_count += 1
            else:
                invalid_count += 1
            self._validate_model_metrics_raw(
                step_attempt,
                f"{path_label}:step_attempts[{index - 1}]",
                participant_id=_optional_str(payload.get("participant_id")),
            )
            model_metrics = step_attempt.get("model_metrics")
            if isinstance(model_metrics, dict):
                estimated_cost += float(model_metrics.get("estimated_cost_usd") or 0.0)

        self._expect_equal(
            path_label,
            "total_step_attempts",
            payload.get("total_step_attempts"),
            len(step_attempts),
        )
        self._expect_equal(
            path_label,
            "total_committed_moves",
            payload.get("total_committed_moves"),
            committed_count,
        )
        self._expect_equal(
            path_label,
            "total_invalid_attempts",
            payload.get("total_invalid_attempts"),
            invalid_count,
        )
        if not math.isclose(
            float(payload.get("estimated_cost_usd") or 0.0),
            estimated_cost,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            self._error(
                path_label,
                "estimated_cost_usd does not equal the sum of step model costs",
            )

    def _validate_model_metrics_raw(
        self,
        payload: dict[str, Any],
        path_label: str | Path,
        *,
        participant_id: str | None,
    ) -> None:
        model_metrics = payload.get("model_metrics")
        if model_metrics is None:
            return
        if not isinstance(model_metrics, dict):
            self._error(path_label, "model_metrics is not an object")
            return

        expected_total = _model_metrics_total_tokens(
            model_metrics,
            participant_id=participant_id,
        )
        self._expect_equal(
            path_label,
            "model_metrics.total_tokens",
            model_metrics.get("total_tokens"),
            expected_total,
        )

    def _participant_id_for_run_id(self, run_id: str) -> str | None:
        run_result = self.results_by_run_id.get(run_id)
        if run_result is None:
            return None
        return _optional_str(run_result.get("participant_id"))

    def _validate_artifact_dir_reference(
        self,
        path_label: str | Path,
        artifact_dir_value: str,
    ) -> None:
        referenced = Path(artifact_dir_value)
        if not referenced.is_absolute():
            referenced = Path.cwd() / referenced
        if referenced.resolve() != self.artifact_dir.resolve():
            self._error(
                path_label,
                f"artifactDir {artifact_dir_value!r} does not resolve to {self.artifact_dir}",
            )

    def _validate_json_file(
        self,
        path: Path,
        model_type: type[BaseModel],
    ) -> BaseModel | None:
        return self._validate_model(model_type, self._read_json(path), path)

    def _validate_model(
        self,
        model_type: type[BaseModel],
        payload: Any,
        path_label: str | Path,
    ) -> Any | None:
        try:
            return model_type.model_validate(payload)
        except ValidationError as error:
            self._error(
                path_label,
                f"{model_type.__name__} validation failed: "
                f"{_format_validation_error(error)}",
            )
            return None

    def _read_json(self, path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self._error(path, "file does not exist")
        except json.JSONDecodeError as error:
            self._error(path, f"invalid JSON: {error}")
        return None

    def _read_jsonl(self, path: Path) -> list[tuple[int, dict[str, Any]]]:
        rows: list[tuple[int, dict[str, Any]]] = []
        try:
            with path.open("r", encoding="utf-8") as file_handle:
                for line_number, line in enumerate(file_handle, start=1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        payload = json.loads(stripped)
                    except json.JSONDecodeError as error:
                        self._error(f"{path}:{line_number}", f"invalid JSON: {error}")
                        continue
                    if not isinstance(payload, dict):
                        self._error(f"{path}:{line_number}", "line is not a JSON object")
                        continue
                    rows.append((line_number, payload))
        except FileNotFoundError:
            self._error(path, "file does not exist")
        return rows

    def _expect_equal(
        self,
        path_label: str | Path,
        field_name: str,
        actual: Any,
        expected: Any,
    ) -> None:
        if actual != expected:
            self._error(
                path_label,
                f"{field_name} mismatch: expected {expected!r}, got {actual!r}",
            )

    def _error(self, path_label: str | Path, message: str) -> None:
        self.total_error_count += 1
        if len(self.errors) >= self.max_errors:
            return
        self.errors.append(f"{path_label}: {message}")

    def _summary(self) -> dict[str, Any]:
        return {
            "artifactDir": str(self.artifact_dir),
            "frontendDataDir": (
                str(self.frontend_data_dir) if self.frontend_data_dir is not None else None
            ),
            "valid": self.total_error_count == 0,
            "errorCount": self.total_error_count,
            "reportedErrors": self.errors,
            "counts": {
                "racesInResults": len(self.race_ids),
                "raceDirs": len(self.race_dir_ids),
                "runsInResults": len(self.run_ids),
                "runResultFiles": len(self.run_file_ids),
                "uniqueRaceStreamEvents": sum(
                    len(event_ids) for event_ids in self.event_ids_by_race_id.values()
                ),
                "uniqueRunStreamEvents": sum(
                    len(event_ids) for event_ids in self.event_ids_by_run_id.values()
                ),
                "storedEventRowsByType": dict(sorted(self.event_type_counts.items())),
            },
        }


def _model_metrics_total_tokens(
    model_metrics: dict[str, Any],
    *,
    participant_id: str | None,
) -> int:
    base_tokens = int(model_metrics.get("input_tokens") or 0) + int(
        model_metrics.get("output_tokens") or 0,
    )
    cache_tokens = int(model_metrics.get("cache_creation_input_tokens") or 0) + int(
        model_metrics.get("cache_read_input_tokens") or 0,
    )
    if _uses_additive_cache_token_totals(participant_id):
        return base_tokens + cache_tokens
    return base_tokens


def _uses_additive_cache_token_totals(participant_id: str | None) -> bool:
    if participant_id is None:
        return False
    normalized = participant_id.casefold()
    return "claude" in normalized or "anthropic" in normalized


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _format_validation_error(error: ValidationError) -> str:
    first_error = error.errors()[0]
    location = ".".join(str(part) for part in first_error.get("loc", ()))
    message = first_error.get("msg", "validation failed")
    if location:
        return f"{location}: {message}"
    return str(message)


def _run_result_total_model_tokens(payload: dict[str, Any]) -> int:
    total = 0
    step_attempts = payload.get("step_attempts")
    if not isinstance(step_attempts, list):
        return total
    for step_attempt in step_attempts:
        if not isinstance(step_attempt, dict):
            continue
        model_metrics = step_attempt.get("model_metrics")
        if not isinstance(model_metrics, dict):
            continue
        total += int(model_metrics.get("total_tokens") or 0)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate WikiArena benchmark artifact shape and cross-file consistency.",
    )
    parser.add_argument(
        "artifact_dir",
        type=Path,
        help="Artifact directory containing results.jsonl and races/.",
    )
    parser.add_argument(
        "--frontend-data-dir",
        type=Path,
        default=None,
        help="Optional frontend public data directory to validate alongside artifacts.",
    )
    parser.add_argument(
        "--expected-benchmark-id",
        default=None,
        help="Optional benchmark_id expected in run and race artifacts.",
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=50,
        help="Maximum number of validation errors to include in the JSON report.",
    )
    args = parser.parse_args()

    validator = ArtifactValidator(
        artifact_dir=args.artifact_dir,
        frontend_data_dir=args.frontend_data_dir,
        expected_benchmark_id=args.expected_benchmark_id,
        max_errors=max(args.max_errors, 1),
    )
    summary = validator.validate()
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
