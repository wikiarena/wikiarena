#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OLD_BENCHMARK_ID = "wikiarena_v0_official_graph_local_solver_v1"
NEW_BENCHMARK_ID = "wikiarena_v0"


@dataclass(frozen=True)
class RaceMapping:
    old_race_id: str
    new_race_id: str
    index: int


@dataclass(frozen=True)
class RunMapping:
    old_run_id: str
    new_run_id: str
    old_race_id: str
    new_race_id: str
    participant_id: str
    provider: str | None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate original WikiArena v0 artifacts to clean IDs and fixed token totals.",
    )
    parser.add_argument(
        "--input-results",
        type=Path,
        default=Path("dumps/eval_wikiarena_v0_official_results.jsonl"),
    )
    parser.add_argument(
        "--source-artifact-dir",
        type=Path,
        default=Path("artifacts/wikiarena_v0_official"),
    )
    parser.add_argument(
        "--dest-artifact-dir",
        type=Path,
        default=Path("artifacts/wikiarena/v0"),
    )
    parser.add_argument(
        "--old-benchmark-id",
        default=OLD_BENCHMARK_ID,
    )
    parser.add_argument(
        "--new-benchmark-id",
        default=NEW_BENCHMARK_ID,
    )
    parser.add_argument(
        "--overwrite-dest",
        action="store_true",
        help="Delete and recreate the destination directory if it already exists.",
    )
    args = parser.parse_args()

    _prepare_destination(
        source_artifact_dir=args.source_artifact_dir,
        dest_artifact_dir=args.dest_artifact_dir,
        overwrite_dest=args.overwrite_dest,
    )

    run_results = _load_jsonl(args.input_results)
    race_mappings = _build_race_mappings(
        run_results,
        source_artifact_dir=args.source_artifact_dir,
        new_benchmark_id=args.new_benchmark_id,
    )
    run_mappings = _build_run_mappings(
        run_results,
        source_artifact_dir=args.source_artifact_dir,
        race_mappings=race_mappings,
        new_benchmark_id=args.new_benchmark_id,
    )

    args.dest_artifact_dir.mkdir(parents=True)

    migrated_results: list[dict[str, Any]] = []
    token_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "runs": 0,
            "model_calls": 0,
            "old_total_tokens": 0,
            "new_total_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    )
    total_model_tokens_by_new_run_id: dict[str, int] = {}
    migrated_run_results_by_new_run_id: dict[str, dict[str, Any]] = {}

    for run_result in run_results:
        old_run_id = _require_str(run_result, "run_id")
        run_mapping = run_mappings[old_run_id]
        migrated = _migrate_run_result(
            run_result,
            run_mapping=run_mapping,
            new_benchmark_id=args.new_benchmark_id,
            token_stats=token_stats,
        )
        migrated_results.append(migrated)
        migrated_run_results_by_new_run_id[run_mapping.new_run_id] = migrated
        total_model_tokens_by_new_run_id[run_mapping.new_run_id] = (
            _sum_model_total_tokens(migrated)
        )

    _write_jsonl(
        args.dest_artifact_dir / "results.jsonl",
        migrated_results,
    )

    run_mappings_by_old_race_id: dict[str, list[RunMapping]] = defaultdict(list)
    for run_mapping in run_mappings.values():
        run_mappings_by_old_race_id[run_mapping.old_race_id].append(run_mapping)

    for old_race_id, race_mapping in race_mappings.items():
        source_race_dir = args.source_artifact_dir / "races" / old_race_id
        dest_race_dir = args.dest_artifact_dir / "races" / race_mapping.new_race_id
        dest_runs_dir = dest_race_dir / "runs"
        dest_runs_dir.mkdir(parents=True)

        race_run_mappings = run_mappings_by_old_race_id[old_race_id]
        _write_migrated_race_metadata(
            source_race_dir=source_race_dir,
            dest_race_dir=dest_race_dir,
            race_mapping=race_mapping,
            run_mappings=race_run_mappings,
            new_benchmark_id=args.new_benchmark_id,
        )
        _write_migrated_race_events(
            source_race_dir=source_race_dir,
            dest_race_dir=dest_race_dir,
            run_mappings=race_run_mappings,
            race_mappings=race_mappings,
            new_benchmark_id=args.new_benchmark_id,
            total_model_tokens_by_new_run_id=total_model_tokens_by_new_run_id,
        )
        for run_mapping in race_run_mappings:
            _write_json(
                dest_runs_dir / f"{run_mapping.new_run_id}.result.json",
                migrated_run_results_by_new_run_id[run_mapping.new_run_id],
            )
            _write_migrated_run_events(
                source_race_dir=source_race_dir,
                dest_runs_dir=dest_runs_dir,
                run_mapping=run_mapping,
                race_mappings=race_mappings,
                new_benchmark_id=args.new_benchmark_id,
                total_model_tokens_by_new_run_id=total_model_tokens_by_new_run_id,
            )

    _write_json(
        args.dest_artifact_dir / "id_map.json",
        {
            "old_benchmark_id": args.old_benchmark_id,
            "new_benchmark_id": args.new_benchmark_id,
            "races": [
                {
                    "old_race_id": mapping.old_race_id,
                    "new_race_id": mapping.new_race_id,
                    "index": mapping.index,
                }
                for mapping in sorted(
                    race_mappings.values(),
                    key=lambda item: item.index,
                )
            ],
            "runs": [
                {
                    "old_run_id": mapping.old_run_id,
                    "new_run_id": mapping.new_run_id,
                    "old_race_id": mapping.old_race_id,
                    "new_race_id": mapping.new_race_id,
                    "participant_id": mapping.participant_id,
                    "provider": mapping.provider,
                }
                for mapping in sorted(
                    run_mappings.values(),
                    key=lambda item: (item.new_race_id, item.participant_id),
                )
            ],
        },
    )
    _write_json(
        args.dest_artifact_dir / "migration_summary.json",
        {
            "source_results": str(args.input_results),
            "source_artifact_dir": str(args.source_artifact_dir),
            "dest_artifact_dir": str(args.dest_artifact_dir),
            "old_benchmark_id": args.old_benchmark_id,
            "new_benchmark_id": args.new_benchmark_id,
            "run_count": len(migrated_results),
            "race_count": len(race_mappings),
            "token_stats_by_participant": dict(token_stats),
        },
    )

    print(
        json.dumps(
            {
                "dest_artifact_dir": str(args.dest_artifact_dir),
                "run_count": len(migrated_results),
                "race_count": len(race_mappings),
            },
            indent=2,
        ),
    )


