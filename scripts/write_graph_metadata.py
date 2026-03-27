from __future__ import annotations

import argparse
import json
from pathlib import Path

from wikiarena.graph import build_graph_release_metadata, graph_metadata_file_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write release metadata for wikiarena graph artifacts.",
    )
    parser.add_argument(
        "--graph",
        type=Path,
        required=True,
        help="Path to the dated raw graph binary",
    )
    parser.add_argument(
        "--compressed",
        type=Path,
        required=True,
        help="Path to the compressed graph artifact",
    )
    parser.add_argument(
        "--dump-date",
        type=str,
        required=True,
        help="Wikimedia dump date, e.g. 20260301",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output JSON metadata path, e.g. wikiarena_graph_enwiki_20260301.metadata.json",
    )
    parser.add_argument(
        "--snapshot-id",
        type=str,
        default=None,
        help="Optional snapshot identifier to record in metadata",
    )
    parser.add_argument(
        "--wiki",
        type=str,
        default="enwiki",
        help="Wiki identifier for metadata",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    expected_metadata_name = graph_metadata_file_name(
        wiki=args.wiki,
        dump_date=args.dump_date,
    )
    if args.output.name != expected_metadata_name:
        raise ValueError(
            f"metadata output file name must be {expected_metadata_name}, got {args.output.name}",
        )
    metadata = build_graph_release_metadata(
        graph_file_path=args.graph,
        compressed_file_path=args.compressed,
        dump_date=args.dump_date,
        snapshot_id=args.snapshot_id,
        wiki=args.wiki,
    )

    args.output.write_text(
        json.dumps(
            metadata.to_dict(),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
