from __future__ import annotations

from pathlib import Path

from wikiarena.graph import (
    build_graph_release_metadata,
    graph_file_name,
    graph_metadata_file_name,
    list_standard_graph_files,
    smoke_test_graph,
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


def test_smoke_test_graph_uses_default_cases(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "toy_graph.bin"
    write_solver_binary(
        file_path=binary_path,
        data=SolverBinaryData(
            canonical_titles=(
                "1980s",
                "Alberto_Segado",
                "Apple",
                "Atheism",
                "Byzantine_Empire",
                "Claude_Shannon",
                "Fruit",
                "List_of_Buran_missions",
                "Mir",
                "Plata_dulce",
                "The_Official_Story",
            ),
            out_offsets=(0, 1, 1, 2, 3, 3, 4, 4, 5, 6, 7, 8),
            out_neighbors=(10, 6, 4, 3, 8, 0, 1, 9),
            in_offsets=(0, 1, 2, 2, 3, 4, 4, 5, 5, 6, 7, 8),
            in_neighbors=(8, 9, 5, 3, 2, 7, 10, 0),
        ),
    )

    results = smoke_test_graph(
        graph_file_path=binary_path,
    )

    assert [result["expected_length"] for result in results] == [1, 2, 5]


def test_build_graph_release_metadata_reports_counts_and_hashes(
    tmp_path: Path,
) -> None:
    graph_path = tmp_path / "toy_graph.bin"
    compressed_path = tmp_path / "toy_graph.bin.xz"
    write_solver_binary(
        file_path=graph_path,
        data=_make_toy_solver_binary_data(),
    )
    compressed_path.write_bytes(
        b"fake-compressed-graph",
    )

    metadata = build_graph_release_metadata(
        graph_file_path=graph_path,
        compressed_file_path=compressed_path,
        dump_date="20260301",
        snapshot_id="enwiki-20260301",
    )

    assert metadata.dump_date == "20260301"
    assert metadata.snapshot_id == "enwiki-20260301"
    assert metadata.graph.node_count == 6
    assert metadata.graph.edge_count == 5
    assert metadata.graph.file_name == "toy_graph.bin"
    assert metadata.compressed.file_name == "toy_graph.bin.xz"
    assert len(metadata.graph.sha256) == 64
    assert len(metadata.compressed.sha256) == 64


def test_graph_file_name_helpers_use_dated_standard() -> None:
    assert (
        graph_file_name(wiki="enwiki", dump_date="20260301")
        == "wikiarena_graph_enwiki_20260301.bin"
    )
    assert (
        graph_metadata_file_name(wiki="enwiki", dump_date="20260301")
        == "wikiarena_graph_enwiki_20260301.metadata.json"
    )


def test_list_standard_graph_files_sorts_newest_first(
    tmp_path: Path,
) -> None:
    older_graph_path = tmp_path / "wikiarena_graph_enwiki_20260301.bin"
    newer_graph_path = tmp_path / "wikiarena_graph_enwiki_20260401.bin"
    legacy_graph_path = tmp_path / "wikiarena_graph.bin"
    older_graph_path.write_bytes(b"older")
    newer_graph_path.write_bytes(b"newer")
    legacy_graph_path.write_bytes(b"legacy")

    assert list_standard_graph_files(tmp_path) == (
        newer_graph_path,
        older_graph_path,
    )
