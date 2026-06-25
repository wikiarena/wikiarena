from __future__ import annotations

import argparse
import json
import sys
from array import array
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

from wikiarena.solver.binary import (
    MappedBinarySolverGraph,
    search_shortest_path_by_node_ids,
)
from wikiarena.solver.binary.mapped_graph import U32_STRUCT
from wikiarena.wiki_runtime import (
    infer_snapshot_id_from_graph_path,
    resolve_graph_file_path,
)

SweepDirection = Literal["outgoing", "incoming"]

DEFAULT_SOURCE_TITLE = "Yu ssi samdaerok"
DEFAULT_TARGET_TITLE = "2009 California League season"
DEFAULT_RANDOM_PAIR_SUMMARY = Path(
    "artifacts/diameter/random_pair_lengths_100k_seed42_summary.json",
)
DEFAULT_OUTPUT_PATH = Path("frontend/public/data/diameter-explorer.json")


def main() -> None:
    args = _parse_args()
    graph_paths = args.graph or [
        resolve_graph_file_path(
            None,
        ),
    ]
    snapshots = []
    for graph_path in graph_paths:
        snapshots.append(
            _build_snapshot_payload(
                graph_path=graph_path,
                source_title=args.source_title,
                target_title=args.target_title,
                direction=args.direction,
            ),
        )

    payload = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "methodNote": (
            "The witness path is an exact shortest path for the listed page pair. "
            "It is a diameter lower bound, not an exact global diameter proof."
        ),
        "snapshots": snapshots,
        "randomPairHistogram": _read_random_pair_histogram(args.random_pair_summary),
        "priorWork": [
            {
                "title": "Fast diameter and radius BFS-based computation in real-world graphs",
                "url": "https://doi.org/10.1016/j.tcs.2015.02.033",
            },
            {
                "title": "SNAP English Wikipedia hyperlink network",
                "url": "https://snap.stanford.edu/data/enwiki-2013.html",
            },
            {
                "title": "The Difficulty of Path Traversal in Information Networks",
                "url": "https://research.thewikigame.com/papers/the-difficulty-of-path-traversal-in-information-networks.pdf",
            },
        ],
    }
    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.output.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.output}",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate static data for the WikiArena diameter explorer page.",
    )
    parser.add_argument(
        "--graph",
        type=Path,
        nargs="+",
        default=None,
        help=(
            "Graph binaries to include. Defaults to WIKIARENA_GRAPH_PATH "
            "or the latest installed graph."
        ),
    )
    parser.add_argument(
        "--source-title",
        default=DEFAULT_SOURCE_TITLE,
        help="Witness source page title.",
    )
    parser.add_argument(
        "--target-title",
        default=DEFAULT_TARGET_TITLE,
        help="Witness target page title.",
    )
    parser.add_argument(
        "--direction",
        choices=("outgoing", "incoming"),
        default="outgoing",
        help="Wavefront expansion direction.",
    )
    parser.add_argument(
        "--random-pair-summary",
        type=Path,
        default=DEFAULT_RANDOM_PAIR_SUMMARY,
        help="Random-pair shortest-path summary JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Output JSON path.",
    )
    return parser.parse_args()


def _build_snapshot_payload(
    *,
    graph_path: Path,
    source_title: str,
    target_title: str,
    direction: SweepDirection,
) -> dict[str, object]:
    with MappedBinarySolverGraph(
        file_path=graph_path,
    ) as graph:
        source_node_id = graph.find_node_id(
            source_title,
        )
        target_node_id = graph.find_node_id(
            target_title,
        )
        if source_node_id is None:
            raise SystemExit(
                f"unknown source title in {graph_path}: {source_title!r}",
            )
        if target_node_id is None:
            raise SystemExit(
                f"unknown target title in {graph_path}: {target_title!r}",
            )

        shortest_path_result = search_shortest_path_by_node_ids(
            graph,
            start_node_id=source_node_id,
            target_node_id=target_node_id,
        )
        if shortest_path_result.path_node_ids is None:
            raise SystemExit(
                f"no path from {source_title!r} to {target_title!r} in {graph_path}",
            )

        print(
            (
                f"building wavefront snapshot={infer_snapshot_id_from_graph_path(graph_path)} "
                f"source={source_title!r} target={target_title!r}"
            ),
            file=sys.stderr,
        )
        wavefront = _build_wavefront(
            graph=graph,
            origin_node_id=source_node_id,
            target_node_id=target_node_id,
            direction=direction,
        )

        return {
            "snapshotId": infer_snapshot_id_from_graph_path(graph_path),
            "nodeCount": graph.node_count,
            "edgeCount": graph.edge_count,
            "witness": {
                "sourceTitle": graph.title_for_node_id(
                    source_node_id,
                ),
                "targetTitle": graph.title_for_node_id(
                    target_node_id,
                ),
                "sourceNodeId": source_node_id,
                "targetNodeId": target_node_id,
                "distance": shortest_path_result.path_length,
                "pagesVisited": shortest_path_result.pages_visited,
                "linksScanned": shortest_path_result.links_scanned,
                "pathTitles": [
                    graph.title_for_node_id(
                        node_id,
                    )
                    for node_id in shortest_path_result.path_node_ids
                ],
                "solverUrl": (
                    "./solver.html?"
                    + urlencode(
                        {
                            "start": source_title,
                            "target": target_title,
                            "mode": "all_shortest",
                        },
                    )
                ),
            },
            "wavefront": {
                "originTitle": graph.title_for_node_id(
                    source_node_id,
                ),
                "targetTitle": graph.title_for_node_id(
                    target_node_id,
                ),
                "direction": direction,
                "targetDistance": shortest_path_result.path_length,
                "reachablePages": wavefront["reachablePages"],
                "linksScanned": wavefront["linksScanned"],
                "layers": wavefront["layers"],
            },
        }


