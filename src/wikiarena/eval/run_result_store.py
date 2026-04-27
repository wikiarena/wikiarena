from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from wikiarena.core import RunExecutionArtifact
from wikiarena.protocol import RunResult


class ResultFileIdentity(BaseModel):
    total_runs: int
    ruleset_hashes: list[str]
    taskset_hashes: list[str]
    navigation_backends: list[str]
    navigation_snapshot_ids: list[str]
    solver_backends: list[str]
    solver_snapshot_ids: list[str]


class RunResultStore:
    def __init__(
        self,
        output_path: str | Path,
        *,
        artifact_store: Any | None = None,
    ):
        self.output_path = Path(
            output_path,
        )
        self.artifact_store = artifact_store
        self.output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    def append_run_result(
        self,
        run_result: RunResult,
    ) -> None:
        line = json.dumps(
            run_result.model_dump(mode="json"),
            ensure_ascii=False,
        )
        with self.output_path.open(
            "a",
            encoding="utf-8",
        ) as file_handle:
            file_handle.write(
                line,
            )
            file_handle.write(
                "\n",
            )

    def append_artifact(
        self,
        artifact: RunExecutionArtifact,
    ) -> None:
        self.append_run_result(
            artifact.run_result,
        )
        if self.artifact_store is not None:
            self.artifact_store.write_artifact(
                artifact,
            )


def inspect_result_file_identity(
    input_path: str | Path,
) -> ResultFileIdentity:
    resolved_input_path = Path(
        input_path,
    )
    ruleset_hashes: set[str] = set()
    taskset_hashes: set[str] = set()
    navigation_backends: set[str] = set()
    navigation_snapshot_ids: set[str] = set()
    solver_backends: set[str] = set()
    solver_snapshot_ids: set[str] = set()
    total_runs = 0

    with resolved_input_path.open(
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
                payload = json.loads(
                    stripped_line,
                )
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"invalid JSON on line {line_number} of {resolved_input_path}",
                ) from error

            total_runs += 1

            ruleset_hash = payload.get(
                "ruleset_hash",
            )
            if ruleset_hash is not None:
                ruleset_hashes.add(
                    ruleset_hash,
                )

            taskset_hash = payload.get(
                "taskset_hash",
            )
            if taskset_hash is not None:
                taskset_hashes.add(
                    taskset_hash,
                )

            navigation_backend = payload.get(
                "navigation_backend",
            )
            if navigation_backend is not None:
                navigation_backends.add(
                    navigation_backend,
                )

            navigation_snapshot_id = payload.get(
                "navigation_snapshot_id",
            )
            if navigation_snapshot_id is not None:
                navigation_snapshot_ids.add(
                    navigation_snapshot_id,
                )

            solver_backend = payload.get(
                "solver_backend",
            )
            if solver_backend is not None:
                solver_backends.add(
                    solver_backend,
                )

            solver_snapshot_id = payload.get(
                "solver_snapshot_id",
            )
            if solver_snapshot_id is not None:
                solver_snapshot_ids.add(
                    solver_snapshot_id,
                )

    return ResultFileIdentity(
        total_runs=total_runs,
        ruleset_hashes=sorted(
            ruleset_hashes,
        ),
        taskset_hashes=sorted(
            taskset_hashes,
        ),
        navigation_backends=sorted(
            navigation_backends,
        ),
        navigation_snapshot_ids=sorted(
            navigation_snapshot_ids,
        ),
        solver_backends=sorted(
            solver_backends,
        ),
        solver_snapshot_ids=sorted(
            solver_snapshot_ids,
        ),
    )
