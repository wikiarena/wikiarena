from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CsrGraphArrays:
    out_offsets: tuple[int, ...]
    out_neighbors: tuple[int, ...]
    in_offsets: tuple[int, ...]
    in_neighbors: tuple[int, ...]


def build_csr_graph_arrays(
    *,
    node_count: int,
    edges: tuple[tuple[int, int], ...],
) -> CsrGraphArrays:
    if node_count < 0:
        raise ValueError(
            f"node count cannot be negative: {node_count}",
        )

    outgoing_sets = [set() for _ in range(node_count)]
    incoming_sets = [set() for _ in range(node_count)]

    for source_id, target_id in edges:
        if source_id < 0 or source_id >= node_count:
            raise ValueError(
                f"source node id out of range: {source_id}",
            )
        if target_id < 0 or target_id >= node_count:
            raise ValueError(
                f"target node id out of range: {target_id}",
            )
        outgoing_sets[source_id].add(
            target_id,
        )
        incoming_sets[target_id].add(
            source_id,
        )

    out_offsets, out_neighbors = _build_offsets_and_neighbors(
        adjacency_sets=outgoing_sets,
    )
    in_offsets, in_neighbors = _build_offsets_and_neighbors(
        adjacency_sets=incoming_sets,
    )
    return CsrGraphArrays(
        out_offsets=out_offsets,
        out_neighbors=out_neighbors,
        in_offsets=in_offsets,
        in_neighbors=in_neighbors,
    )


def _build_offsets_and_neighbors(
    *,
    adjacency_sets: list[set[int]],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    offsets = [0]
    neighbors: list[int] = []

    for adjacency_set in adjacency_sets:
        neighbors.extend(
            sorted(
                adjacency_set,
            ),
        )
        offsets.append(
            len(neighbors),
        )

    return tuple(offsets), tuple(neighbors)
