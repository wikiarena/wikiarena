from __future__ import annotations

import argparse
import json
from pathlib import Path

from wikiarena.analysis import generate_task_candidates, write_task_candidates_jsonl
from wikiarena.analysis.taskset_candidates import default_task_candidate_seed
from wikiarena.solver.binary import MappedBinarySolverGraph
from wikiarena.wiki_runtime import (
    infer_snapshot_id_from_graph_path,
    resolve_graph_file_path,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate reproducible task candidates from a dated WikiArena graph binary.",
    )
    parser.add_argument(
        "--graph",
        type=Path,
        default=None,
        help=(
            "Path to a dated graph binary. Defaults to WIKIARENA_GRAPH_PATH "
            "or the latest installed graph."
        ),
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output JSONL path for candidate tasks",
    )
    parser.add_argument(
        "--distance-count",
        required=True,
        action="append",
        dest="distance_counts",
        help="Requested bucket in the form DISTANCE:COUNT. Repeat as needed.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=default_task_candidate_seed(),
        help="Random seed for reproducible pair sampling. Defaults to today's date in YYYYMMDD form.",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="Language code stored on generated TaskSpec records",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=100000,
        help="Maximum random pair attempts before giving up",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output file if it already exists",
    )
    args = parser.parse_args()

    if args.output.exists() and not args.overwrite:
        raise SystemExit(
            f"output path already exists: {args.output}. Pass --overwrite to replace it.",
        )

    counts_by_distance = _parse_distance_counts(
        args.distance_counts,
    )
    graph_path = resolve_graph_file_path(
        args.graph,
    )
    solver_snapshot_id = infer_snapshot_id_from_graph_path(
        graph_path,
    )

    with MappedBinarySolverGraph(
        file_path=graph_path,
    ) as graph:
        result = generate_task_candidates(
            graph,
            counts_by_distance=counts_by_distance,
            language=args.language,
            seed=args.seed,
            max_attempts=args.max_attempts,
            solver_snapshot_id=solver_snapshot_id,
        )

    write_task_candidates_jsonl(
        result.tasks,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "output_path": str(args.output),
                "seed": result.seed,
                "requested_counts_by_distance": result.requested_counts_by_distance,
                "generated_counts_by_distance": result.generated_counts_by_distance,
                "total_candidates": len(result.tasks),
                "attempts": result.attempts,
                "unique_pairs_considered": result.unique_pairs_considered,
                "solver_snapshot_id": solver_snapshot_id,
            },
            indent=2,
        ),
    )


def _parse_distance_counts(
    raw_values: list[str],
) -> dict[int, int]:
    counts_by_distance: dict[int, int] = {}
    for raw_value in raw_values:
        if ":" not in raw_value:
            raise SystemExit(
                f"invalid --distance-count value: {raw_value}. Expected DISTANCE:COUNT.",
            )
        distance_text, count_text = raw_value.split(
            ":",
            maxsplit=1,
        )
        distance = int(
            distance_text,
        )
        if distance in counts_by_distance:
            raise SystemExit(
                f"duplicate distance bucket provided: {distance}",
            )
        counts_by_distance[distance] = int(
            count_text,
        )
    return counts_by_distance


if __name__ == "__main__":
    main()
