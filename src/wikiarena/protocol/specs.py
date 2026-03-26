from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator

from wikiarena.protocol.enums import ParticipantKind
from wikiarena.protocol.enums import PathKind
from wikiarena.protocol.enums import PathSource
from wikiarena.protocol.rules import BenchmarkRules
from wikiarena.protocol.rules import ExecutionPolicy
from wikiarena.protocol.rules import NavigationRules


def _normalize_title_for_id(title: str) -> str:
    collapsed_whitespace = " ".join(
        title.strip().split(),
    )
    underscores = collapsed_whitespace.replace(
        " ",
        "_",
    )
    alnum_safe = re.sub(
        r"[^0-9A-Za-z_]+",
        "_",
        underscores,
    )
    deduped_underscores = re.sub(
        r"_+",
        "_",
        alnum_safe,
    )
    return deduped_underscores.strip("_").lower()


def build_task_id(
    language: str,
    start_page_title: str,
    target_page_title: str,
) -> str:
    start = _normalize_title_for_id(
        start_page_title,
    )
    target = _normalize_title_for_id(
        target_page_title,
    )
    return f"{language}__{start}__{target}"


class ReferencePath(BaseModel):
    path_kind: PathKind = PathKind.SHORTEST
    page_titles: list[str] = Field(
        min_length=2,
    )
    hop_count: int | None = Field(
        default=None,
        ge=0,
    )
    computed_at: datetime
    valid_for_snapshot_id: str | None = None
    source: PathSource = PathSource.LOCAL_SQLITE

    @model_validator(mode="after")
    def ensure_hop_count(self) -> "ReferencePath":
        inferred_hop_count = (
            len(
                self.page_titles,
            )
            - 1
        )
        if self.hop_count is None:
            self.hop_count = inferred_hop_count
            return self
        if self.hop_count != inferred_hop_count:
            raise ValueError(
                "hop_count must equal len(page_titles) - 1",
            )
        return self


class TaskSpec(BaseModel):
    task_id: str | None = None
    language: str = "en"
    start_page_title: str
    target_page_title: str
    reference_paths: list[ReferencePath] = Field(
        default_factory=list,
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    @model_validator(mode="after")
    def validate_and_fill_task_id(self) -> "TaskSpec":
        if self.start_page_title == self.target_page_title:
            raise ValueError(
                "start_page_title and target_page_title must be different",
            )

        canonical_task_id = build_task_id(
            language=self.language,
            start_page_title=self.start_page_title,
            target_page_title=self.target_page_title,
        )

        if self.task_id is None:
            self.task_id = canonical_task_id
            return self

        if self.task_id != canonical_task_id:
            raise ValueError(
                f"task_id '{self.task_id}' does not match canonical value '{canonical_task_id}'",
            )

        return self


class DriverConfig(BaseModel):
    provider: str
    model: str
    settings: dict[str, Any] = Field(
        default_factory=dict,
    )


class ParticipantSpec(BaseModel):
    participant_id: str
    participant_kind: ParticipantKind = ParticipantKind.LLM
    display_name: str
    driver_config: DriverConfig
    execution_policy_overrides: ExecutionPolicy | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )


class RunSpec(BaseModel):
    run_id: str
    benchmark_id: str
    race_id: str
    task_id: str
    participant_id: str
    navigation_rules: NavigationRules
    seed: int | None = None
    max_step_attempts_override: int | None = Field(
        default=None,
        ge=1,
    )

    @property
    def max_step_attempts(self) -> int:
        if self.max_step_attempts_override is not None:
            return self.max_step_attempts_override
        return self.navigation_rules.derived_max_step_attempts


class RaceSpec(BaseModel):
    race_id: str
    benchmark_id: str
    task_id: str
    run_ids: list[str] = Field(
        default_factory=list,
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )


class BenchmarkSpec(BaseModel):
    benchmark_id: str
    taskset_id: str
    rules: BenchmarkRules
    participants: list[ParticipantSpec]
    tasks: list[TaskSpec]
    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "BenchmarkSpec":
        participant_ids = [
            participant.participant_id for participant in self.participants
        ]
        duplicate_participants = _find_duplicates(
            participant_ids,
        )
        if duplicate_participants:
            raise ValueError(
                f"duplicate participant_id values: {sorted(duplicate_participants)}",
            )

        task_ids: list[str] = []
        for task in self.tasks:
            if task.task_id is None:
                raise ValueError(
                    "task_id cannot be null after TaskSpec validation",
                )
            task_ids.append(
                task.task_id,
            )
        duplicate_tasks = _find_duplicates(
            task_ids,
        )
        if duplicate_tasks:
            raise ValueError(
                f"duplicate task_id values: {sorted(duplicate_tasks)}",
            )

        return self


def _find_duplicates(values: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(
                value,
            )
            continue
        seen.add(
            value,
        )
    return duplicates
