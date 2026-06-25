from __future__ import annotations

import argparse
import json
from pathlib import Path

from wikiarena.analysis.taskset_candidates import default_task_candidate_seed
from wikiarena.analysis.taskset_pool import (
    default_task_candidate_worker_count,
    generate_task_candidate_pool,
    write_task_candidate_pool_jsonl,
)
from wikiarena.wiki_runtime import (
    infer_snapshot_id_from_graph_path,
    resolve_graph_file_path,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a process-parallel pool of reachable WikiArena task candidates.",
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
        help="Output JSONL path for candidate pool rows",
    )
    parser.add_argument(
        "--candidate-count",
        required=True,
        type=int,
        help="Number of reachable candidate rows to generate",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=default_task_candidate_seed(),
        help="Base seed for reproducible worker sampling. Defaults to today's date in YYYYMMDD form.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=default_task_candidate_worker_count(),
        help="Process count for candidate generation",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="Language code stored on generated TaskSpec records",
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

    graph_path = resolve_graph_file_path(
        args.graph,
    )
    solver_snapshot_id = infer_snapshot_id_from_graph_path(
        graph_path,
    )
    result = generate_task_candidate_pool(
        graph_path=graph_path,
        candidate_count=args.candidate_count,
        language=args.language,
        base_seed=args.seed,
        worker_count=args.workers,
        solver_snapshot_id=solver_snapshot_id,
    )
    write_task_candidate_pool_jsonl(
        result.candidates,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "output_path": str(args.output),
                **result.build_summary(),
            },
            indent=2,
        ),
    )


if __name__ == "__main__":
    main()
