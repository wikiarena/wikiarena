from __future__ import annotations

import argparse
import json
from pathlib import Path

from wikiarena.graph import smoke_test_graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run basic smoke tests against a dated WikiArena graph binary.",
    )
    parser.add_argument(
        "--graph",
        type=Path,
        required=True,
        help="Path to a dated graph binary, e.g. wikiarena_graph_enwiki_20260301.bin",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results = smoke_test_graph(
        graph_file_path=args.graph,
    )

    print(
        json.dumps(
            {
                "graph_path": str(args.graph),
                "cases": results,
            },
            indent=2,
        ),
    )


if __name__ == "__main__":
    main()
