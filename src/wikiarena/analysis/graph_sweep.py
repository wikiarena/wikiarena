from __future__ import annotations

from array import array
from dataclasses import dataclass
from random import Random
from time import perf_counter
from typing import Callable, Iterable, Literal, Protocol

from wikiarena.solver.binary.mapped_graph import U32_STRUCT, MappedBinarySolverGraph

SweepDirection = Literal["outgoing", "incoming"]


class SweepGraph(Protocol):
    @property
    def node_count(
        self,
    ) -> int: ...

    def iter_outgoing_neighbors(
        self,
        node_id: int,
    ) -> Iterable[int]: ...

    def iter_incoming_neighbors(
        self,
        node_id: int,
    ) -> Iterable[int]: ...


@dataclass(frozen=True)
class BfsSweepProgress:
    origin_node_id: int
    direction: SweepDirection
    distance: int
    frontier_size: int
    next_frontier_size: int
    visited_count: int
    links_scanned: int
    elapsed_s: float


@dataclass(frozen=True)
class BfsFarthestResult:
    origin_node_id: int
    farthest_node_id: int
    direction: SweepDirection
    distance: int
    visited_count: int
    links_scanned: int
    max_frontier_size: int
    exhausted: bool
    elapsed_s: float


def opposite_sweep_direction(
    direction: SweepDirection,
) -> SweepDirection:
    if direction == "outgoing":
        return "incoming"
    if direction == "incoming":
        return "outgoing"
    raise ValueError(
        f"unknown sweep direction: {direction}",
    )


def outgoing_candidate_endpoints(
    result: BfsFarthestResult,
) -> tuple[int, int]:
    """Return the directed outgoing-edge pair represented by this sweep.

    An incoming sweep from A to B follows reverse edges, which proves an
    outgoing path B -> A of the same length.
    """
    if result.direction == "outgoing":
        return result.origin_node_id, result.farthest_node_id
    return result.farthest_node_id, result.origin_node_id


def alternating_sweeps(
    *,
    graph: SweepGraph,
    start_node_id: int,
    initial_direction: SweepDirection = "outgoing",
    sweep_count: int = 2,
    rng: Random | None = None,
    max_depth: int | None = None,
    progress_callback: Callable[[BfsSweepProgress], None] | None = None,
) -> tuple[BfsFarthestResult, ...]:
    if sweep_count < 1:
        raise ValueError(
            "sweep_count must be at least 1",
        )

    results: list[BfsFarthestResult] = []
    current_node_id = start_node_id
    current_direction = initial_direction
    for _ in range(
        sweep_count,
    ):
        result = find_farthest_reachable_node(
            graph=graph,
            origin_node_id=current_node_id,
            direction=current_direction,
            rng=rng,
            max_depth=max_depth,
            progress_callback=progress_callback,
        )
        results.append(
            result,
        )
        current_node_id = result.farthest_node_id
        current_direction = opposite_sweep_direction(
            current_direction,
        )

    return tuple(
        results,
    )


def find_farthest_reachable_node(
    *,
    graph: SweepGraph,
    origin_node_id: int,
    direction: SweepDirection = "outgoing",
    rng: Random | None = None,
    max_depth: int | None = None,
    progress_callback: Callable[[BfsSweepProgress], None] | None = None,
) -> BfsFarthestResult:
    if origin_node_id < 0 or origin_node_id >= graph.node_count:
        raise ValueError(
            f"origin node id out of range: {origin_node_id}",
        )
    if max_depth is not None and max_depth < 0:
        raise ValueError(
            "max_depth cannot be negative",
        )

    if isinstance(
        graph,
        MappedBinarySolverGraph,
    ):
        return _find_farthest_reachable_node_mapped(
            graph=graph,
            origin_node_id=origin_node_id,
            direction=direction,
            rng=rng,
            max_depth=max_depth,
            progress_callback=progress_callback,
        )

    return _find_farthest_reachable_node_generic(
        graph=graph,
        origin_node_id=origin_node_id,
        direction=direction,
        rng=rng,
        max_depth=max_depth,
        progress_callback=progress_callback,
    )


