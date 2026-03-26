from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from wikiarena.core import RunExecutionArtifact
from wikiarena.protocol import RunResult


class ResultFileIdentity(BaseModel):
    total_runs: int
    ruleset_hashes: list[str]
    taskset_hashes: list[str]
    wiki_backends: list[str]
    wiki_snapshot_ids: list[str]


class RunResultStore:
    def __init__(
        self,
        output_path: str | Path,
    ):
        self.output_path = Path(
            output_path,
        )
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


def inspect_result_file_identity(
    input_path: str | Path,
) -> ResultFileIdentity:
    resolved_input_path = Path(
        input_path,
    )
    ruleset_hashes: set[str] = set()
    taskset_hashes: set[str] = set()
    wiki_backends: set[str] = set()
    wiki_snapshot_ids: set[str] = set()
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

            wiki_backend = payload.get(
                "wiki_backend",
            )
            if wiki_backend is not None:
                wiki_backends.add(
                    wiki_backend,
                )

            wiki_snapshot_id = payload.get(
                "wiki_snapshot_id",
            )
            if wiki_snapshot_id is not None:
                wiki_snapshot_ids.add(
                    wiki_snapshot_id,
                )

    return ResultFileIdentity(
        total_runs=total_runs,
        ruleset_hashes=sorted(
            ruleset_hashes,
        ),
        taskset_hashes=sorted(
            taskset_hashes,
        ),
        wiki_backends=sorted(
            wiki_backends,
        ),
        wiki_snapshot_ids=sorted(
            wiki_snapshot_ids,
        ),
    )
