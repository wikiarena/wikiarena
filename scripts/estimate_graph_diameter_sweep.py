from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from random import Random
from typing import Any, Callable, TextIO

from wikiarena.analysis.graph_sweep import (
    BfsFarthestResult,
    BfsSweepProgress,
    SweepDirection,
    find_farthest_reachable_node,
    opposite_sweep_direction,
    outgoing_candidate_endpoints,
)
from wikiarena.solver.binary import MappedBinarySolverGraph
from wikiarena.wiki_runtime import (
    infer_snapshot_id_from_graph_path,
    resolve_graph_file_path,
)


def main() -> None:
    args = _parse_args()
    rng = Random(
        args.seed,
    )
    graph_path = resolve_graph_file_path(
        args.graph,
    )
    snapshot_id = infer_snapshot_id_from_graph_path(
        graph_path,
    )

    if args.jsonl_output is not None and args.jsonl_output.exists():
        if not args.overwrite:
            raise SystemExit(
                f"output path already exists: {args.jsonl_output}. "
                "Pass --overwrite to replace it.",
            )

    rows: list[dict[str, Any]] = []
    with MappedBinarySolverGraph(
        file_path=graph_path,
    ) as graph:
        print(
            (
                f"graph={graph_path} snapshot={snapshot_id} "
                f"nodes={graph.node_count:,} edges={graph.edge_count:,}"
            ),
            file=sys.stderr,
        )
        start_node_ids = _resolve_start_node_ids(
            graph=graph,
            starts=args.starts,
            start_node_id=args.start_node_id,
            start_title=args.start_title,
            initial_direction=args.initial_direction,
            min_start_degree=args.min_start_degree,
            rng=rng,
        )

        jsonl_handle: TextIO | None = None
        try:
            if args.jsonl_output is not None:
                jsonl_handle = args.jsonl_output.open(
                    "w",
                    encoding="utf-8",
                )

            for trial_index, start_node_id in enumerate(
                start_node_ids,
                start=1,
            ):
                current_node_id = start_node_id
                current_direction = args.initial_direction
                for sweep_index in range(
                    1,
                    args.sweeps + 1,
                ):
                    print(
                        (
                            f"trial={trial_index} sweep={sweep_index} "
                            f"direction={current_direction} "
                            f"origin={current_node_id} "
                            f"title={graph.title_for_node_id(current_node_id)!r}"
                        ),
                        file=sys.stderr,
                    )
                    result = find_farthest_reachable_node(
                        graph=graph,
                        origin_node_id=current_node_id,
                        direction=current_direction,
                        rng=rng,
                        max_depth=args.max_depth,
                        progress_callback=_build_progress_callback(
                            trial_index=trial_index,
                            sweep_index=sweep_index,
                            progress_seconds=args.progress_seconds,
                        ),
                    )
                    row = _result_row(
                        graph=graph,
                        graph_path=graph_path,
                        snapshot_id=snapshot_id,
                        trial_index=trial_index,
                        sweep_index=sweep_index,
                        result=result,
                    )
                    rows.append(
                        row,
                    )
                    if jsonl_handle is not None:
                        jsonl_handle.write(
                            json.dumps(
                                row,
                                ensure_ascii=False,
                            )
                            + "\n",
                        )
                        jsonl_handle.flush()

                    candidate = row["outgoing_path_candidate"]
                    print(
                        (
                            f"  distance={result.distance} "
                            f"visited={result.visited_count:,} "
                            f"links_scanned={result.links_scanned:,} "
                            f"exhausted={result.exhausted} "
                            f"candidate={candidate['source_title']!r} "
                            f"-> {candidate['target_title']!r}"
                        ),
                        file=sys.stderr,
                    )
                    current_node_id = result.farthest_node_id
                    current_direction = opposite_sweep_direction(
                        current_direction,
                    )
        finally:
            if jsonl_handle is not None:
                jsonl_handle.close()

    print(
        json.dumps(
            _summary(
                graph_path=graph_path,
                snapshot_id=snapshot_id,
                rows=rows,
            ),
            ensure_ascii=False,
            indent=2,
        ),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Estimate a finite directed graph diameter lower bound with "
            "alternating BFS sweeps over a WikiArena graph binary."
        ),
    )
    parser.add_argument(
        "--graph",
        type=Path,
        default=None,
        help=(
            "Path to a dated graph binary. Defaults to WIKIARENA_GRAPH_PATH or "
            "the newest installed WikiArena graph."
        ),
    )
    parser.add_argument(
        "--starts",
        type=int,
        default=1,
        help="Number of random start pages to try.",
    )
    parser.add_argument(
        "--sweeps",
        type=int,
        default=2,
        help="Number of alternating sweeps per start.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed for reproducible starts and farthest-node sampling.",
    )
    parser.add_argument(
        "--initial-direction",
        choices=("outgoing", "incoming"),
        default="outgoing",
        help="Direction for the first sweep. Later sweeps alternate direction.",
    )
    parser.add_argument(
        "--start-node-id",
        type=int,
        default=None,
        help="Explicit start node id. Cannot be combined with --start-title.",
    )
    parser.add_argument(
        "--start-title",
        default=None,
        help="Explicit start title. Cannot be combined with --start-node-id.",
    )
    parser.add_argument(
        "--min-start-degree",
        type=int,
        default=1,
        help="Minimum degree required when choosing random starts.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Optional depth cap for smoke tests. A capped result is not exhausted.",
    )
    parser.add_argument(
        "--progress-seconds",
        type=float,
        default=10.0,
        help="Minimum seconds between progress lines. Use 0 to disable.",
    )
    parser.add_argument(
        "--jsonl-output",
        type=Path,
        default=None,
        help="Optional path for per-sweep JSONL rows.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite --jsonl-output if it already exists.",
    )
    args = parser.parse_args()

    if args.starts < 1:
        parser.error(
            "--starts must be at least 1",
        )
    if args.sweeps < 1:
        parser.error(
            "--sweeps must be at least 1",
        )
    if args.min_start_degree < 0:
        parser.error(
            "--min-start-degree cannot be negative",
        )
    if args.max_depth is not None and args.max_depth < 0:
        parser.error(
            "--max-depth cannot be negative",
        )
    if args.start_node_id is not None and args.start_title is not None:
        parser.error(
            "--start-node-id and --start-title cannot be combined",
        )
    if (
        args.start_node_id is not None or args.start_title is not None
    ) and args.starts != 1:
        parser.error(
            "explicit starts require --starts 1",
        )
    return args


