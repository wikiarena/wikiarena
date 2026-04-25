from __future__ import annotations

import gzip
import shutil
from pathlib import Path

import pytest

from wikiarena.solver.binary.builder import (
    build_solver_binary_from_grouped_intermediates,
    build_solver_binary_from_intermediates,
    build_solver_binary_from_intermediates_streaming,
    load_solver_binary_data_from_intermediates,
)
from wikiarena.solver.binary.io import load_solver_binary


def _write_gzip_text(
    file_path: Path,
    content: str,
) -> None:
    with gzip.open(
        file_path,
        "wt",
        encoding="utf-8",
    ) as file_handle:
        file_handle.write(
            content,
        )


def test_load_solver_binary_data_from_intermediates_builds_expected_graph(
    tmp_path: Path,
) -> None:
    pages_file_path = tmp_path / "pages.pruned.txt.gz"
    links_file_path = tmp_path / "links.normalized_ids.txt.gz"
    _write_gzip_text(
        pages_file_path,
        "10\t0\tCharlie\t0\n20\t0\tAlpha\t0\n30\t0\tBravo\t0\n40\t0\tRedirected\t1\n50\t0\tDelta\t0\n",
    )
    _write_gzip_text(
        links_file_path,
        "20\t10\n20\t30\n20\t10\n30\t50\n10\t50\n",
    )

    solver_binary_data = load_solver_binary_data_from_intermediates(
        pages_file_path=pages_file_path,
        links_file_path=links_file_path,
    )

    assert solver_binary_data.canonical_titles == (
        "Alpha",
        "Bravo",
        "Charlie",
        "Delta",
    )
    assert solver_binary_data.out_offsets == (
        0,
        2,
        3,
        4,
        4,
    )
    assert solver_binary_data.out_neighbors == (
        1,
        2,
        3,
        3,
    )
    assert solver_binary_data.in_offsets == (
        0,
        0,
        1,
        2,
        4,
    )
    assert solver_binary_data.in_neighbors == (
        0,
        0,
        1,
        2,
    )


def test_build_solver_binary_from_intermediates_writes_loadable_binary(
    tmp_path: Path,
) -> None:
    pages_file_path = tmp_path / "pages.pruned.txt.gz"
    links_file_path = tmp_path / "links.normalized_ids.txt.gz"
    output_file_path = tmp_path / "solver.bin"
    _write_gzip_text(
        pages_file_path,
        "10\t0\tCharlie\t0\n20\t0\tAlpha\t0\n30\t0\tBravo\t0\n50\t0\tDelta\t0\n",
    )
    _write_gzip_text(
        links_file_path,
        "20\t30\n20\t10\n30\t50\n10\t50\n",
    )

    build_result = build_solver_binary_from_intermediates(
        pages_file_path=pages_file_path,
        links_file_path=links_file_path,
        output_file_path=output_file_path,
    )
    loaded_binary = load_solver_binary(
        file_path=output_file_path,
    )

    assert build_result.node_count == 4
    assert build_result.edge_count == 4
    assert build_result.canonical_titles == loaded_binary.canonical_titles
    assert loaded_binary.out_neighbors == (
        1,
        2,
        3,
        3,
    )


def test_build_solver_binary_from_intermediates_streaming_matches_in_memory_export(
    tmp_path: Path,
) -> None:
    if shutil.which("sort") is None:
        pytest.skip("sort binary is required for streaming exporter test")

    pages_file_path = tmp_path / "pages.pruned.txt.gz"
    links_file_path = tmp_path / "links.normalized_ids.txt.gz"
    in_memory_output_file_path = tmp_path / "solver.in_memory.bin"
    streaming_output_file_path = tmp_path / "solver.streaming.bin"
    _write_gzip_text(
        pages_file_path,
        "10\t0\tCharlie\t0\n20\t0\tAlpha\t0\n30\t0\tBravo\t0\n40\t0\tRedirected\t1\n50\t0\tDelta\t0\n",
    )
    _write_gzip_text(
        links_file_path,
        "20\t10\n20\t30\n20\t10\n30\t50\n10\t50\n",
    )

    build_solver_binary_from_intermediates(
        pages_file_path=pages_file_path,
        links_file_path=links_file_path,
        output_file_path=in_memory_output_file_path,
    )
    build_solver_binary_from_intermediates_streaming(
        pages_file_path=pages_file_path,
        links_file_path=links_file_path,
        output_file_path=streaming_output_file_path,
        temp_dir_path=tmp_path,
    )

    assert load_solver_binary(
        file_path=streaming_output_file_path,
    ) == load_solver_binary(
        file_path=in_memory_output_file_path,
    )


def test_load_solver_binary_data_from_intermediates_rejects_redirect_edge_ids(
    tmp_path: Path,
) -> None:
    pages_file_path = tmp_path / "pages.pruned.txt.gz"
    links_file_path = tmp_path / "links.normalized_ids.txt.gz"
    _write_gzip_text(
        pages_file_path,
        "10\t0\tCharlie\t0\n20\t0\tAlpha\t0\n30\t0\tBravo\t0\n40\t0\tRedirected\t1\n50\t0\tDelta\t0\n",
    )
    _write_gzip_text(
        links_file_path,
        "40\t20\n",
    )

    with pytest.raises(
        ValueError,
        match="unknown canonical source page id 40",
    ):
        load_solver_binary_data_from_intermediates(
            pages_file_path=pages_file_path,
            links_file_path=links_file_path,
        )


def test_build_solver_binary_from_grouped_intermediates_matches_in_memory_export(
    tmp_path: Path,
) -> None:
    pages_file_path = tmp_path / "pages.pruned.txt.gz"
    links_file_path = tmp_path / "links.normalized_ids.txt.gz"
    grouped_links_by_source_file_path = tmp_path / "links.grouped_by_source_id.txt.gz"
    grouped_links_by_target_file_path = tmp_path / "links.grouped_by_target_id.txt.gz"
    in_memory_output_file_path = tmp_path / "solver.in_memory.bin"
    grouped_output_file_path = tmp_path / "solver.grouped.bin"
    _write_gzip_text(
        pages_file_path,
        "10\t0\tCharlie\t0\n20\t0\tAlpha\t0\n30\t0\tBravo\t0\n40\t0\tRedirected\t1\n50\t0\tDelta\t0\n",
    )
    _write_gzip_text(
        links_file_path,
        "20\t10\n20\t30\n20\t10\n30\t50\n10\t50\n",
    )
    _write_gzip_text(
        grouped_links_by_source_file_path,
        "10\t50\n20\t10|30\n30\t50\n",
    )
    _write_gzip_text(
        grouped_links_by_target_file_path,
        "10\t20\n30\t20\n50\t10|30\n",
    )

    build_solver_binary_from_intermediates(
        pages_file_path=pages_file_path,
        links_file_path=links_file_path,
        output_file_path=in_memory_output_file_path,
    )
    build_solver_binary_from_grouped_intermediates(
        pages_file_path=pages_file_path,
        grouped_links_by_source_file_path=grouped_links_by_source_file_path,
        grouped_links_by_target_file_path=grouped_links_by_target_file_path,
        output_file_path=grouped_output_file_path,
    )

    assert load_solver_binary(
        file_path=grouped_output_file_path,
    ) == load_solver_binary(
        file_path=in_memory_output_file_path,
    )
