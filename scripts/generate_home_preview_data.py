#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_TASKS = [
    ("Matcha", "Labubu"),
    ("Turing machine", "Pokémon"),
    ("Deep learning", "Singularity"),
    ("Isaac Newton", "ASML"),
    ("Mechanistic interpretability", "Hero's journey"),
    ("Unicellular organism", "Dyson sphere"),
    ("Claude Shannon", "Dune (novel)"),
    ("Thomas Kuhn", "Tensor Processing Unit"),
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate static homepage race preview paths from the solver API.",
    )
    parser.add_argument(
        "--api-base-url",
        default="http://127.0.0.1:8000",
        help="Solver API base URL.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("frontend/public/data/home-preview-races.json"),
        help="Output JSON file.",
    )
    parser.add_argument(
        "--paths-per-race",
        type=int,
        default=8,
        help="Maximum distinct-first-hop shortest paths to keep per race.",
    )
    args = parser.parse_args()

    races: list[dict[str, Any]] = []
    snapshot_id: str | None = None
    for start_title, target_title in DEFAULT_TASKS:
        response = solve(
            args.api_base_url,
            start_title=start_title,
            target_title=target_title,
        )
        snapshot_id = response.get("snapshot_id") or snapshot_id
        if response.get("path_length") not in {3, 4}:
            continue
        paths = select_preview_paths(
            response.get("paths", []),
            limit=args.paths_per_race,
        )
        if len(paths) < 2:
            continue
        races.append(
            {
                "startTitle": response["start_title"],
                "targetTitle": response["target_title"],
                "pathLength": response["path_length"],
                "paths": paths,
            },
        )

    payload = {
        "snapshotId": snapshot_id,
        "generatedAt": datetime.now(UTC).isoformat(),
        "races": races,
    }
    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def solve(api_base_url: str, *, start_title: str, target_title: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{api_base_url.rstrip('/')}/v1/solve",
        data=json.dumps(
            {
                "start_title": start_title,
                "target_title": target_title,
                "path_mode": "all_shortest",
            },
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=120,
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(
            f"Solver API rejected {start_title!r} -> {target_title!r}: "
            f"{error.status} {error.read().decode('utf-8')}",
        ) from error


def select_preview_paths(paths: list[list[str]], *, limit: int) -> list[list[str]]:
    selected: list[list[str]] = []
    seen_first_hops: set[str] = set()
    for path in paths:
        if len(path) < 3:
            continue
        first_hop = path[1]
        if first_hop in seen_first_hops:
            continue
        selected.append(path)
        seen_first_hops.add(first_hop)
        if len(selected) >= limit:
            break
    return selected


if __name__ == "__main__":
    main()
