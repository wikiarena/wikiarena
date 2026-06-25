from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Iterable

from wikiarena.analysis.graph_sweep import (
    alternating_sweeps,
    find_farthest_reachable_node,
    outgoing_candidate_endpoints,
)


@dataclass(frozen=True)
class ToyGraph:
    outgoing: tuple[tuple[int, ...], ...]
    incoming: tuple[tuple[int, ...], ...]

    @property
    def node_count(
        self,
    ) -> int:
        return len(
            self.outgoing,
        )

    def iter_outgoing_neighbors(
        self,
        node_id: int,
    ) -> Iterable[int]:
        return iter(
            self.outgoing[node_id],
        )

    def iter_incoming_neighbors(
        self,
        node_id: int,
    ) -> Iterable[int]:
        return iter(
            self.incoming[node_id],
        )


def test_outgoing_sweep_finds_farthest_reachable_node() -> None:
    graph = _chain_with_shortcut_graph()

    result = find_farthest_reachable_node(
        graph=graph,
        origin_node_id=0,
        direction="outgoing",
    )

    assert result.farthest_node_id == 4
    assert result.distance == 4
    assert result.visited_count == 5
    assert result.exhausted is True
    assert outgoing_candidate_endpoints(
        result,
    ) == (0, 4)


def test_incoming_sweep_reports_outgoing_candidate_in_reverse() -> None:
    graph = _chain_with_shortcut_graph()

    result = find_farthest_reachable_node(
        graph=graph,
        origin_node_id=4,
        direction="incoming",
    )

    assert result.farthest_node_id == 0
    assert result.distance == 4
    assert outgoing_candidate_endpoints(
        result,
    ) == (0, 4)


def test_alternating_sweeps_switch_direction_each_round() -> None:
    graph = _chain_with_shortcut_graph()

    results = alternating_sweeps(
        graph=graph,
        start_node_id=0,
        initial_direction="outgoing",
        sweep_count=2,
        rng=Random(
            7,
        ),
    )

    assert [result.direction for result in results] == ["outgoing", "incoming"]
    assert [result.distance for result in results] == [4, 4]
    assert [
        outgoing_candidate_endpoints(
            result,
        )
        for result in results
    ] == [(0, 4), (0, 4)]


def test_sweep_can_stop_at_depth_limit() -> None:
    graph = _chain_with_shortcut_graph()

    result = find_farthest_reachable_node(
        graph=graph,
        origin_node_id=0,
        direction="outgoing",
        max_depth=2,
    )

    assert result.farthest_node_id == 2
    assert result.distance == 2
    assert result.visited_count == 3
    assert result.exhausted is False


def _chain_with_shortcut_graph() -> ToyGraph:
    # 0 -> 1 -> 2 -> 3 -> 4, plus 5 -> 4. The shortcut source proves that
    # incoming sweeps respect direction instead of treating the graph as
    # undirected.
    outgoing = (
        (1,),
        (2,),
        (3,),
        (4,),
        (),
        (4,),
    )
    incoming = (
        (),
        (0,),
        (1,),
        (2,),
        (3, 5),
        (),
    )
    return ToyGraph(
        outgoing=outgoing,
        incoming=incoming,
    )
