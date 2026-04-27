from __future__ import annotations

from wikiarena.protocol.enums import RunEventType
from wikiarena.protocol.events import EventEnvelope
from wikiarena.server.race_models import RaceMetadata, RaceParticipantSummary
from wikiarena.server.race_store import LocalRaceArtifactStore


def test_race_store_persists_metadata_and_ordered_events(tmp_path) -> None:
    store = LocalRaceArtifactStore(tmp_path)
    metadata = RaceMetadata(
        race_id="race_1",
        benchmark_id="benchmark_1",
        task_id="task_1",
        start_title="Apple",
        target_title="Fruit",
        participants=[
            RaceParticipantSummary(
                participant_id="participant_1",
                display_name="GPT",
                provider="codex",
                model="gpt-5.4",
                run_id="race_1__participant_1",
            )
        ],
    )

    store.write_metadata(metadata)
    first_event = _event("race_1__participant_1", 1, RunEventType.RUN_STARTED)
    second_event = _event("race_1__participant_1", 2, RunEventType.MOVE_COMMITTED)

    stored_first = store.append_event("race_1", first_event)
    stored_second = store.append_event("race_1", second_event)
    stored_run_first = store.append_run_event(
        "race_1", "race_1__participant_1", first_event
    )
    stored_run_second = store.append_run_event(
        "race_1",
        "race_1__participant_1",
        second_event,
    )

    assert store.read_metadata("race_1") == metadata
    assert stored_first.stream_sequence == 1
    assert stored_second.stream_sequence == 2
    assert stored_run_first.stream_sequence == 1
    assert stored_run_second.stream_sequence == 2
    assert store.latest_stream_sequence("race_1") == 2
    assert store.latest_run_stream_sequence("race_1", "race_1__participant_1") == 2
    assert store.read_events("race_1", after_stream_sequence=1) == [stored_second]
    assert store.read_run_events(
        "race_1",
        "race_1__participant_1",
        after_stream_sequence=1,
    ) == [stored_run_second]


def _event(run_id: str, sequence: int, event_type: RunEventType) -> EventEnvelope:
    return EventEnvelope(
        event_id=f"{run_id}:{sequence}",
        event_type=event_type,
        benchmark_id="benchmark_1",
        race_id="race_1",
        run_id=run_id,
        sequence=sequence,
        payload={},
    )
