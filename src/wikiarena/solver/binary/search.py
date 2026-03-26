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

    path_node_ids = find_shortest_path_by_node_ids(
        graph,
        start_node_id=start_node_id,
        target_node_id=target_node_id,
    )
    if path_node_ids is None:
        return None

    return BinaryShortestPathResult(
        path_node_ids=path_node_ids,
        path_titles=tuple(
            graph.title_for_node_id(
                node_id,
            )
            for node_id in path_node_ids
        ),
    )


def find_shortest_path_by_node_ids(
    graph: BinarySearchGraph,
    *,
    start_node_id: int,
    target_node_id: int,
) -> tuple[int, ...] | None:
    if start_node_id == target_node_id:
        return (start_node_id,)

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

    while forward_frontier and backward_frontier:
        if len(forward_frontier) < len(backward_frontier):
            next_forward_frontier, meeting_node_ids = _expand_forward_frontier(
                graph,
                frontier_node_ids=forward_frontier,
                forward_parents=forward_parents,
                backward_parents=backward_parents,
            )
            if meeting_node_ids:
                return _reconstruct_path(
                    meeting_node_id=min(
                        meeting_node_ids,
                    ),
                    forward_parents=forward_parents,
                    backward_parents=backward_parents,
                )
            forward_frontier = next_forward_frontier
        else:
            next_backward_frontier, meeting_node_ids = _expand_backward_frontier(
                graph,
                frontier_node_ids=backward_frontier,
                backward_parents=backward_parents,
                forward_parents=forward_parents,
            )
            if meeting_node_ids:
                return _reconstruct_path(
                    meeting_node_id=min(
                        meeting_node_ids,
                    ),
                    forward_parents=forward_parents,
                    backward_parents=backward_parents,
                )
            backward_frontier = next_backward_frontier

    return None


def _expand_forward_frontier(
    graph: BinarySearchGraph,
    *,
    frontier_node_ids: set[int],
    forward_parents: dict[int, int | None],
    backward_parents: dict[int, int | None],
) -> tuple[set[int], set[int]]:
    next_frontier: set[int] = set()
    meeting_node_ids: set[int] = set()

    for node_id in sorted(
        frontier_node_ids,
    ):
        for neighbor_id in graph.iter_outgoing_neighbors(
            node_id,
        ):
            if neighbor_id in forward_parents:
                continue
            forward_parents[neighbor_id] = node_id
            next_frontier.add(
                neighbor_id,
            )
            if neighbor_id in backward_parents:
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
) -> tuple[set[int], set[int]]:
    next_frontier: set[int] = set()
    meeting_node_ids: set[int] = set()

    for node_id in sorted(
        frontier_node_ids,
    ):
        for neighbor_id in graph.iter_incoming_neighbors(
            node_id,
        ):
            if neighbor_id in backward_parents:
                continue
            backward_parents[neighbor_id] = node_id
            next_frontier.add(
                neighbor_id,
            )
            if neighbor_id in forward_parents:
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
