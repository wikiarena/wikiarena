from __future__ import annotations

import argparse
import json
from pathlib import Path

from wikiarena.graph import smoke_test_graph
from wikiarena.wiki_runtime import resolve_graph_file_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run basic smoke tests against a dated WikiArena graph binary.",
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    graph_path = resolve_graph_file_path(
        args.graph,
    )
    results = smoke_test_graph(
        graph_file_path=graph_path,
    )

    print(
        json.dumps(
            {
                "graph_path": str(graph_path),
                "cases": results,
            },
            indent=2,
        ),
    )


if __name__ == "__main__":
    main()
