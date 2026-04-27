from __future__ import annotations

import json
from pathlib import Path

from wikiarena.core import RunExecutionArtifact
from wikiarena.protocol.events import EventEnvelope
from wikiarena.protocol.results import RunResult
from wikiarena.server.race_models import RaceMetadata, StoredRaceEvent


class LocalRaceArtifactStore:
    def __init__(self, artifact_dir: str | Path):
        self.artifact_dir = Path(artifact_dir)
        self.races_dir = self.artifact_dir / "races"

    def race_dir(self, race_id: str) -> Path:
        return self.races_dir / race_id

    def write_metadata(self, metadata: RaceMetadata) -> None:
        race_dir = self.race_dir(metadata.race_id)
        race_dir.mkdir(parents=True, exist_ok=True)
        _write_json(race_dir / "race.json", metadata.model_dump(mode="json"))

    def read_metadata(self, race_id: str) -> RaceMetadata | None:
        path = self.race_dir(race_id) / "race.json"
        if not path.exists():
            return None
        return RaceMetadata.model_validate_json(path.read_text(encoding="utf-8"))

    def append_event(self, race_id: str, event: EventEnvelope) -> StoredRaceEvent:
        race_dir = self.race_dir(race_id)
        race_dir.mkdir(parents=True, exist_ok=True)
        stored_event = StoredRaceEvent(
            stream_sequence=self.latest_stream_sequence(race_id) + 1,
            event=event,
        )
        with (race_dir / "events.jsonl").open("a", encoding="utf-8") as file_handle:
            file_handle.write(
                json.dumps(stored_event.model_dump(mode="json"), ensure_ascii=False)
            )
            file_handle.write("\n")
        return stored_event

    def append_run_event(
        self,
        race_id: str,
        run_id: str,
        event: EventEnvelope,
    ) -> StoredRaceEvent:
        runs_dir = self.race_dir(race_id) / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        stored_event = StoredRaceEvent(
            stream_sequence=self.latest_run_stream_sequence(race_id, run_id) + 1,
            event=event,
        )
        with (runs_dir / f"{run_id}.events.jsonl").open(
            "a",
            encoding="utf-8",
        ) as file_handle:
            file_handle.write(
                json.dumps(stored_event.model_dump(mode="json"), ensure_ascii=False)
            )
            file_handle.write("\n")
        return stored_event

    def read_events(
        self,
        race_id: str,
        *,
        after_stream_sequence: int = 0,
    ) -> list[StoredRaceEvent]:
        path = self.race_dir(race_id) / "events.jsonl"
        if not path.exists():
            return []
        events: list[StoredRaceEvent] = []
        with path.open("r", encoding="utf-8") as file_handle:
            for line_number, line in enumerate(file_handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    stored_event = StoredRaceEvent.model_validate_json(stripped)
                except ValueError as error:
                    raise ValueError(
                        f"invalid race event JSON on line {line_number} of {path}"
                    ) from error
                if stored_event.stream_sequence > after_stream_sequence:
                    events.append(stored_event)
        return events

    def read_run_events(
        self,
        race_id: str,
        run_id: str,
        *,
        after_stream_sequence: int = 0,
    ) -> list[StoredRaceEvent]:
        path = self.race_dir(race_id) / "runs" / f"{run_id}.events.jsonl"
        return _read_stored_events(
            path,
            after_stream_sequence=after_stream_sequence,
        )

    def latest_stream_sequence(self, race_id: str) -> int:
        events = self.read_events(race_id)
        if not events:
            return 0
        return events[-1].stream_sequence

    def latest_run_stream_sequence(self, race_id: str, run_id: str) -> int:
        events = self.read_run_events(race_id, run_id)
        if not events:
            return 0
        return events[-1].stream_sequence

    def write_run_result(self, run_result: RunResult) -> None:
        race_dir = self.race_dir(run_result.race_id)
        runs_dir = race_dir / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            runs_dir / f"{run_result.run_id}.result.json",
            run_result.model_dump(mode="json"),
        )

    def write_artifact(self, artifact: RunExecutionArtifact) -> None:
        self.write_run_result(artifact.run_result)

    def read_run_results(self, race_id: str) -> list[RunResult]:
        runs_dir = self.race_dir(race_id) / "runs"
        if not runs_dir.exists():
            return []
        return [
            RunResult.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(runs_dir.glob("*.result.json"))
        ]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _read_stored_events(
    path: Path,
    *,
    after_stream_sequence: int = 0,
) -> list[StoredRaceEvent]:
    if not path.exists():
        return []
    events: list[StoredRaceEvent] = []
    with path.open("r", encoding="utf-8") as file_handle:
        for line_number, line in enumerate(file_handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                stored_event = StoredRaceEvent.model_validate_json(stripped)
            except ValueError as error:
                raise ValueError(
                    f"invalid race event JSON on line {line_number} of {path}"
                ) from error
            if stored_event.stream_sequence > after_stream_sequence:
                events.append(stored_event)
    return events
