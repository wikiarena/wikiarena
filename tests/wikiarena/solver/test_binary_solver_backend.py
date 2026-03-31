from __future__ import annotations

from pathlib import Path

import pytest

from wikiarena.solver import BinarySolverBackend
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


@pytest.mark.asyncio
async def test_binary_solver_backend_finds_shortest_path_from_toy_binary(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "toy.solver.bin"
    write_solver_binary(
        file_path=binary_path,
        data=_make_toy_solver_binary_data(),
    )

    backend = BinarySolverBackend.from_file_path(
        binary_path,
        snapshot_id="toy-snapshot",
    )

    response = await backend.find_shortest_path(
        "Alpha",
        "Echo",
    )

    assert backend.capabilities.backend_id == "binary_v1"
    assert backend.capabilities.supports_target_sessions is False
    assert response.path_length == 3
    assert response.paths == [["Alpha", "Bravo", "Delta", "Echo"]]
    assert response.pages_visited == 5
    assert response.links_scanned == 5

    await backend.shutdown()


@pytest.mark.asyncio
async def test_binary_solver_backend_reports_no_path_for_disconnected_target(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "toy.solver.bin"
    write_solver_binary(
        file_path=binary_path,
        data=_make_toy_solver_binary_data(),
    )

    backend = BinarySolverBackend.from_file_path(
        binary_path,
    )

    response = await backend.find_shortest_path(
        "Alpha",
        "Foxtrot",
    )

    assert response.path_length == -1
    assert response.paths == []
    assert response.pages_visited == 2
    assert response.links_scanned == 0

    await backend.shutdown()


@pytest.mark.asyncio
async def test_binary_solver_backend_session_wrapper_delegates_to_backend(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "toy.solver.bin"
    write_solver_binary(
        file_path=binary_path,
        data=_make_toy_solver_binary_data(),
    )

    backend = BinarySolverBackend.from_file_path(
        binary_path,
    )

    session = await backend.create_target_session(
        "Echo",
    )
    response = await session.find_shortest_path(
        "Alpha",
    )

    assert session.target_page == "Echo"
    assert response.path_length == 3
    assert response.paths[0] == ["Alpha", "Bravo", "Delta", "Echo"]

    await backend.shutdown()


@pytest.mark.asyncio
async def test_binary_solver_backend_all_shortest_mode_returns_all_paths(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "multi_split.solver.bin"
    write_solver_binary(
        file_path=binary_path,
        data=_make_multi_split_solver_binary_data(),
    )

    backend = BinarySolverBackend.from_file_path(
        binary_path,
        path_mode="all_shortest",
    )

    response = await backend.find_shortest_path(
        "Alpha",
        "Foxtrot",
    )

    assert response.path_length == 3
    assert response.paths == [
        ["Alpha", "Bravo", "Delta", "Foxtrot"],
        ["Alpha", "Bravo", "Echo", "Foxtrot"],
        ["Alpha", "Charlie", "Delta", "Foxtrot"],
        ["Alpha", "Charlie", "Echo", "Foxtrot"],
    ]

    await backend.shutdown()


@pytest.mark.asyncio
async def test_binary_solver_backend_single_mode_still_returns_one_deterministic_path(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "multi_split.solver.bin"
    write_solver_binary(
        file_path=binary_path,
        data=_make_multi_split_solver_binary_data(),
    )

    backend = BinarySolverBackend.from_file_path(
        binary_path,
        path_mode="single",
    )

    response = await backend.find_shortest_path(
        "Alpha",
        "Foxtrot",
    )

    assert response.path_length == 3
    assert response.paths == [["Alpha", "Bravo", "Delta", "Foxtrot"]]

    await backend.shutdown()
