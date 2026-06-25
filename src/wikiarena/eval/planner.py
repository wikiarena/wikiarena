from __future__ import annotations

import re
import unicodedata
from typing import Any

from pydantic import BaseModel

from wikiarena.protocol import BenchmarkSpec
from wikiarena.protocol import HarnessConfig
from wikiarena.protocol import NavigationRules
from wikiarena.protocol import ParticipantSpec
from wikiarena.protocol import ScoringRules
from wikiarena.protocol import TaskSpec
from wikiarena.protocol import stable_sha256


_SECRET_FIELD_FRAGMENTS = (
    "api_key",
    "token",
    "secret",
    "password",
    "credential",
    "auth",
)


class BenchmarkIdentityPlan(BaseModel):
    ruleset_hash: str
    taskset_hash: str
    participant_hashes: dict[str, str]


def plan_benchmark_identity(
    benchmark_spec: BenchmarkSpec,
    *,
    protocol_version: str,
) -> BenchmarkIdentityPlan:
    return BenchmarkIdentityPlan(
        ruleset_hash=build_ruleset_hash(
            protocol_version=protocol_version,
            navigation_rules=benchmark_spec.rules.navigation,
            harness_config=benchmark_spec.rules.harness,
            scoring_rules=benchmark_spec.rules.scoring,
        ),
        taskset_hash=build_taskset_hash(
            benchmark_spec.tasks,
        ),
        participant_hashes={
            participant.participant_id: build_participant_hash(
                participant,
            )
            for participant in benchmark_spec.participants
        },
    )


def build_ruleset_hash(
    *,
    protocol_version: str,
    navigation_rules: NavigationRules,
    harness_config: HarnessConfig,
    scoring_rules: ScoringRules,
) -> str:
    return stable_sha256(
        {
            "protocol_version": protocol_version,
            "navigation_rules": navigation_rules.model_dump(mode="json"),
            "harness_config": harness_config.model_dump(mode="json"),
            "scoring_rules": scoring_rules.model_dump(mode="json"),
        },
    )


def build_taskset_hash(
    tasks: list[TaskSpec],
) -> str:
    canonical_task_ids: list[str] = []
    for task in tasks:
        if task.task_id is None:
            raise ValueError(
                "task_id cannot be null when building taskset_hash",
            )
        canonical_task_ids.append(
            task.task_id,
        )

    return stable_sha256(
        {
            "task_ids": canonical_task_ids,
        },
    )


def build_participant_hash(
    participant: ParticipantSpec,
) -> str:
    sanitized_settings = _sanitize_settings(
        participant.driver_config.settings,
    )
    return stable_sha256(
        {
            "participant_kind": participant.participant_kind.value,
            "provider": participant.driver_config.provider,
            "model": participant.driver_config.model,
            "settings": sanitized_settings,
        },
    )


def build_race_id(
    *,
    benchmark_id: str,
    task_id: str,
    task_index: int,
    start_page_title: str | None = None,
    target_page_title: str | None = None,
) -> str:
    if start_page_title is not None and target_page_title is not None:
        language = task_id.split(
            "__",
            1,
        )[0] or "task"
        return (
            f"race_{_slugify(benchmark_id)}_{task_index:04d}_{_slugify(language)}_"
            f"{_slugify(start_page_title)}__{_slugify(target_page_title)}"
        )
    return f"race_{_slugify(benchmark_id)}_{task_index:04d}_{_slugify(task_id)}"


def build_run_id(
    *,
    race_id: str,
    participant_id: str,
) -> str:
    match = re.match(
        r"^race_(?P<benchmark>.+?)_(?P<task_index>\d{4})_.+$",
        race_id,
    )
    if match is not None:
        return (
            f"run_{match.group('benchmark')}_{match.group('task_index')}_"
            f"{_slugify(participant_id)}"
        )
    return f"run_{_slugify(race_id)}_{_slugify(participant_id)}"


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize(
        "NFKD",
        value,
    )
    normalized = normalized.encode(
        "ascii",
        "ignore",
    ).decode(
        "ascii",
    )
    slug = re.sub(
        r"[^0-9A-Za-z]+",
        "_",
        normalized.strip(),
    )
    slug = re.sub(
        r"_+",
        "_",
        slug,
    )
    return slug.strip("_").lower()


def _sanitize_settings(
    value: Any,
) -> Any:
    if isinstance(
        value,
        dict,
    ):
        sanitized_dict = {}
        for key, nested_value in value.items():
            normalized_key = key.lower().strip()
            if any(fragment in normalized_key for fragment in _SECRET_FIELD_FRAGMENTS):
                continue
            sanitized_dict[key] = _sanitize_settings(
                nested_value,
            )
        return sanitized_dict

    if isinstance(
        value,
        list,
    ):
        return [
            _sanitize_settings(
                item,
            )
            for item in value
        ]

    return value
