"""Solver models for path finding functionality."""

from typing import Annotated, List

from pydantic import BaseModel, Field


class SolverRequest(BaseModel):
    """Request model for shortest path finding."""

    start_page: Annotated[str, Field(min_length=1)] = Field(
        ..., description="Starting Wikipedia page title"
    )
    target_page: Annotated[str, Field(min_length=1)] = Field(
        ..., description="Target Wikipedia page title"
    )


class SolverResponse(BaseModel):
    """Response model for shortest path finding results."""

    paths: List[List[str]] = Field(
        ...,
        description="Shortest paths from start to target page, list of paths, each path is a list of page titles",
    )
    path_length: int = Field(
        ...,
        description="Number of steps in the shortest paths (all returned paths will have this length)",
    )
    computation_time_ms: float = Field(
        ..., description="Time taken to compute the path in milliseconds"
    )
    pages_visited: int = Field(
        default=0,
        description="Number of unique graph pages discovered during the search",
    )
    links_scanned: int = Field(
        default=0,
        description="Number of graph links inspected during the search",
    )


class PositionSolverFacts(BaseModel):
    """Graph facts for one current-page/target-page position."""

    page_title: str
    target_page_title: str
    shortest_path_length: int | None = Field(
        default=None,
        ge=0,
    )
    shortest_paths: list[list[str]] = Field(
        default_factory=list,
    )
    shortest_next_hop_titles: list[str] = Field(
        default_factory=list,
    )
    computation_time_ms: float = Field(
        default=0.0,
        ge=0.0,
    )
    pages_visited: int = Field(
        default=0,
        ge=0,
    )
    links_scanned: int = Field(
        default=0,
        ge=0,
    )
    solver_snapshot_id: str | None = None

    @classmethod
    def from_solver_response(
        cls,
        *,
        page_title: str,
        target_page_title: str,
        solver_response: SolverResponse,
        solver_snapshot_id: str | None = None,
    ) -> "PositionSolverFacts":
        shortest_path_length = None
        if solver_response.path_length >= 0:
            shortest_path_length = solver_response.path_length

        return cls(
            page_title=page_title,
            target_page_title=target_page_title,
            shortest_path_length=shortest_path_length,
            shortest_paths=solver_response.paths,
            shortest_next_hop_titles=_extract_shortest_next_hops(
                solver_response.paths,
            ),
            computation_time_ms=solver_response.computation_time_ms,
            pages_visited=solver_response.pages_visited,
            links_scanned=solver_response.links_scanned,
            solver_snapshot_id=solver_snapshot_id,
        )


def _extract_shortest_next_hops(
    shortest_paths: list[list[str]],
) -> list[str]:
    next_hops: list[str] = []
    seen_next_hops: set[str] = set()
    for path in shortest_paths:
        if len(path) < 2:
            continue
        next_hop = path[1]
        if next_hop in seen_next_hops:
            continue
        seen_next_hops.add(
            next_hop,
        )
        next_hops.append(
            next_hop,
        )
    return next_hops
