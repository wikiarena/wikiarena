from __future__ import annotations

import json
from pathlib import Path

import pytest

import wikiarena.graph.info as graph_info
from wikiarena.graph import build_graph_release_metadata, graph_file_name
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


def test_load_graph_info_reports_active_installed_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph_path = tmp_path / graph_file_name(
        wiki="enwiki",
        dump_date="20260301",
    )
    metadata_path = tmp_path / "wikiarena_graph_enwiki_20260301.metadata.json"
    write_solver_binary(
        file_path=graph_path,
        data=_make_toy_solver_binary_data(),
    )
    metadata_path.write_text(
        json.dumps(
            build_graph_release_metadata(
                graph_file_path=graph_path,
                compressed_file_path=graph_path,
                dump_date="20260301",
                snapshot_id="enwiki-20260301",
                wiki="enwiki",
                git_sha="abc123",
            ).to_dict(),
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "wikiarena.wiki_runtime.get_default_graph_install_dir",
        lambda: tmp_path,
    )
    monkeypatch.delenv("WIKIARENA_GRAPH_PATH", raising=False)

    info = graph_info.load_graph_info()

    assert info.selected_via == "installed_latest"
    assert info.graph_path == graph_path.resolve()
    assert info.metadata_path == metadata_path.resolve()
    assert info.metadata_present is True
    assert info.snapshot_id == "enwiki-20260301"
    assert info.wiki == "enwiki"
    assert info.dump_date == "20260301"
    assert info.release_tag == "graph-enwiki-20260301"
    assert info.node_count == 6
    assert info.edge_count == 5
    assert info.verified is False


def test_load_graph_info_supports_explicit_graph_without_metadata(
    tmp_path: Path,
) -> None:
    graph_path = tmp_path / graph_file_name(
        wiki="enwiki",
        dump_date="20260301",
    )
    write_solver_binary(
        file_path=graph_path,
        data=_make_toy_solver_binary_data(),
    )

    info = graph_info.load_graph_info(
        graph_path=graph_path,
    )

    assert info.selected_via == "explicit"
    assert info.metadata_present is False
    assert info.snapshot_id == "enwiki-20260301"
    assert info.release_tag == "graph-enwiki-20260301"
    assert info.verified is False


def test_load_graph_info_verify_checks_metadata(
    tmp_path: Path,
) -> None:
    graph_path = tmp_path / graph_file_name(
        wiki="enwiki",
        dump_date="20260301",
    )
    metadata_path = tmp_path / "wikiarena_graph_enwiki_20260301.metadata.json"
    write_solver_binary(
        file_path=graph_path,
        data=_make_toy_solver_binary_data(),
    )
    metadata_path.write_text(
        json.dumps(
            build_graph_release_metadata(
                graph_file_path=graph_path,
                compressed_file_path=graph_path,
                dump_date="20260301",
                snapshot_id="enwiki-20260301",
                wiki="enwiki",
                git_sha="abc123",
            ).to_dict(),
        )
        + "\n",
        encoding="utf-8",
    )

    info = graph_info.load_graph_info(
        graph_path=graph_path,
        verify=True,
    )

    assert info.verified is True
    assert info.graph_sha256 is not None


def test_load_graph_info_preserves_nonstandard_graph_basename_for_metadata(
    tmp_path: Path,
) -> None:
    graph_path = tmp_path / "custom.graph.bin"
    metadata_path = tmp_path / "custom.graph.metadata.json"
    write_solver_binary(
        file_path=graph_path,
        data=_make_toy_solver_binary_data(),
    )
    metadata_path.write_text(
        json.dumps(
            build_graph_release_metadata(
                graph_file_path=graph_path,
                compressed_file_path=graph_path,
                dump_date="20260301",
                snapshot_id="enwiki-20260301",
                wiki="enwiki",
                git_sha="abc123",
            ).to_dict(),
        )
        + "\n",
        encoding="utf-8",
    )

    info = graph_info.load_graph_info(
        graph_path=graph_path,
        verify=True,
    )

    assert info.metadata_path == metadata_path.resolve()
    assert info.verified is True