def _build_wavefront(
    *,
    graph: MappedBinarySolverGraph,
    origin_node_id: int,
    target_node_id: int,
    direction: SweepDirection,
) -> dict[str, object]:
    offsets_off, neighbors_off = _mapped_sections(
        graph,
        direction,
    )
    mapped_bytes = graph._mapped_bytes
    visited = bytearray(
        graph.node_count,
    )
    visited[origin_node_id] = 1
    frontier = array(
        "I",
        [origin_node_id],
    )
    distance = 0
    visited_count = 1
    cumulative_links_scanned = 0
    target_distance = 0 if origin_node_id == target_node_id else None
    layers: list[dict[str, int | bool]] = []

    while frontier:
        next_frontier = array(
            "I",
        )
        layer_links_scanned = 0
        for node_id in frontier:
            start = U32_STRUCT.unpack_from(
                mapped_bytes,
                offsets_off + (node_id * U32_STRUCT.size),
            )[0]
            end = U32_STRUCT.unpack_from(
                mapped_bytes,
                offsets_off + ((node_id + 1) * U32_STRUCT.size),
            )[0]
            layer_links_scanned += end - start
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
                    if neighbor_node_id == target_node_id and target_distance is None:
                        target_distance = distance + 1
                byte_offset += 3

        cumulative_links_scanned += layer_links_scanned
        layers.append(
            {
                "distance": distance,
                "frontierSize": len(
                    frontier,
                ),
                "newPagesDiscovered": len(
                    next_frontier,
                ),
                "linksScanned": layer_links_scanned,
                "cumulativePages": visited_count
                + len(
                    next_frontier,
                ),
                "cumulativeLinksScanned": cumulative_links_scanned,
                "targetOnFrontier": target_distance == distance,
            },
        )
        print(
            (
                f"  layer={distance:>2} frontier={len(frontier):,} "
                f"next={len(next_frontier):,} links={layer_links_scanned:,}"
            ),
            file=sys.stderr,
        )

        if not next_frontier:
            break
        visited_count += len(
            next_frontier,
        )
        frontier = next_frontier
        distance += 1

    return {
        "reachablePages": visited_count,
        "linksScanned": cumulative_links_scanned,
        "targetDistance": target_distance,
        "layers": layers,
    }


def _mapped_sections(
    graph: MappedBinarySolverGraph,
    direction: SweepDirection,
) -> tuple[int, int]:
    if direction == "outgoing":
        return graph.header.out_offsets_off, graph.header.out_neighbors_off
    return graph.header.in_offsets_off, graph.header.in_neighbors_off


def _read_random_pair_histogram(
    summary_path: Path,
) -> dict[str, object]:
    summary = json.loads(
        summary_path.read_text(
            encoding="utf-8",
        ),
    )
    return {
        "sampleSize": summary["sample_size"],
        "seed": summary["seed"],
        "reachablePairs": summary["reachable_pairs"],
        "unreachablePairs": summary["unreachable_pairs"],
        "reachableShare": summary["reachable_share"],
        "histogram": [
            {
                "distance": int(
                    distance,
                ),
                "count": values["count"],
                "shareOfReachablePairs": values["share_of_reachable_pairs"],
            }
            for distance, values in sorted(
                summary["length_histogram"].items(),
                key=lambda item: int(
                    item[0],
                ),
            )
        ],
    }


if __name__ == "__main__":
    main()
