from __future__ import annotations

import argparse
import json
from pathlib import Path

from wikiarena.graph import (
    ProgressReporter,
    build_graph_binary,
    build_graph_from_dump,
    graph_file_name,
    resolve_dump_date,
)


def _validate_non_legacy_graph_output_path(
    output_path: Path,
) -> None:
    if output_path.name == "wikiarena_graph.bin":
        raise ValueError(
            "legacy graph file name is no longer supported; use a dated file name like wikiarena_graph_enwiki_20260301.bin",
        )


def _validate_standard_graph_output_path(
    *,
    output_path: Path,
    wiki: str,
    dump_date: str,
) -> None:
    _validate_non_legacy_graph_output_path(
        output_path,
    )
    expected_file_name = graph_file_name(
        wiki=wiki,
        dump_date=dump_date,
    )
    if output_path.name != expected_file_name:
        raise ValueError(
            f"graph output file name must be {expected_file_name}, got {output_path.name}",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the official dated WikiArena graph artifact.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output path for the dated graph binary, e.g. wikiarena_graph_enwiki_20260301.bin",
    )
    parser.add_argument(
        "--pages",
        type=Path,
        default=None,
        help="Optional path to pages.pruned.txt.gz",
    )
    parser.add_argument(
        "--grouped-source",
        type=Path,
        default=None,
        help="Optional path to links.grouped_by_source_id.txt.gz",
    )
    parser.add_argument(
        "--grouped-target",
        type=Path,
        default=None,
        help="Optional path to links.grouped_by_target_id.txt.gz",
    )
    parser.add_argument(
        "--dump-date",
        type=str,
        default=None,
        help="Optional Wikimedia dump date in YYYYMMDD format. Defaults to latest pagelinkstable dump.",
    )
    parser.add_argument(
        "--wiki",
        type=str,
        default="enwiki",
        help="Wiki dump prefix to build from",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path("dumps"),
        help="Working directory for downloaded dumps and intermediates",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    progress_reporter = ProgressReporter(
        enabled=not args.quiet,
    )
    use_existing_inputs = all(
        value is not None
        for value in (
            args.pages,
            args.grouped_source,
            args.grouped_target,
        )
    )
    if use_existing_inputs:
        with progress_reporter.step(
            f"build {args.output.name} from existing grouped inputs",
        ):
            _validate_non_legacy_graph_output_path(
                args.output,
            )
            build_result = build_graph_binary(
                pages_file_path=args.pages,
                grouped_links_by_source_file_path=args.grouped_source,
                grouped_links_by_target_file_path=args.grouped_target,
                output_file_path=args.output,
                progress_callback=progress_reporter.log,
            )
        print(
            json.dumps(
                {
                    "mode": "from-existing-inputs",
                    "output_path": str(args.output),
                    "node_count": build_result.node_count,
                    "edge_count": build_result.edge_count,
                },
                indent=2,
            ),
        )
        return

    if any(
        value is not None
        for value in (
            args.pages,
            args.grouped_source,
            args.grouped_target,
        )
    ):
        raise ValueError(
            "either provide all of --pages/--grouped-source/--grouped-target, or provide none of them",
        )

    dump_date = resolve_dump_date(
        wiki=args.wiki,
        requested_dump_date=args.dump_date,
    )
    _validate_standard_graph_output_path(
        output_path=args.output,
        wiki=args.wiki,
        dump_date=dump_date,
    )
    build_paths = build_graph_from_dump(
        wiki=args.wiki,
        dump_date=dump_date,
        output_dir=args.work_dir,
        output_file_path=args.output,
        progress_reporter=progress_reporter,
    )
    print(
        json.dumps(
            {
                "mode": "from-raw-dump",
                "wiki": args.wiki,
                "dump_date": dump_date,
                "output_path": str(build_paths.output_file_path),
                "node_count": build_paths.node_count,
                "edge_count": build_paths.edge_count,
                "pages_file_path": str(build_paths.pages_file_path),
                "grouped_links_by_source_file_path": str(
                    build_paths.grouped_links_by_source_file_path
                ),
                "grouped_links_by_target_file_path": str(
                    build_paths.grouped_links_by_target_file_path
                ),
            },
            indent=2,
        ),
    )


if __name__ == "__main__":
    main()