def _prepare_destination(
    *,
    source_artifact_dir: Path,
    dest_artifact_dir: Path,
    overwrite_dest: bool,
) -> None:
    source = source_artifact_dir.resolve()
    dest = dest_artifact_dir.resolve()
    if source == dest or _is_relative_to(dest, source) or _is_relative_to(source, dest):
        raise SystemExit(
            f"refusing unsafe source/destination relationship: {source} -> {dest}",
        )
    if dest_artifact_dir.exists():
        if not overwrite_dest:
            raise SystemExit(
                f"destination already exists: {dest_artifact_dir}. "
                "Pass --overwrite-dest to recreate it.",
            )
        shutil.rmtree(dest_artifact_dir)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file_handle:
        for line_number, line in enumerate(file_handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON on line {line_number} of {path}") from error
            if not isinstance(payload, dict):
                raise ValueError(f"line {line_number} of {path} is not an object")
            rows.append(payload)
    return rows


def _build_race_mappings(
    run_results: list[dict[str, Any]],
    *,
    source_artifact_dir: Path,
    new_benchmark_id: str,
) -> dict[str, RaceMapping]:
    old_race_ids = sorted(
        {
            _require_str(run_result, "race_id")
            for run_result in run_results
        },
        key=_race_sort_key,
    )
    mappings: dict[str, RaceMapping] = {}
    used_new_ids: set[str] = set()
    for fallback_index, old_race_id in enumerate(old_race_ids, start=1):
        index = _parse_race_index(old_race_id) or fallback_index
        metadata = _load_json(
            source_artifact_dir / "races" / old_race_id / "race.json",
        )
        task_id = _require_str(metadata, "task_id")
        language = task_id.split("__", 1)[0] or "task"
        new_race_id = (
            f"race_{_slugify(new_benchmark_id)}_{index:04d}_"
            f"{_slugify(language)}_{_slugify_title(_require_str(metadata, 'start_title'))}"
            f"__{_slugify_title(_require_str(metadata, 'target_title'))}"
        )
        if new_race_id in used_new_ids:
            raise ValueError(f"duplicate migrated race id: {new_race_id}")
        used_new_ids.add(new_race_id)
        mappings[old_race_id] = RaceMapping(
            old_race_id=old_race_id,
            new_race_id=new_race_id,
            index=index,
        )
    return mappings


def _build_run_mappings(
    run_results: list[dict[str, Any]],
    *,
    source_artifact_dir: Path,
    race_mappings: dict[str, RaceMapping],
    new_benchmark_id: str,
) -> dict[str, RunMapping]:
    provider_by_old_run_id = _provider_by_old_run_id(
        source_artifact_dir=source_artifact_dir,
        race_mappings=race_mappings,
    )
    mappings: dict[str, RunMapping] = {}
    used_new_ids: set[str] = set()
    for run_result in run_results:
        old_run_id = _require_str(run_result, "run_id")
        old_race_id = _require_str(run_result, "race_id")
        participant_id = _require_str(run_result, "participant_id")
        race_mapping = race_mappings[old_race_id]
        new_run_id = (
            f"run_{_slugify(new_benchmark_id)}_{race_mapping.index:04d}_"
            f"{_slugify(participant_id)}"
        )
        if new_run_id in used_new_ids:
            raise ValueError(f"duplicate migrated run id: {new_run_id}")
        used_new_ids.add(new_run_id)
        mappings[old_run_id] = RunMapping(
            old_run_id=old_run_id,
            new_run_id=new_run_id,
            old_race_id=old_race_id,
            new_race_id=race_mapping.new_race_id,
            participant_id=participant_id,
            provider=provider_by_old_run_id.get(old_run_id),
        )
    return mappings


def _provider_by_old_run_id(
    *,
    source_artifact_dir: Path,
    race_mappings: dict[str, RaceMapping],
) -> dict[str, str]:
    provider_by_run_id: dict[str, str] = {}
    for old_race_id in race_mappings:
        metadata = _load_json(
            source_artifact_dir / "races" / old_race_id / "race.json",
        )
        for participant in metadata.get("participants", []):
            if not isinstance(participant, dict):
                continue
            run_id = participant.get("run_id")
            provider = participant.get("provider")
            if isinstance(run_id, str) and isinstance(provider, str):
                provider_by_run_id[run_id] = provider
    return provider_by_run_id


def _migrate_run_result(
    run_result: dict[str, Any],
    *,
    run_mapping: RunMapping,
    new_benchmark_id: str,
    token_stats: dict[str, dict[str, int]],
) -> dict[str, Any]:
    migrated = copy.deepcopy(run_result)
    migrated["benchmark_id"] = new_benchmark_id
    migrated["race_id"] = run_mapping.new_race_id
    migrated["run_id"] = run_mapping.new_run_id

    participant_id = _require_str(migrated, "participant_id")
    token_stats[participant_id]["runs"] += 1
    for step_attempt in migrated.get("step_attempts", []):
        if not isinstance(step_attempt, dict):
            continue
        model_metrics = step_attempt.get("model_metrics")
        if not isinstance(model_metrics, dict):
            continue
        _migrate_model_metrics(
            model_metrics,
            run_mapping=run_mapping,
            participant_id=participant_id,
            token_stats=token_stats,
        )
    return migrated


def _migrate_model_metrics(
    model_metrics: dict[str, Any],
    *,
    run_mapping: RunMapping,
    participant_id: str,
    token_stats: dict[str, dict[str, int]],
) -> None:
    old_total = _int_value(model_metrics.get("total_tokens"))
    input_tokens = _int_value(model_metrics.get("input_tokens"))
    output_tokens = _int_value(model_metrics.get("output_tokens"))
    cache_creation_input_tokens = _int_value(
        model_metrics.get("cache_creation_input_tokens"),
    )
    cache_read_input_tokens = _int_value(
        model_metrics.get("cache_read_input_tokens"),
    )
    new_total = old_total
    if _uses_anthropic_token_semantics(run_mapping):
        new_total = (
            input_tokens
            + output_tokens
            + cache_creation_input_tokens
            + cache_read_input_tokens
        )
        model_metrics["total_tokens"] = new_total

    token_stats[participant_id]["model_calls"] += 1
    token_stats[participant_id]["old_total_tokens"] += old_total
    token_stats[participant_id]["new_total_tokens"] += new_total
    token_stats[participant_id]["cache_creation_input_tokens"] += (
        cache_creation_input_tokens
    )
    token_stats[participant_id]["cache_read_input_tokens"] += cache_read_input_tokens


def _uses_anthropic_token_semantics(run_mapping: RunMapping) -> bool:
    if run_mapping.provider == "anthropic":
        return True
    return run_mapping.participant_id.startswith("claude_")


def _write_migrated_race_metadata(
    *,
    source_race_dir: Path,
    dest_race_dir: Path,
    race_mapping: RaceMapping,
    run_mappings: list[RunMapping],
    new_benchmark_id: str,
) -> None:
    metadata = _load_json(source_race_dir / "race.json")
    metadata["race_id"] = race_mapping.new_race_id
    metadata["benchmark_id"] = new_benchmark_id
    run_mapping_by_old_run_id = {
        run_mapping.old_run_id: run_mapping for run_mapping in run_mappings
    }
    participants = []
    for participant in metadata.get("participants", []):
        if not isinstance(participant, dict):
            continue
        old_run_id = participant.get("run_id")
        if old_run_id not in run_mapping_by_old_run_id:
            continue
        migrated_participant = copy.deepcopy(participant)
        migrated_participant["run_id"] = run_mapping_by_old_run_id[
            old_run_id
        ].new_run_id
        participants.append(migrated_participant)
    metadata["participants"] = participants
    _write_json(dest_race_dir / "race.json", metadata)


def _write_migrated_race_events(
    *,
    source_race_dir: Path,
    dest_race_dir: Path,
    run_mappings: list[RunMapping],
    race_mappings: dict[str, RaceMapping],
    new_benchmark_id: str,
    total_model_tokens_by_new_run_id: dict[str, int],
) -> None:
    dest_path = dest_race_dir / "events.jsonl"
    migrated_events = []
    for run_mapping in run_mappings:
        source_path = source_race_dir / "runs" / f"{run_mapping.old_run_id}.events.jsonl"
        for payload in _select_final_run_event_segment(_load_jsonl(source_path)):
            migrated = _migrate_stored_event(
                payload,
                run_mappings={run_mapping.old_run_id: run_mapping},
                race_mappings=race_mappings,
                new_benchmark_id=new_benchmark_id,
                total_model_tokens_by_new_run_id=total_model_tokens_by_new_run_id,
            )
            if migrated is not None:
                migrated_events.append(migrated)
    migrated_events.sort(key=_stored_event_sort_key)
    _renumber_stream_sequences(migrated_events)
    _write_jsonl(dest_path, migrated_events)


def _write_migrated_run_events(
    *,
    source_race_dir: Path,
    dest_runs_dir: Path,
    run_mapping: RunMapping,
    race_mappings: dict[str, RaceMapping],
    new_benchmark_id: str,
    total_model_tokens_by_new_run_id: dict[str, int],
) -> None:
    source_path = source_race_dir / "runs" / f"{run_mapping.old_run_id}.events.jsonl"
    dest_path = dest_runs_dir / f"{run_mapping.new_run_id}.events.jsonl"
    migrated_events = []
    for payload in _select_final_run_event_segment(_load_jsonl(source_path)):
        migrated = _migrate_stored_event(
            payload,
            run_mappings={run_mapping.old_run_id: run_mapping},
            race_mappings=race_mappings,
            new_benchmark_id=new_benchmark_id,
            total_model_tokens_by_new_run_id=total_model_tokens_by_new_run_id,
        )
        if migrated is not None:
            migrated_events.append(migrated)
    _renumber_stream_sequences(migrated_events)
    _write_jsonl(dest_path, migrated_events)


def _select_final_run_event_segment(
    stored_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    last_run_started_index = 0
    for index, stored_event in enumerate(stored_events):
        event = stored_event.get("event")
        if not isinstance(event, dict):
            continue
        if event.get("event_type") == "run_started":
            last_run_started_index = index
    return stored_events[last_run_started_index:]


def _migrate_stored_event(
    stored_event: dict[str, Any],
    *,
    run_mappings: dict[str, RunMapping],
    race_mappings: dict[str, RaceMapping],
    new_benchmark_id: str,
    total_model_tokens_by_new_run_id: dict[str, int],
) -> dict[str, Any] | None:
    event = stored_event.get("event")
    if not isinstance(event, dict):
        return None
    old_run_id = event.get("run_id")
    old_race_id = event.get("race_id")
    if not isinstance(old_run_id, str) or old_run_id not in run_mappings:
        return None
    if not isinstance(old_race_id, str) or old_race_id not in race_mappings:
        return None

    run_mapping = run_mappings[old_run_id]
    migrated = copy.deepcopy(stored_event)
    migrated_event = migrated["event"]
    sequence = _int_value(migrated_event.get("sequence"))
    migrated_event["event_id"] = f"{run_mapping.new_run_id}:{sequence}"
    migrated_event["benchmark_id"] = new_benchmark_id
    migrated_event["race_id"] = run_mapping.new_race_id
    migrated_event["run_id"] = run_mapping.new_run_id
    payload = migrated_event.get("payload")
    if isinstance(payload, dict):
        model_metrics = payload.get("model_metrics")
        if isinstance(model_metrics, dict):
            empty_stats: dict[str, dict[str, int]] = defaultdict(
                lambda: {
                    "runs": 0,
                    "model_calls": 0,
                    "old_total_tokens": 0,
                    "new_total_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            )
            _migrate_model_metrics(
                model_metrics,
                run_mapping=run_mapping,
                participant_id=run_mapping.participant_id,
                token_stats=empty_stats,
            )
        if migrated_event.get("event_type") == "run_terminated":
            payload["total_model_tokens"] = total_model_tokens_by_new_run_id.get(
                run_mapping.new_run_id,
                payload.get("total_model_tokens"),
            )
    return migrated


def _renumber_stream_sequences(stored_events: list[dict[str, Any]]) -> None:
    for stream_sequence, stored_event in enumerate(stored_events, start=1):
        stored_event["stream_sequence"] = stream_sequence


def _stored_event_sort_key(stored_event: dict[str, Any]) -> tuple[str, str, int]:
    event = stored_event.get("event")
    if not isinstance(event, dict):
        return ("", "", 0)
    occurred_at = event.get("occurred_at")
    run_id = event.get("run_id")
    sequence = _int_value(event.get("sequence"))
    return (
        occurred_at if isinstance(occurred_at, str) else "",
        run_id if isinstance(run_id, str) else "",
        sequence,
    )


def _sum_model_total_tokens(run_result: dict[str, Any]) -> int:
    total = 0
    for step_attempt in run_result.get("step_attempts", []):
        if not isinstance(step_attempt, dict):
            continue
        model_metrics = step_attempt.get("model_metrics")
        if not isinstance(model_metrics, dict):
            continue
        total += _int_value(model_metrics.get("total_tokens"))
    return total


def _race_sort_key(race_id: str) -> tuple[int, str]:
    return (_parse_race_index(race_id) or 1_000_000, race_id)


def _parse_race_index(race_id: str) -> int | None:
    match = re.search(r"_(\d{4})_", race_id)
    if match is None:
        return None
    return int(match.group(1))


def _slugify_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    return _slugify(normalized)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", value.strip())
    slug = re.sub(r"_+", "_", slug)
    return slug.strip("_").lower()


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing string field {key!r}")
    return value


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, payloads: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_handle:
        for payload in payloads:
            file_handle.write(json.dumps(payload, ensure_ascii=False))
            file_handle.write("\n")


if __name__ == "__main__":
    main()
