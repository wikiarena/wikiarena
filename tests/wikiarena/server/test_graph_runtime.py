from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from wikiarena.server.config import ServerConfig
from wikiarena.server.errors import UnknownTitleError
from wikiarena.server.graph_runtime import GraphSolverRuntime
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


def _make_multi_split_solver_binary_data() -> SolverBinaryData:
    return SolverBinaryData(
        canonical_titles=(
            "Alpha",
            "Bravo",
            "Charlie",
            "Delta",
            "Echo",
            "Foxtrot",
        ),
        out_offsets=(0, 2, 4, 6, 7, 8, 8),
        out_neighbors=(1, 2, 3, 4, 3, 4, 5, 5),
        in_offsets=(0, 0, 1, 2, 4, 6, 8),
        in_neighbors=(0, 0, 1, 2, 1, 2, 3, 4),
    )


def _write_graph_metadata(
    metadata_path: Path,
) -> None:
    metadata_path.write_text(
        json.dumps(
            {
                "wiki": "enwiki",
                "dump_date": "20260301",
                "snapshot_id": "enwiki-20260301",
                "generated_at_utc": "2026-03-24T00:00:00+00:00",
                "git_sha": "abc123",
                "graph": {
                    "file_name": "wikiarena_graph.bin",
                    "bytes": 123,
                    "sha256": "graph-sha",
                    "node_count": 6,
                    "edge_count": 5,
                },
                "compressed": {
                    "file_name": "wikiarena_graph.bin.xz",
                    "bytes": 99,
                    "sha256": "compressed-sha",
                },
            },
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_graph_solver_runtime_loads_metadata_and_solves_queries(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "wikiarena_graph.bin"
    metadata_path = tmp_path / "wikiarena_graph.metadata.json"
    write_solver_binary(
        file_path=binary_path,
        data=_make_toy_solver_binary_data(),
    )
    _write_graph_metadata(
        metadata_path,
    )

    runtime = GraphSolverRuntime(
        ServerConfig(
            graph_path=binary_path,
            graph_metadata_path=metadata_path,
            service_version="0.1.0",
        ),
    )

    await runtime.startup()

    assert runtime.is_ready() is True
    assert runtime.get_health_status() == "ok"

    meta_response = runtime.get_meta()
    assert meta_response.service_version == "0.1.0"
    assert meta_response.snapshot_id == "enwiki-20260301"
    assert meta_response.dump_date == "20260301"
    assert meta_response.node_count == 6
    assert meta_response.edge_count == 5
    assert meta_response.default_path_mode == "single"
    assert meta_response.supported_path_modes == ["single", "all_shortest"]

    solve_response = await runtime.solve(
        start_title="Alpha",
        target_title="Echo",
        path_mode="single",
    )
    assert solve_response.snapshot_id == "enwiki-20260301"
    assert solve_response.start_title == "Alpha"
    assert solve_response.target_title == "Echo"
    assert solve_response.path_length == 3
    assert solve_response.paths == [["Alpha", "Bravo", "Delta", "Echo"]]
    assert solve_response.pages_visited == 5
    assert solve_response.links_scanned == 5
    assert solve_response.solve_ms >= 0.0

    await runtime.shutdown()


@pytest.mark.asyncio
async def test_graph_solver_runtime_returns_empty_paths_for_disconnected_titles(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "wikiarena_graph.bin"
    metadata_path = tmp_path / "wikiarena_graph.metadata.json"
    write_solver_binary(
        file_path=binary_path,
        data=_make_toy_solver_binary_data(),
    )
    _write_graph_metadata(
        metadata_path,
    )

    runtime = GraphSolverRuntime(
        ServerConfig(
            graph_path=binary_path,
            graph_metadata_path=metadata_path,
            service_version="0.1.0",
        ),
    )

    await runtime.startup()

    solve_response = await runtime.solve(
        start_title="Alpha",
        target_title="Foxtrot",
        path_mode="single",
    )
    assert solve_response.path_length is None
    assert solve_response.paths == []
    assert solve_response.pages_visited == 2
    assert solve_response.links_scanned == 0

    await runtime.shutdown()


@pytest.mark.asyncio
async def test_graph_solver_runtime_raises_unknown_title_for_missing_start_page(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "wikiarena_graph.bin"
    metadata_path = tmp_path / "wikiarena_graph.metadata.json"
    write_solver_binary(
        file_path=binary_path,
        data=_make_toy_solver_binary_data(),
    )
    _write_graph_metadata(
        metadata_path,
    )

    runtime = GraphSolverRuntime(
        ServerConfig(
            graph_path=binary_path,
            graph_metadata_path=metadata_path,
            service_version="0.1.0",
        ),
    )

    await runtime.startup()

    with pytest.raises(
        UnknownTitleError,
    ) as error_info:
        await runtime.solve(
            start_title="Not A Page",
            target_title="Echo",
            path_mode="single",
        )

    assert error_info.value.title_role == "start"
    assert error_info.value.title == "Not A Page"

    await runtime.shutdown()


@pytest.mark.asyncio
async def test_graph_solver_runtime_returns_random_page_titles(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "wikiarena_graph.bin"
    metadata_path = tmp_path / "wikiarena_graph.metadata.json"
    write_solver_binary(
        file_path=binary_path,
        data=_make_toy_solver_binary_data(),
    )
    _write_graph_metadata(
        metadata_path,
    )

    runtime = GraphSolverRuntime(
        ServerConfig(
            graph_path=binary_path,
            graph_metadata_path=metadata_path,
            service_version="0.1.0",
        ),
    )

    await runtime.startup()

    with patch(
        "wikiarena.server.graph_runtime.random.sample",
        return_value=[0, 2, 4],
    ):
        random_titles_response = await runtime.random_page_titles(
            count=3,
        )

    assert random_titles_response.snapshot_id == "enwiki-20260301"
    assert random_titles_response.titles == [
        "Alpha",
        "Charlie",
        "Echo",
    ]

    await runtime.shutdown()


@pytest.mark.asyncio
async def test_graph_solver_runtime_returns_all_shortest_paths_when_requested(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "multi_split.solver.bin"
    metadata_path = tmp_path / "wikiarena_graph.metadata.json"
    write_solver_binary(
        file_path=binary_path,
        data=_make_multi_split_solver_binary_data(),
    )
    _write_graph_metadata(
        metadata_path,
    )

    runtime = GraphSolverRuntime(
        ServerConfig(
            graph_path=binary_path,
            graph_metadata_path=metadata_path,
            service_version="0.1.0",
        ),
    )

    await runtime.startup()

    solve_response = await runtime.solve(
        start_title="Alpha",
        target_title="Foxtrot",
        path_mode="all_shortest",
    )
    assert solve_response.path_length == 3
    assert solve_response.paths == [
        ["Alpha", "Bravo", "Delta", "Foxtrot"],
        ["Alpha", "Bravo", "Echo", "Foxtrot"],
        ["Alpha", "Charlie", "Delta", "Foxtrot"],
        ["Alpha", "Charlie", "Echo", "Foxtrot"],
    ]

    await runtime.shutdown()
