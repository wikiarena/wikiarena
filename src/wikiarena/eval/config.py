from __future__ import annotations

import json
import tomllib
from pathlib import Path

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator

from wikiarena.eval.benchmark_runner import BenchmarkConcurrencyConfig
from wikiarena.eval.benchmark_runner import BenchmarkRunOptions
from wikiarena.protocol import BenchmarkRules
from wikiarena.protocol import BenchmarkSpec
from wikiarena.protocol import ParticipantSpec
from wikiarena.protocol import TaskSpec


class EvalRunConfig(BaseModel):
    benchmark_id: str
    taskset_id: str
    participants: list[ParticipantSpec]
    rules: BenchmarkRules
    tasks: list[TaskSpec] = Field(
        default_factory=list,
    )
    taskset_path: str | None = None
    run_options: BenchmarkRunOptions = Field(
        default_factory=BenchmarkRunOptions,
    )
    concurrency: BenchmarkConcurrencyConfig = Field(
        default_factory=BenchmarkConcurrencyConfig,
    )
    metadata: dict[str, object] = Field(
        default_factory=dict,
    )

    @model_validator(mode="after")
    def validate_task_source(self) -> "EvalRunConfig":
        has_inline_tasks = bool(
            self.tasks,
        )
        has_taskset_path = self.taskset_path is not None

        if has_inline_tasks == has_taskset_path:
            raise ValueError(
                "exactly one of tasks or taskset_path must be provided",
            )

        return self

    def to_benchmark_spec(self) -> BenchmarkSpec:
        return BenchmarkSpec(
            benchmark_id=self.benchmark_id,
            taskset_id=self.taskset_id,
            rules=self.rules,
            participants=self.participants,
            tasks=self.tasks,
            metadata=self.metadata,
        )


class LoadedEvalRunConfig(BaseModel):
    benchmark_spec: BenchmarkSpec
    run_options: BenchmarkRunOptions
    concurrency: BenchmarkConcurrencyConfig


def load_eval_run_config(
    config_path: str | Path,
) -> LoadedEvalRunConfig:
    resolved_config_path = (
        Path(
            config_path,
        )
        .expanduser()
        .resolve()
    )
    raw_config = _load_data_file(
        resolved_config_path,
    )
    eval_run_config = EvalRunConfig.model_validate(
        raw_config,
    )

    if eval_run_config.taskset_path is not None:
        taskset_path = (
            resolved_config_path.parent / eval_run_config.taskset_path
        ).resolve()
        loaded_tasks = load_taskset(
            taskset_path,
        )
        eval_run_config = eval_run_config.model_copy(
            update={
                "tasks": loaded_tasks,
                "taskset_path": None,
            },
        )

    return LoadedEvalRunConfig(
        benchmark_spec=eval_run_config.to_benchmark_spec(),
        run_options=eval_run_config.run_options,
        concurrency=eval_run_config.concurrency,
    )


load_benchmark_run_config = load_eval_run_config
BenchmarkRunConfig = EvalRunConfig
LoadedBenchmarkRunConfig = LoadedEvalRunConfig


def load_taskset(
    taskset_path: str | Path,
) -> list[TaskSpec]:
    resolved_taskset_path = (
        Path(
            taskset_path,
        )
        .expanduser()
        .resolve()
    )

    if resolved_taskset_path.suffix == ".jsonl":
        tasks: list[TaskSpec] = []
        with resolved_taskset_path.open(
            "r",
            encoding="utf-8",
        ) as file_handle:
            for line_number, line in enumerate(
                file_handle,
                start=1,
            ):
                stripped_line = line.strip()
                if not stripped_line:
                    continue
                try:
                    parsed_line = json.loads(
                        stripped_line,
                    )
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"invalid JSON on line {line_number} of {resolved_taskset_path}",
                    ) from error

                tasks.append(
                    TaskSpec.model_validate(
                        parsed_line,
                    ),
                )
        return tasks

    raw_data = _load_data_file(
        resolved_taskset_path,
    )
    if not isinstance(
        raw_data,
        list,
    ):
        raise ValueError(
            f"taskset file {resolved_taskset_path} must contain a list of tasks",
        )

    return [
        TaskSpec.model_validate(
            task,
        )
        for task in raw_data
    ]


def _load_data_file(
    file_path: Path,
) -> object:
    suffix = file_path.suffix.lower()
    if suffix == ".json":
        with file_path.open(
            "r",
            encoding="utf-8",
        ) as file_handle:
            return json.load(
                file_handle,
            )

    if suffix == ".toml":
        with file_path.open(
            "rb",
        ) as file_handle:
            return tomllib.load(
                file_handle,
            )

    raise ValueError(
        f"unsupported config format for {file_path}; use .json, .jsonl, or .toml",
    )
