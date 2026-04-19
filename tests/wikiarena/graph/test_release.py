from __future__ import annotations

import json
from pathlib import Path

import pytest

from wikiarena.graph.release import (
    build_graph_release_metadata,
    graph_release_metadata_from_dict,
    load_graph_release_metadata,
)
from wikiarena.solver.binary.io import SolverBinaryData, write_solver_binary


def _make_toy_solver_binary_data() -> SolverBinaryData:
    return SolverBinaryData(
        canonical_titles=(
            "Alpha",
            "Bravo",
            "Charlie",
            "Delta",
            "Echo",
            "Foxtrot",
        ),
        out_offsets=(0, 2, 3, 4, 5, 5, 5),
        out_neighbors=(1, 2, 3, 3, 4),
        in_offsets=(0, 0, 1, 2, 4, 5, 5),
        in_neighbors=(0, 0, 1, 2, 3),
    )


def test_load_graph_release_metadata_round_trips_from_disk(
    tmp_path: Path,
) -> None:
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    compressed_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin.xz"
    metadata_path = tmp_path / "wikiarena_graph_enwiki_20260301.metadata.json"
    write_solver_binary(
        file_path=graph_path,
        data=_make_toy_solver_binary_data(),
    )
    compressed_path.write_bytes(b"compressed-graph")

    expected_metadata = build_graph_release_metadata(
        graph_file_path=graph_path,
        compressed_file_path=compressed_path,
        dump_date="20260301",
        snapshot_id="enwiki-20260301",
        wiki="enwiki",
        git_sha="abc123",
    )
    metadata_path.write_text(
        json.dumps(
            expected_metadata.to_dict(),
        )
        + "\n",
        encoding="utf-8",
    )

    loaded_metadata = load_graph_release_metadata(
        metadata_path,
    )

    assert loaded_metadata == expected_metadata


def test_graph_release_metadata_from_dict_rejects_missing_graph_payload() -> None:
    with pytest.raises(
        ValueError,
        match="metadata field graph must be an object",
    ):
        graph_release_metadata_from_dict(
            {
                "wiki": "enwiki",
                "dump_date": "20260301",
                "generated_at_utc": "2026-04-19T00:00:00+00:00",
                "compressed": {
                    "file_name": "wikiarena_graph_enwiki_20260301.bin.xz",
                    "bytes": 42,
                    "sha256": "compressed-sha",
                },
            },
        )
