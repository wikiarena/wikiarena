from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from wikiarena.solver.binary import (
    MappedBinarySolverGraph,
    find_shortest_path_by_titles,
)


@dataclass(frozen=True)
class SmokeTestCase:
    start_page: str
    target_page: str
    expected_length: int


DEFAULT_SMOKE_CASES = (
    SmokeTestCase(
        start_page="Apple",
        target_page="Fruit",
        expected_length=1,
    ),
    SmokeTestCase(
        start_page="Claude Shannon",
        target_page="Byzantine Empire",
        expected_length=2,
    ),
    SmokeTestCase(
        start_page="List of Buran missions",
        target_page="Alberto Segado",
        expected_length=5,
    ),
)


def smoke_test_graph(
    *,
    graph_file_path: Path,
    cases: tuple[SmokeTestCase, ...] = DEFAULT_SMOKE_CASES,
) -> list[dict[str, object]]:
    graph_path = graph_file_path
    results: list[dict[str, object]] = []
    with MappedBinarySolverGraph(
        file_path=graph_path,
    ) as graph:
        for case in cases:
            result = find_shortest_path_by_titles(
                graph,
                start_title=case.start_page,
                target_title=case.target_page,
            )
            if result is None:
                raise RuntimeError(
                    f"No path found for smoke test case {case.start_page!r} -> {case.target_page!r}",
                )
            if result.path_length != case.expected_length:
                raise RuntimeError(
                    f"Unexpected path length for {case.start_page!r} -> {case.target_page!r}: "
                    f"expected {case.expected_length}, got {result.path_length}",
                )
            results.append(
                {
                    "start_page": case.start_page,
                    "target_page": case.target_page,
                    "expected_length": case.expected_length,
                    "first_path": list(
                        result.path_titles,
                    ),
                },
            )
    return results
