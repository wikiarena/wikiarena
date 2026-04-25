from __future__ import annotations

import os
from pathlib import Path

import pytest

from wikiarena.solver.backends.wikigame_solver_backend import WikiGameSolverBackend
from wikiarena.solver.backends.wikigame_solver_backend import (
    _canonical_title_from_output_line,
)
from wikiarena.solver.backends.wikigame_solver_backend import (
    _parse_wikigame_solver_paths,
)


def test_parse_wikigame_solver_single_path_output() -> None:
    response_text = "Apple\nFruit"
    assert _parse_wikigame_solver_paths(response_text) == [["Apple", "Fruit"]]


def test_parse_wikigame_solver_multi_path_output_with_redirect_annotations() -> None:
    response_text = "\n".join(
        [
            "Path #1",
            "Apple",
            "Fruit",
            "",
            "Path #2",
            "Apple",
            "Malus_domestica (redirects to Apple)",
            "Fruit",
        ],
    )

    assert _parse_wikigame_solver_paths(response_text) == [
        ["Apple", "Fruit"],
        ["Apple", "Apple", "Fruit"],
    ]


def test_canonical_title_from_output_line_extracts_redirect_target() -> None:
    assert _canonical_title_from_output_line("Fruit") == "Fruit"
    assert _canonical_title_from_output_line("Apples (redirects to Apple)") == "Apple"


WIKIGAME_BINARY = Path(
    os.getenv(
        "WIKIARENA_WIKIGAME_SOLVER_BIN",
        "/Users/hupaulson/projects/WikiGameSolver/cli_server_local",
    ),
)
WIKIGAME_DB = Path(
    os.getenv(
        "WIKIARENA_WIKIGAME_SOLVER_DB",
        "/Users/hupaulson/Downloads/en.bin",
    ),
)


@pytest.mark.skipif(
    not WIKIGAME_BINARY.exists()
    or not WIKIGAME_DB.exists()
    or os.getenv("WIKIARENA_RUN_WIKIGAME_BACKEND_TESTS") != "1",
    reason="requires local WikiGameSolver binary/db and WIKIARENA_RUN_WIKIGAME_BACKEND_TESTS=1",
)
@pytest.mark.asyncio
async def test_wikigame_solver_backend_smoke_query() -> None:
    backend = WikiGameSolverBackend(
        binary_path=WIKIGAME_BINARY,
        db_path=WIKIGAME_DB,
    )

    response = await backend.find_shortest_path(
        "Apple",
        "Fruit",
    )

    assert response.path_length == 1
    assert response.paths[0] == ["Apple", "Fruit"]

    await backend.shutdown()
