from __future__ import annotations

import argparse
import json
from pathlib import Path

from wikiarena.analysis.taskset_candidates import default_task_candidate_seed
from wikiarena.analysis.taskset_pool import read_task_candidate_pool_jsonl
from wikiarena.analysis.taskset_selection import (
    select_taskset_from_candidate_pool,
    write_selected_taskset_jsonl,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select a balanced taskset from a precomputed candidate pool.",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Input JSONL path for candidate pool rows",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output JSONL path for final TaskSpec rows",
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
        help="Selection seed for deterministic sampling within the pool",
    )
    parser.add_argument(
        "--max-distance",
        type=int,
        default=None,
        help="Optional maximum allowed shortest path length",
    )
    parser.add_argument(
        "--exclude-title-pattern",
        action="append",
        dest="exclude_title_patterns",
        default=None,
        help="Additional regex title filter applied during selection",
    )
    parser.add_argument(
        "--no-default-excludes",
        action="store_true",
        help="Do not apply the default title exclusions during selection",
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

    candidates = read_task_candidate_pool_jsonl(
        args.input,
    )
    excluded_title_patterns: tuple[str, ...]
    if args.no_default_excludes:
        excluded_title_patterns = ()
    else:
        from wikiarena.analysis.taskset_candidates import (
            DEFAULT_EXCLUDED_TITLE_PATTERNS,
        )

        excluded_title_patterns = DEFAULT_EXCLUDED_TITLE_PATTERNS
    if args.exclude_title_patterns:
        excluded_title_patterns = (
            excluded_title_patterns + tuple(
                args.exclude_title_patterns,
            )
        )

    result = select_taskset_from_candidate_pool(
        candidates,
        counts_by_distance=_parse_distance_counts(
            args.distance_counts,
        ),
        selection_seed=args.seed,
        max_distance=args.max_distance,
        excluded_title_patterns=excluded_title_patterns,
    )
    write_selected_taskset_jsonl(
        result.tasks,
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
