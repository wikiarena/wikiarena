from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Protocol


class BinarySearchGraph(Protocol):
    def find_node_id(
        self,
        title: str,
    ) -> int | None: ...

    def title_for_node_id(
        self,
        node_id: int,
    ) -> str: ...

    def iter_outgoing_neighbors(
        self,
        node_id: int,
    ) -> Iterator[int]: ...

    def iter_incoming_neighbors(
        self,
        node_id: int,
    ) -> Iterator[int]: ...


@dataclass(frozen=True)
class BinaryShortestPathResult:
    path_node_ids: tuple[int, ...]
    path_titles: tuple[str, ...]
    pages_visited: int
    links_scanned: int

    @property
    def path_length(
        self,
    ) -> int:
        return (
            len(
                self.path_node_ids,
            )
            - 1
        )


@dataclass(frozen=True)
class BinaryShortestPathSearchResult:
    path_node_ids: tuple[int, ...] | None
    pages_visited: int
    links_scanned: int

    @property
    def path_length(
        self,
    ) -> int | None:
        if self.path_node_ids is None:
            return None
        return (
            len(
                self.path_node_ids,
            )
            - 1
        )


@dataclass
class _BinarySearchCounter:
    pages_visited: int
    links_scanned: int


def find_shortest_path_by_titles(
    graph: BinarySearchGraph,
    *,
    start_title: str,
    target_title: str,
) -> BinaryShortestPathResult | None:
    start_node_id = graph.find_node_id(
        start_title,
    )
    if start_node_id is None:
        raise ValueError(
            f"unknown start title: {start_title}",
        )

    target_node_id = graph.find_node_id(
        target_title,
    )
    if target_node_id is None:
        raise ValueError(
            f"unknown target title: {target_title}",
        )

    search_result = search_shortest_path_by_node_ids(
        graph,
        start_node_id=start_node_id,
        target_node_id=target_node_id,
    )
    if search_result.path_node_ids is None:
        return None

    return BinaryShortestPathResult(
        path_node_ids=search_result.path_node_ids,
        path_titles=tuple(
            graph.title_for_node_id(
                node_id,
            )
            for node_id in search_result.path_node_ids
        ),
        pages_visited=search_result.pages_visited,
        links_scanned=search_result.links_scanned,
    )


def find_shortest_path_by_node_ids(
    graph: BinarySearchGraph,
    *,
    start_node_id: int,
    target_node_id: int,
) -> tuple[int, ...] | None:
    return search_shortest_path_by_node_ids(
        graph,
        start_node_id=start_node_id,
        target_node_id=target_node_id,
    ).path_node_ids


def search_shortest_path_by_node_ids(
    graph: BinarySearchGraph,
    *,
    start_node_id: int,
    target_node_id: int,
) -> BinaryShortestPathSearchResult:
    if start_node_id == target_node_id:
        return BinaryShortestPathSearchResult(
            path_node_ids=(start_node_id,),
            pages_visited=1,
            links_scanned=0,
        )

    forward_frontier = {
        start_node_id,
    }
    backward_frontier = {
        target_node_id,
    }
    forward_parents: dict[int, int | None] = {
        start_node_id: None,
    }
    backward_parents: dict[int, int | None] = {
        target_node_id: None,
    }
    search_counter = _BinarySearchCounter(
        pages_visited=2,
        links_scanned=0,
    )

    while forward_frontier and backward_frontier:
        if len(forward_frontier) < len(backward_frontier):
            next_forward_frontier, meeting_node_ids = _expand_forward_frontier(
                graph,
                frontier_node_ids=forward_frontier,
                forward_parents=forward_parents,
                backward_parents=backward_parents,
                search_counter=search_counter,
            )
            if meeting_node_ids:
                return BinaryShortestPathSearchResult(
                    path_node_ids=_reconstruct_path(
                        meeting_node_id=min(
                            meeting_node_ids,
                        ),
                        forward_parents=forward_parents,
                        backward_parents=backward_parents,
                    ),
                    pages_visited=search_counter.pages_visited,
                    links_scanned=search_counter.links_scanned,
                )
            forward_frontier = next_forward_frontier
        else:
            next_backward_frontier, meeting_node_ids = _expand_backward_frontier(
                graph,
                frontier_node_ids=backward_frontier,
                backward_parents=backward_parents,
                forward_parents=forward_parents,
                search_counter=search_counter,
            )
            if meeting_node_ids:
                return BinaryShortestPathSearchResult(
                    path_node_ids=_reconstruct_path(
                        meeting_node_id=min(
                            meeting_node_ids,
                        ),
                        forward_parents=forward_parents,
                        backward_parents=backward_parents,
                    ),
                    pages_visited=search_counter.pages_visited,
                    links_scanned=search_counter.links_scanned,
                )
            backward_frontier = next_backward_frontier

    return BinaryShortestPathSearchResult(
        path_node_ids=None,
        pages_visited=search_counter.pages_visited,
        links_scanned=search_counter.links_scanned,
    )


def _expand_forward_frontier(
    graph: BinarySearchGraph,
    *,
    frontier_node_ids: set[int],
    forward_parents: dict[int, int | None],
    backward_parents: dict[int, int | None],
    search_counter: _BinarySearchCounter,
) -> tuple[set[int], set[int]]:
    next_frontier: set[int] = set()
    meeting_node_ids: set[int] = set()

    for node_id in sorted(
        frontier_node_ids,
    ):
        for neighbor_id in graph.iter_outgoing_neighbors(
            node_id,
        ):
            search_counter.links_scanned += 1
            if neighbor_id in forward_parents:
                continue
            neighbor_seen_by_backward = neighbor_id in backward_parents
            if not neighbor_seen_by_backward:
                search_counter.pages_visited += 1
            forward_parents[neighbor_id] = node_id
            next_frontier.add(
                neighbor_id,
            )
            if neighbor_seen_by_backward:
                meeting_node_ids.add(
                    neighbor_id,
                )

    return next_frontier, meeting_node_ids


def _expand_backward_frontier(
    graph: BinarySearchGraph,
    *,
    frontier_node_ids: set[int],
    backward_parents: dict[int, int | None],
    forward_parents: dict[int, int | None],
    search_counter: _BinarySearchCounter,
) -> tuple[set[int], set[int]]:
    next_frontier: set[int] = set()
    meeting_node_ids: set[int] = set()

    for node_id in sorted(
        frontier_node_ids,
    ):
        for neighbor_id in graph.iter_incoming_neighbors(
            node_id,
        ):
            search_counter.links_scanned += 1
            if neighbor_id in backward_parents:
                continue
            neighbor_seen_by_forward = neighbor_id in forward_parents
            if not neighbor_seen_by_forward:
                search_counter.pages_visited += 1
            backward_parents[neighbor_id] = node_id
            next_frontier.add(
                neighbor_id,
            )
            if neighbor_seen_by_forward:
                meeting_node_ids.add(
                    neighbor_id,
                )

    return next_frontier, meeting_node_ids


def _reconstruct_path(
    *,
    meeting_node_id: int,
    forward_parents: dict[int, int | None],
    backward_parents: dict[int, int | None],
) -> tuple[int, ...]:
    prefix: list[int] = []
    current_node_id: int | None = meeting_node_id
    while current_node_id is not None:
        prefix.append(
            current_node_id,
        )
        current_node_id = forward_parents[current_node_id]
    prefix.reverse()

    suffix: list[int] = []
    current_node_id = backward_parents[meeting_node_id]
    while current_node_id is not None:
        suffix.append(
            current_node_id,
        )
        current_node_id = backward_parents[current_node_id]

    return tuple(
        prefix + suffix,
    )