def _find_farthest_reachable_node_mapped(
    *,
    graph: MappedBinarySolverGraph,
    origin_node_id: int,
    direction: SweepDirection,
    rng: Random | None,
    max_depth: int | None,
    progress_callback: Callable[[BfsSweepProgress], None] | None,
) -> BfsFarthestResult:
    offsets_off, neighbors_off = _mapped_sections(
        graph,
        direction,
    )
    mapped_bytes = graph._mapped_bytes

    start_time = perf_counter()
    visited = bytearray(
        graph.node_count,
    )
    visited[origin_node_id] = 1
    frontier = array(
        "I",
        [origin_node_id],
    )
    last_frontier = frontier
    distance = 0
    visited_count = 1
    links_scanned = 0
    max_frontier_size = 1
    exhausted = True

    while frontier:
        if max_depth is not None and distance >= max_depth:
            exhausted = False
            break

        next_frontier = array(
            "I",
        )
        for node_id in frontier:
            start = U32_STRUCT.unpack_from(
                mapped_bytes,
                offsets_off + (node_id * U32_STRUCT.size),
            )[0]
            end = U32_STRUCT.unpack_from(
                mapped_bytes,
                offsets_off + ((node_id + 1) * U32_STRUCT.size),
            )[0]
            links_scanned += end - start
            byte_offset = neighbors_off + (start * 3)
            byte_end = neighbors_off + (end * 3)
            while byte_offset < byte_end:
                neighbor_node_id = (
                    mapped_bytes[byte_offset]
                    | (mapped_bytes[byte_offset + 1] << 8)
                    | (mapped_bytes[byte_offset + 2] << 16)
                )
                if not visited[neighbor_node_id]:
                    visited[neighbor_node_id] = 1
                    next_frontier.append(
                        neighbor_node_id,
                    )
                byte_offset += 3

        if not next_frontier:
            break

        distance += 1
        visited_count += len(
            next_frontier,
        )
        max_frontier_size = max(
            max_frontier_size,
            len(
                next_frontier,
            ),
        )
        if progress_callback is not None:
            progress_callback(
                BfsSweepProgress(
                    origin_node_id=origin_node_id,
                    direction=direction,
                    distance=distance,
                    frontier_size=len(
                        frontier,
                    ),
                    next_frontier_size=len(
                        next_frontier,
                    ),
                    visited_count=visited_count,
                    links_scanned=links_scanned,
                    elapsed_s=perf_counter() - start_time,
                ),
            )
        frontier = next_frontier
        last_frontier = frontier

    return BfsFarthestResult(
        origin_node_id=origin_node_id,
        farthest_node_id=_select_frontier_node(
            last_frontier,
            rng,
        ),
        direction=direction,
        distance=distance,
        visited_count=visited_count,
        links_scanned=links_scanned,
        max_frontier_size=max_frontier_size,
        exhausted=exhausted,
        elapsed_s=perf_counter() - start_time,
    )


def _find_farthest_reachable_node_generic(
    *,
    graph: SweepGraph,
    origin_node_id: int,
    direction: SweepDirection,
    rng: Random | None,
    max_depth: int | None,
    progress_callback: Callable[[BfsSweepProgress], None] | None,
) -> BfsFarthestResult:
    neighbor_iter = _generic_neighbor_iter(
        graph,
        direction,
    )
    start_time = perf_counter()
    visited = bytearray(
        graph.node_count,
    )
    visited[origin_node_id] = 1
    frontier = array(
        "I",
        [origin_node_id],
    )
    last_frontier = frontier
    distance = 0
    visited_count = 1
    links_scanned = 0
    max_frontier_size = 1
    exhausted = True

    while frontier:
        if max_depth is not None and distance >= max_depth:
            exhausted = False
            break

        next_frontier = array(
            "I",
        )
        for node_id in frontier:
            for neighbor_node_id in neighbor_iter(
                node_id,
            ):
                links_scanned += 1
                if not visited[neighbor_node_id]:
                    visited[neighbor_node_id] = 1
                    next_frontier.append(
                        neighbor_node_id,
                    )

        if not next_frontier:
            break

        distance += 1
        visited_count += len(
            next_frontier,
        )
        max_frontier_size = max(
            max_frontier_size,
            len(
                next_frontier,
            ),
        )
        if progress_callback is not None:
            progress_callback(
                BfsSweepProgress(
                    origin_node_id=origin_node_id,
                    direction=direction,
                    distance=distance,
                    frontier_size=len(
                        frontier,
                    ),
                    next_frontier_size=len(
                        next_frontier,
                    ),
                    visited_count=visited_count,
                    links_scanned=links_scanned,
                    elapsed_s=perf_counter() - start_time,
                ),
            )
        frontier = next_frontier
        last_frontier = frontier

    return BfsFarthestResult(
        origin_node_id=origin_node_id,
        farthest_node_id=_select_frontier_node(
            last_frontier,
            rng,
        ),
        direction=direction,
        distance=distance,
        visited_count=visited_count,
        links_scanned=links_scanned,
        max_frontier_size=max_frontier_size,
        exhausted=exhausted,
        elapsed_s=perf_counter() - start_time,
    )


def _select_frontier_node(
    frontier: array[int],
    rng: Random | None,
) -> int:
    if not frontier:
        raise ValueError(
            "cannot select from an empty frontier",
        )
    if rng is None:
        return int(
            frontier[0],
        )
    return int(
        frontier[
            rng.randrange(
                len(
                    frontier,
                ),
            )
        ],
    )


def _mapped_sections(
    graph: MappedBinarySolverGraph,
    direction: SweepDirection,
) -> tuple[int, int]:
    if direction == "outgoing":
        return graph.header.out_offsets_off, graph.header.out_neighbors_off
    if direction == "incoming":
        return graph.header.in_offsets_off, graph.header.in_neighbors_off
    raise ValueError(
        f"unknown sweep direction: {direction}",
    )


def _generic_neighbor_iter(
    graph: SweepGraph,
    direction: SweepDirection,
) -> Callable[[int], Iterable[int]]:
    if direction == "outgoing":
        return graph.iter_outgoing_neighbors
    if direction == "incoming":
        return graph.iter_incoming_neighbors
    raise ValueError(
        f"unknown sweep direction: {direction}",
    )
