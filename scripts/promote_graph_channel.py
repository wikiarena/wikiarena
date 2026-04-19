from __future__ import annotations

import argparse
import json
from pathlib import Path

from wikiarena.graph.channel import build_graph_channel_manifest
from wikiarena.graph.release import load_graph_release_metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a graph channel manifest from a graph metadata file.",
    )
    parser.add_argument(
        "--channel",
        type=str,
        required=True,
        help="Channel name to publish, e.g. production",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        required=True,
        help="Local graph metadata JSON path",
    )
    parser.add_argument(
        "--graph-key",
        type=str,
        required=True,
        help="S3 object key for the raw graph binary",
    )
    parser.add_argument(
        "--checksum-key",
        type=str,
        required=True,
        help="S3 object key for the raw graph checksum file",
    )
    parser.add_argument(
        "--metadata-key",
        type=str,
        required=True,
        help="S3 object key for the graph metadata file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output manifest path",
    )
    parser.add_argument(
        "--promoted-by",
        type=str,
        default=None,
        help="Actor or system promoting the graph",
    )
    parser.add_argument(
        "--source-release-tag",
        type=str,
        default=None,
        help="Optional source release tag override",
    )
    parser.add_argument(
        "--source-run-id",
        type=str,
        default=None,
        help="Optional GitHub Actions run id",
    )
    parser.add_argument(
        "--promoted-at-utc",
        type=str,
        default=None,
        help="Optional ISO timestamp override",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    release_metadata = load_graph_release_metadata(
        args.metadata,
    )
    manifest = build_graph_channel_manifest(
        channel=args.channel,
        release_metadata=release_metadata,
        graph_key=args.graph_key,
        checksum_key=args.checksum_key,
        metadata_key=args.metadata_key,
        promoted_at_utc=args.promoted_at_utc,
        promoted_by=args.promoted_by,
        source_release_tag=args.source_release_tag,
        source_run_id=args.source_run_id,
    )
    args.output.write_text(
        json.dumps(
            manifest.to_dict(),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