def _resolve_start_node_ids(
    *,
    graph: MappedBinarySolverGraph,
    starts: int,
    start_node_id: int | None,
    start_title: str | None,
    initial_direction: SweepDirection,
    min_start_degree: int,
    rng: Random,
) -> tuple[int, ...]:
    if start_node_id is not None:
        if start_node_id < 0 or start_node_id >= graph.node_count:
            raise SystemExit(
                f"start node id out of range: {start_node_id}",
            )
        return (start_node_id,)

    if start_title is not None:
        resolved_node_id = graph.find_node_id(
            start_title,
        )
        if resolved_node_id is None:
            raise SystemExit(
                f"unknown graph title: {start_title!r}",
            )
        return (resolved_node_id,)

    return tuple(
        _random_node_with_degree(
            graph=graph,
            direction=initial_direction,
            min_degree=min_start_degree,
            rng=rng,
        )
        for _ in range(
            starts,
        )
    )


def _random_node_with_degree(
    *,
    graph: MappedBinarySolverGraph,
    direction: SweepDirection,
    min_degree: int,
    rng: Random,
) -> int:
    if min_degree == 0:
        return rng.randrange(
            graph.node_count,
        )

    degree_fn = (
        graph.outgoing_degree if direction == "outgoing" else graph.incoming_degree
    )
    for _ in range(
        100_000,
    ):
        node_id = rng.randrange(
            graph.node_count,
        )
        if (
            degree_fn(
                node_id,
            )
            >= min_degree
        ):
            return node_id

    start = rng.randrange(
        graph.node_count,
    )
    for offset in range(
        graph.node_count,
    ):
        node_id = (start + offset) % graph.node_count
        if (
            degree_fn(
                node_id,
            )
            >= min_degree
        ):
            return node_id

    raise SystemExit(
        f"no node found with {direction} degree >= {min_degree}",
    )


def _build_progress_callback(
    *,
    trial_index: int,
    sweep_index: int,
    progress_seconds: float,
) -> Callable[[BfsSweepProgress], None] | None:
    if progress_seconds <= 0:
        return None

    last_elapsed_s = 0.0

    def progress(
        event: BfsSweepProgress,
    ) -> None:
        nonlocal last_elapsed_s
        if event.elapsed_s - last_elapsed_s < progress_seconds:
            return
        last_elapsed_s = event.elapsed_s
        print(
            (
                f"  progress trial={trial_index} sweep={sweep_index} "
                f"distance={event.distance} "
                f"frontier={event.next_frontier_size:,} "
                f"visited={event.visited_count:,} "
                f"links_scanned={event.links_scanned:,} "
                f"elapsed={event.elapsed_s:.1f}s"
            ),
            file=sys.stderr,
        )

    return progress


def _result_row(
    *,
    graph: MappedBinarySolverGraph,
    graph_path: Path,
    snapshot_id: str | None,
    trial_index: int,
    sweep_index: int,
    result: BfsFarthestResult,
) -> dict[str, Any]:
    source_node_id, target_node_id = outgoing_candidate_endpoints(
        result,
    )
    return {
        "graph_path": str(
            graph_path,
        ),
        "snapshot_id": snapshot_id,
        "trial_index": trial_index,
        "sweep_index": sweep_index,
        **asdict(
            result,
        ),
        "origin_title": graph.title_for_node_id(
            result.origin_node_id,
        ),
        "farthest_title": graph.title_for_node_id(
            result.farthest_node_id,
        ),
        "outgoing_path_candidate": {
            "source_node_id": source_node_id,
            "source_title": graph.title_for_node_id(
                source_node_id,
            ),
            "target_node_id": target_node_id,
            "target_title": graph.title_for_node_id(
                target_node_id,
            ),
            "distance": result.distance,
            "exact_if_exhausted": result.exhausted,
        },
    }


def _summary(
    *,
    graph_path: Path,
    snapshot_id: str | None,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    best_row = max(
        rows,
        key=lambda row: row["distance"],
        default=None,
    )
    return {
        "graph_path": str(
            graph_path,
        ),
        "snapshot_id": snapshot_id,
        "sweep_count": len(
            rows,
        ),
        "best_distance": None if best_row is None else best_row["distance"],
        "best_outgoing_path_candidate": None
        if best_row is None
        else best_row["outgoing_path_candidate"],
        "rows": rows,
    }


if __name__ == "__main__":
    main()
