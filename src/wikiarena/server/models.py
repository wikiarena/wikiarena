from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

SolvePathMode = Literal["single", "all_shortest"]


class HealthResponse(BaseModel):
    status: str


class ErrorResponse(BaseModel):
    code: str
    message: str


class MetaResponse(BaseModel):
    service_version: str
    snapshot_id: str
    dump_date: str
    node_count: int
    edge_count: int
    default_path_mode: SolvePathMode
    supported_path_modes: list[SolvePathMode] = Field(
        default_factory=list,
    )


class RandomPageTitlesResponse(BaseModel):
    snapshot_id: str
    titles: list[str] = Field(
        default_factory=list,
    )


class TitleValidationResponse(BaseModel):
    snapshot_id: str
    query_title: str
    exists: bool
    canonical_title: str | None = None


class SolveRequest(BaseModel):
    start_title: Annotated[str, Field(min_length=1)]
    target_title: Annotated[str, Field(min_length=1)]
    path_mode: SolvePathMode = "single"

    @field_validator(
        "start_title",
        "target_title",
    )
    @classmethod
    def strip_and_validate_non_empty(
        cls,
        value: str,
    ) -> str:
        stripped_value = value.strip()
        if not stripped_value:
            raise ValueError(
                "title cannot be empty",
            )
        return stripped_value


class SolveResponse(BaseModel):
    snapshot_id: str
    start_title: str
    target_title: str
    path_length: int | None
    paths: list[list[str]] = Field(
        default_factory=list,
    )
    solve_ms: float
    pages_visited: int
    links_scanned: int
