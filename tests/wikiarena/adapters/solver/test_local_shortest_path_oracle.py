from __future__ import annotations

from wikiarena.adapters.solver import LocalShortestPathOracle
from wikiarena.protocol.enums import PathSource
from wikiarena.protocol.specs import TaskSpec
from wikiarena.solver.models import SolverResponse


class FakeSolver:
    async def find_shortest_path(
        self,
        start_page,
        target_page,
    ):
        return SolverResponse(
            paths=[
                [start_page, "A", target_page],
                [start_page, "B", target_page],
            ],
            path_length=2,
            computation_time_ms=1.0,
        )


async def test_local_shortest_path_oracle_returns_first_solver_shortest_path() -> (
    None
):
    oracle = LocalShortestPathOracle(
        solver_backend=FakeSolver(),
        snapshot_id="enwiki-2026-01-01",
    )

    path = await oracle.get_solver_shortest_path(
        TaskSpec(
            language="en",
            start_page_title="Apple",
            target_page_title="Banana",
        ),
    )

    assert path is not None
    assert path.source == PathSource.LOCAL_GRAPH
    assert path.solver_snapshot_id == "enwiki-2026-01-01"
    assert path.hop_count == 2
    assert path.page_titles == ["Apple", "A", "Banana"]
