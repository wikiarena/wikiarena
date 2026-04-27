from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from wikiarena.protocol import TaskSpec
from wikiarena.solver import (
    PathAuditCache,
    PathAuditResult,
    audit_solver_path_against_live_wikipedia,
)
from wikiarena.solver.path_audit import WikipediaAuditPageService


class TasksetAuditRow(BaseModel):
    task_id: str
    shortest_path_length: int | None = None
    solver_snapshot_id: str | None = None
    source: str | None = None
    path: list[str] = Field(
        default_factory=list,
    )
    audit_status: str
    strict_audit: PathAuditResult | None = None
    redirect_audit: PathAuditResult | None = None
    all_edges_directly_visible: bool | None = None
    all_edges_visible_with_redirects: bool | None = None
    audit_error_type: str | None = None
    audit_error: str | None = None


class TasksetAuditResult(BaseModel):
    rows: list[TasksetAuditRow] = Field(
        default_factory=list,
    )

    def build_summary(
        self,
    ) -> dict[str, object]:
        missing_solver_shortest_path = 0
        audit_error_count = 0
        audited_rows = 0
        strict_pass_count = 0
        redirect_pass_count = 0
        for row in self.rows:
            if row.audit_status == "missing_solver_shortest_path":
                missing_solver_shortest_path += 1
                continue
            if row.audit_status == "audit_error":
                audit_error_count += 1
                continue
            audited_rows += 1
            if row.all_edges_directly_visible:
                strict_pass_count += 1
            if row.all_edges_visible_with_redirects:
                redirect_pass_count += 1

        return {
            "total_tasks": len(
                self.rows,
            ),
            "audited_tasks": audited_rows,
            "missing_solver_shortest_path": missing_solver_shortest_path,
            "audit_error_count": audit_error_count,
            "strict_pass_count": strict_pass_count,
            "redirect_pass_count": redirect_pass_count,
        }


async def audit_taskset_against_live_wikipedia(
    tasks: list[TaskSpec],
    *,
    wiki_service: WikipediaAuditPageService,
) -> TasksetAuditResult:
    cache = PathAuditCache()
    rows: list[TasksetAuditRow] = []
    for task in tasks:
        task_id = task.task_id
        if task_id is None:
            raise ValueError(
                "task_id cannot be null after TaskSpec validation",
            )

        solver_shortest_path = task.solver_shortest_path
        if solver_shortest_path is None:
            rows.append(
                TasksetAuditRow(
                    task_id=task_id,
                    shortest_path_length=task.shortest_path_length,
                    audit_status="missing_solver_shortest_path",
                ),
            )
            continue

        try:
            strict_audit = await audit_solver_path_against_live_wikipedia(
                backend_id=solver_shortest_path.source.value,
                path=solver_shortest_path.page_titles,
                wiki_service=wiki_service,
                allow_redirects=False,
                cache=cache,
            )
            redirect_audit = await audit_solver_path_against_live_wikipedia(
                backend_id=solver_shortest_path.source.value,
                path=solver_shortest_path.page_titles,
                wiki_service=wiki_service,
                allow_redirects=True,
                cache=cache,
            )
        except Exception as error:
            rows.append(
                TasksetAuditRow(
                    task_id=task_id,
                    shortest_path_length=task.shortest_path_length,
                    solver_snapshot_id=solver_shortest_path.solver_snapshot_id,
                    source=solver_shortest_path.source.value,
                    path=list(
                        solver_shortest_path.page_titles,
                    ),
                    audit_status="audit_error",
                    audit_error_type=type(error).__name__,
                    audit_error=str(
                        error,
                    ),
                ),
            )
            continue
        rows.append(
            TasksetAuditRow(
                task_id=task_id,
                shortest_path_length=task.shortest_path_length,
                solver_snapshot_id=solver_shortest_path.solver_snapshot_id,
                source=solver_shortest_path.source.value,
                path=list(
                    solver_shortest_path.page_titles,
                ),
                audit_status="audited",
                strict_audit=strict_audit,
                redirect_audit=redirect_audit,
                all_edges_directly_visible=strict_audit.all_edges_directly_visible,
                all_edges_visible_with_redirects=(
                    redirect_audit.all_edges_visible_with_redirects
                ),
            ),
        )

    return TasksetAuditResult(
        rows=rows,
    )


def read_taskset_jsonl(
    input_path: str | Path,
) -> list[TaskSpec]:
    resolved_input_path = Path(
        input_path,
    ).expanduser()
    tasks: list[TaskSpec] = []
    with resolved_input_path.open(
        "r",
        encoding="utf-8",
    ) as file_handle:
        for line in file_handle:
            stripped_line = line.strip()
            if not stripped_line:
                continue
            tasks.append(
                TaskSpec.model_validate_json(
                    stripped_line,
                ),
            )
    return tasks


def write_taskset_audit_jsonl(
    rows: list[TasksetAuditRow],
    *,
    output_path: str | Path,
) -> None:
    resolved_output_path = Path(
        output_path,
    ).expanduser()
    with resolved_output_path.open(
        "w",
        encoding="utf-8",
    ) as file_handle:
        for row in rows:
            file_handle.write(
                json.dumps(
                    row.model_dump(
                        mode="json",
                    ),
                ),
            )
            file_handle.write(
                "\n",
            )
