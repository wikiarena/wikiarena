from __future__ import annotations

from dataclasses import dataclass
from functools import cache
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


@dataclass(frozen=True)
class BinaryAllShortestPathsResult:
    path_node_id_paths: tuple[tuple[int, ...], ...]
    path_title_paths: tuple[tuple[str, ...], ...]
    pages_visited: int
    links_scanned: int

    @property
    def path_node_ids(
        self,
    ) -> tuple[tuple[int, ...], ...]:
        return self.path_node_id_paths

    @property
    def path_titles(
        self,
    ) -> tuple[tuple[str, ...], ...]:
        return self.path_title_paths

    @property
    def path_count(
        self,
    ) -> int:
        return len(
            self.path_node_id_paths,
        )

    @property
    def path_length(
        self,
    ) -> int:
        return (
            len(
                self.path_node_id_paths[0],
            )
            - 1
        )


@dataclass(frozen=True)
class BinaryAllShortestPathsSearchResult:
    path_node_id_paths: tuple[tuple[int, ...], ...]
    pages_visited: int
    links_scanned: int

    @property
    def path_count(
        self,
    ) -> int:
        return len(
            self.path_node_id_paths,
        )

    @property
    def path_length(
        self,
    ) -> int | None:
        if not self.path_node_id_paths:
            return None
        return (
            len(
                self.path_node_id_paths[0],
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


def find_all_shortest_paths_by_titles(
    graph: BinarySearchGraph,
    *,
    start_title: str,
    target_title: str,
) -> BinaryAllShortestPathsResult | None:
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

    search_result = search_all_shortest_paths_by_node_ids(
        graph,
        start_node_id=start_node_id,
        target_node_id=target_node_id,
    )
    if not search_result.path_node_id_paths:
        return None

    return BinaryAllShortestPathsResult(
        path_node_id_paths=search_result.path_node_id_paths,
        path_title_paths=tuple(
            tuple(
                graph.title_for_node_id(
                    node_id,
                )
                for node_id in path_node_ids
            )
            for path_node_ids in search_result.path_node_id_paths
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


def find_all_shortest_paths_by_node_ids(
    graph: BinarySearchGraph,
    *,
    start_node_id: int,
    target_node_id: int,
) -> tuple[tuple[int, ...], ...]:
    return search_all_shortest_paths_by_node_ids(
        graph,
        start_node_id=start_node_id,
        target_node_id=target_node_id,
    ).path_node_id_paths


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


def search_all_shortest_paths_by_node_ids(
    graph: BinarySearchGraph,
    *,
    start_node_id: int,
    target_node_id: int,
) -> BinaryAllShortestPathsSearchResult:
    if start_node_id == target_node_id:
        return BinaryAllShortestPathsSearchResult(
            path_node_id_paths=((start_node_id,),),
            pages_visited=1,
            links_scanned=0,
        )

    forward_frontier = {
        start_node_id,
    }
    backward_frontier = {
        target_node_id,
    }
    forward_depth_by_node_id = {
        start_node_id: 0,
    }
    backward_depth_by_node_id = {
        target_node_id: 0,
    }
    forward_parents_by_node_id: dict[int, set[int]] = {
        start_node_id: set(),
    }
    backward_successors_by_node_id: dict[int, set[int]] = {
        target_node_id: set(),
    }
    discovered_node_ids = {
        start_node_id,
        target_node_id,
    }
    search_counter = _BinarySearchCounter(
        pages_visited=2,
        links_scanned=0,
    )
    forward_frontier_depth = 0
    backward_frontier_depth = 0

    while forward_frontier and backward_frontier:
        if len(forward_frontier) < len(backward_frontier):
            forward_frontier_depth += 1
            (
                forward_frontier,
                shortest_distance,
                meeting_node_ids,
            ) = _expand_forward_frontier_for_all_paths(
                graph,
                frontier_node_ids=forward_frontier,
                next_depth=forward_frontier_depth,
                forward_depth_by_node_id=forward_depth_by_node_id,
                backward_depth_by_node_id=backward_depth_by_node_id,
                forward_parents_by_node_id=forward_parents_by_node_id,
                discovered_node_ids=discovered_node_ids,
                search_counter=search_counter,
            )
        else:
            backward_frontier_depth += 1
            (
                backward_frontier,
                shortest_distance,
                meeting_node_ids,
            ) = _expand_backward_frontier_for_all_paths(
                graph,
                frontier_node_ids=backward_frontier,
                next_depth=backward_frontier_depth,
                backward_depth_by_node_id=backward_depth_by_node_id,
                forward_depth_by_node_id=forward_depth_by_node_id,
                backward_successors_by_node_id=backward_successors_by_node_id,
                discovered_node_ids=discovered_node_ids,
                search_counter=search_counter,
            )

        if shortest_distance is not None:
            return BinaryAllShortestPathsSearchResult(
                path_node_id_paths=_reconstruct_all_shortest_paths(
                    start_node_id=start_node_id,
                    target_node_id=target_node_id,
                    meeting_node_ids=meeting_node_ids,
                    forward_parents_by_node_id=forward_parents_by_node_id,
                    backward_successors_by_node_id=backward_successors_by_node_id,
                    shortest_distance=shortest_distance,
                    forward_depth_by_node_id=forward_depth_by_node_id,
                    backward_depth_by_node_id=backward_depth_by_node_id,
                ),
                pages_visited=search_counter.pages_visited,
                links_scanned=search_counter.links_scanned,
            )

    return BinaryAllShortestPathsSearchResult(
        path_node_id_paths=(),
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


def _expand_forward_frontier_for_all_paths(
    graph: BinarySearchGraph,
    *,
    frontier_node_ids: set[int],
    next_depth: int,
    forward_depth_by_node_id: dict[int, int],
    backward_depth_by_node_id: dict[int, int],
    forward_parents_by_node_id: dict[int, set[int]],
    discovered_node_ids: set[int],
    search_counter: _BinarySearchCounter,
) -> tuple[set[int], int | None, set[int]]:
    next_frontier: set[int] = set()
    shortest_distance: int | None = None
    meeting_node_ids: set[int] = set()

    for node_id in sorted(
        frontier_node_ids,
    ):
        for neighbor_id in graph.iter_outgoing_neighbors(
            node_id,
        ):
            search_counter.links_scanned += 1
            known_forward_depth = forward_depth_by_node_id.get(
                neighbor_id,
            )
            if known_forward_depth is None:
                forward_depth_by_node_id[neighbor_id] = next_depth
                forward_parents_by_node_id[neighbor_id] = {
                    node_id,
                }
                next_frontier.add(
                    neighbor_id,
                )
                if neighbor_id not in discovered_node_ids:
                    discovered_node_ids.add(
                        neighbor_id,
                    )
                    search_counter.pages_visited += 1
            elif known_forward_depth == next_depth:
                forward_parents_by_node_id[neighbor_id].add(
                    node_id,
                )
            else:
                continue

            backward_depth = backward_depth_by_node_id.get(
                neighbor_id,
            )
            if backward_depth is None:
                continue

            candidate_distance = next_depth + backward_depth
            if shortest_distance is None or candidate_distance < shortest_distance:
                shortest_distance = candidate_distance
                meeting_node_ids = {
                    neighbor_id,
                }
            elif candidate_distance == shortest_distance:
                meeting_node_ids.add(
                    neighbor_id,
                )

    return next_frontier, shortest_distance, meeting_node_ids


def _expand_backward_frontier_for_all_paths(
    graph: BinarySearchGraph,
    *,
    frontier_node_ids: set[int],
    next_depth: int,
    backward_depth_by_node_id: dict[int, int],
    forward_depth_by_node_id: dict[int, int],
    backward_successors_by_node_id: dict[int, set[int]],
    discovered_node_ids: set[int],
    search_counter: _BinarySearchCounter,
) -> tuple[set[int], int | None, set[int]]:
    next_frontier: set[int] = set()
    shortest_distance: int | None = None
    meeting_node_ids: set[int] = set()

    for node_id in sorted(
        frontier_node_ids,
    ):
        for neighbor_id in graph.iter_incoming_neighbors(
            node_id,
        ):
            search_counter.links_scanned += 1
            known_backward_depth = backward_depth_by_node_id.get(
                neighbor_id,
            )
            if known_backward_depth is None:
                backward_depth_by_node_id[neighbor_id] = next_depth
                backward_successors_by_node_id[neighbor_id] = {
                    node_id,
                }
                next_frontier.add(
                    neighbor_id,
                )
                if neighbor_id not in discovered_node_ids:
                    discovered_node_ids.add(
                        neighbor_id,
                    )
                    search_counter.pages_visited += 1
            elif known_backward_depth == next_depth:
                backward_successors_by_node_id[neighbor_id].add(
                    node_id,
                )
            else:
                continue

            forward_depth = forward_depth_by_node_id.get(
                neighbor_id,
            )
            if forward_depth is None:
                continue

            candidate_distance = next_depth + forward_depth
            if shortest_distance is None or candidate_distance < shortest_distance:
                shortest_distance = candidate_distance
                meeting_node_ids = {
                    neighbor_id,
                }
            elif candidate_distance == shortest_distance:
                meeting_node_ids.add(
                    neighbor_id,
                )

    return next_frontier, shortest_distance, meeting_node_ids


def _reconstruct_all_shortest_paths(
    *,
    start_node_id: int,
    target_node_id: int,
    meeting_node_ids: set[int],
    forward_parents_by_node_id: dict[int, set[int]],
    backward_successors_by_node_id: dict[int, set[int]],
    shortest_distance: int,
    forward_depth_by_node_id: dict[int, int],
    backward_depth_by_node_id: dict[int, int],
) -> tuple[tuple[int, ...], ...]:
    canonical_meeting_node_ids = tuple(
        node_id
        for node_id in sorted(
            meeting_node_ids,
        )
        if forward_depth_by_node_id[node_id] + backward_depth_by_node_id[node_id]
        == shortest_distance
    )

    @cache
    def collect_forward_paths(
        node_id: int,
    ) -> tuple[tuple[int, ...], ...]:
        if node_id == start_node_id:
            return ((start_node_id,),)

        paths: list[tuple[int, ...]] = []
        for parent_node_id in sorted(
            forward_parents_by_node_id[node_id],
        ):
            for prefix in collect_forward_paths(
                parent_node_id,
            ):
                paths.append(
                    prefix + (node_id,),
                )
        return tuple(
            paths,
        )

    @cache
    def collect_backward_paths(
        node_id: int,
    ) -> tuple[tuple[int, ...], ...]:
        if node_id == target_node_id:
            return ((target_node_id,),)

        paths: list[tuple[int, ...]] = []
        for successor_node_id in sorted(
            backward_successors_by_node_id[node_id],
        ):
            for suffix in collect_backward_paths(
                successor_node_id,
            ):
                paths.append(
                    (node_id,) + suffix,
                )
        return tuple(
            paths,
        )

    all_paths: list[tuple[int, ...]] = []
    for meeting_node_id in canonical_meeting_node_ids:
        for prefix in collect_forward_paths(
            meeting_node_id,
        ):
            for suffix in collect_backward_paths(
                meeting_node_id,
            ):
                all_paths.append(
                    prefix + suffix[1:],
                )

    all_paths.sort()
    return tuple(
        all_paths,
    )


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
