from __future__ import annotations

import json
from pathlib import Path

from wikiarena.graph.channel import (
    build_graph_channel_manifest,
    graph_channel_manifest_from_dict,
    graph_channel_manifest_key,
    load_graph_channel_manifest,
)
from wikiarena.graph.release import build_graph_release_metadata
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


def test_build_graph_channel_manifest_defaults_release_fields(
    tmp_path: Path,
) -> None:
    graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    compressed_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin.xz"
    write_solver_binary(
        file_path=graph_path,
        data=_make_toy_solver_binary_data(),
    )
    compressed_path.write_bytes(b"compressed")

    release_metadata = build_graph_release_metadata(
        graph_file_path=graph_path,
        compressed_file_path=compressed_path,
        dump_date="20260301",
        snapshot_id=None,
        wiki="enwiki",
        git_sha="abc123",
    )

    manifest = build_graph_channel_manifest(
        channel="production",
        release_metadata=release_metadata,
        graph_key="graphs/enwiki/20260301/wikiarena_graph_enwiki_20260301.bin",
        checksum_key="graphs/enwiki/20260301/wikiarena_graph_enwiki_20260301.bin.sha256",
        metadata_key="graphs/enwiki/20260301/wikiarena_graph_enwiki_20260301.metadata.json",
        promoted_at_utc="2026-04-19T00:00:00+00:00",
        promoted_by="hunter",
        source_run_id="24012107911",
    )

    assert manifest.channel == "production"
    assert manifest.wiki == "enwiki"
    assert manifest.dump_date == "20260301"
    assert manifest.snapshot_id == "enwiki-20260301"
    assert manifest.source_release_tag == "graph-enwiki-20260301"
    assert manifest.source_run_id == "24012107911"


def test_graph_channel_manifest_round_trips_from_disk(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "production.json"
    manifest_payload = {
        "channel": "production",
        "wiki": "enwiki",
        "dump_date": "20260401",
        "snapshot_id": "enwiki-20260401",
        "graph_key": "graphs/enwiki/20260401/wikiarena_graph_enwiki_20260401.bin",
        "checksum_key": "graphs/enwiki/20260401/wikiarena_graph_enwiki_20260401.bin.sha256",
        "metadata_key": "graphs/enwiki/20260401/wikiarena_graph_enwiki_20260401.metadata.json",
        "promoted_at_utc": "2026-04-19T00:00:00+00:00",
        "promoted_by": "hunter",
        "source_release_tag": "graph-enwiki-20260401",
        "source_run_id": "24012107911",
    }
    manifest_path.write_text(
        json.dumps(
            manifest_payload,
        )
        + "\n",
        encoding="utf-8",
    )

    manifest = load_graph_channel_manifest(
        manifest_path,
    )

    assert manifest == graph_channel_manifest_from_dict(
        manifest_payload,
    )
    assert manifest.source_release_tag == "graph-enwiki-20260401"


def test_graph_channel_manifest_key_builds_channel_path() -> None:
    assert graph_channel_manifest_key(
        wiki="enwiki",
        channel="production",
    ) == "graphs/enwiki/channels/production.json"
