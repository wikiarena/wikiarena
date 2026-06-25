from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from wikiarena.analysis.taskset_audit import (
    audit_taskset_against_live_wikipedia,
    read_taskset_jsonl,
    write_taskset_audit_jsonl,
)
from wikiarena.wikipedia import LiveWikiService


async def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit a selected taskset against live Wikipedia using each task's solver_shortest_path.",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Input JSONL path for selected TaskSpec rows",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output JSONL path for audit sidecar rows",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="Wikipedia language edition for the live audit",
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

    tasks = read_taskset_jsonl(
        args.input,
    )
    result = await audit_taskset_against_live_wikipedia(
        tasks,
        wiki_service=LiveWikiService(
            language=args.language,
        ),
    )
    write_taskset_audit_jsonl(
        result.rows,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "input_path": str(args.input),
                "output_path": str(args.output),
                "language": args.language,
                **result.build_summary(),
            },
            indent=2,
        ),
    )


if __name__ == "__main__":
    asyncio.run(
        _main(),
    )
