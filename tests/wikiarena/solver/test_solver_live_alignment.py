from __future__ import annotations

import os
from pathlib import Path

import pytest

from wikiarena.wikipedia import LiveWikiService
from wikiarena.solver.static_db import StaticSolverDB
from wikiarena.solver.solver import WikiTaskSolver


pytestmark = pytest.mark.integration


DB_PATH = Path("dumps/wiki_graph_v2.sqlite")
RUN_LIVE_ALIGNMENT_TESTS = os.getenv("WIKIARENA_RUN_LIVE_ALIGNMENT_TESTS") == "1"


def _build_solver() -> WikiTaskSolver:
    db = StaticSolverDB()
    db.db_path = DB_PATH
    db._initialize_variable_limit()
    db._initialized = True
    return WikiTaskSolver(db=db)


@pytest.mark.skipif(
    not DB_PATH.exists() or not RUN_LIVE_ALIGNMENT_TESTS,
    reason="requires wiki_graph_v2.sqlite and WIKIARENA_RUN_LIVE_ALIGNMENT_TESTS=1",
)
@pytest.mark.asyncio
async def test_solver_direct_edge_matches_live_for_apple_to_fruit() -> None:
    solver = _build_solver()
    live = LiveWikiService(language="en")

    response = await solver.find_shortest_path(
        "Apple",
        "Fruit",
    )
    assert response.path_length == 1
    assert response.paths[0] == ["Apple", "Fruit"]

    apple_page = await live.get_page(
        "Apple",
        include_all_namespaces=False,
    )
    assert "Fruit" in apple_page.links

    await solver.shutdown()


@pytest.mark.skipif(
    not DB_PATH.exists() or not RUN_LIVE_ALIGNMENT_TESTS,
    reason="requires wiki_graph_v2.sqlite and WIKIARENA_RUN_LIVE_ALIGNMENT_TESTS=1",
)
@pytest.mark.asyncio
async def test_solver_direct_edge_matches_live_for_philosophy_to_science() -> None:
    solver = _build_solver()
    live = LiveWikiService(language="en")

    response = await solver.find_shortest_path(
        "Philosophy",
        "Science",
    )
    assert response.path_length == 1
    assert response.paths[0] == ["Philosophy", "Science"]

    philosophy_page = await live.get_page(
        "Philosophy",
        include_all_namespaces=False,
    )
    assert "Science" in philosophy_page.links

    await solver.shutdown()
