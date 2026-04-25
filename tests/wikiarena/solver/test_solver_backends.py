from pathlib import Path

import pytest

from wikiarena.archive import SQLiteSolverBackend


@pytest.mark.asyncio
async def test_sqlite_solver_backend_supports_target_sessions(
    tmp_path: Path,
) -> None:
    backend = SQLiteSolverBackend.from_db_path(
        "dumps/wiki_graph_v2.sqlite",
        snapshot_id="enwiki-20260301-v2",
    )

    session = await backend.create_target_session(
        "Fruit",
    )
    response = await session.find_shortest_path(
        "Apple",
    )

    assert backend.capabilities.backend_id == "sqlite_v2"
    assert backend.capabilities.supports_target_sessions is True
    assert session.target_page == "Fruit"
    assert response.path_length == 1
    assert response.paths[0] == ["Apple", "Fruit"]

    await backend.shutdown()
