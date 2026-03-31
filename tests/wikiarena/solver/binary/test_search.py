from __future__ import annotations

from pathlib import Path

import pytest

from wikiarena.solver.binary.graph import BinarySolverGraph
from wikiarena.solver.binary.io import load_solver_binary, write_solver_binary
from wikiarena.solver.binary.search import (
    find_all_shortest_paths_by_titles,
    find_shortest_path_by_titles,
    search_all_shortest_paths_by_node_ids,
)

from .fixtures import (
    make_multi_split_solver_binary_data,
    make_toy_solver_binary_data,
)


def test_binary_solver_graph_exposes_title_lookup_and_adjacency(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "toy.solver.bin"
    write_solver_binary(
        file_path=binary_path,
        data=make_toy_solver_binary_data(),
    )

    graph = BinarySolverGraph.from_solver_binary_data(
        load_solver_binary(
            file_path=binary_path,
        ),
    )

    assert (
        graph.find_node_id(
            "Charlie",
        )
        == 2
    )
    assert (
        graph.title_for_node_id(
            4,
        )
        == "Echo"
    )
    assert graph.outgoing_neighbors(
        0,
    ) == (
        1,
        2,
    )
    assert graph.incoming_neighbors(
        3,
    ) == (
        1,
        2,
    )


def test_bidirectional_bfs_finds_exact_shortest_path_on_toy_graph(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "toy.solver.bin"
    write_solver_binary(
        file_path=binary_path,
        data=make_toy_solver_binary_data(),
    )

    graph = BinarySolverGraph.from_solver_binary_data(
        load_solver_binary(
            file_path=binary_path,
        ),
    )
    result = find_shortest_path_by_titles(
        graph,
        start_title="Alpha",
        target_title="Echo",
    )

    assert result is not None
    assert result.path_node_ids == (
        0,
        1,
        3,
        4,
    )
    assert result.path_titles == (
        "Alpha",
        "Bravo",
        "Delta",
        "Echo",
    )
    assert result.path_length == 3


def test_bidirectional_bfs_handles_self_case(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "toy.solver.bin"
    write_solver_binary(
        file_path=binary_path,
        data=make_toy_solver_binary_data(),
    )

    graph = BinarySolverGraph.from_solver_binary_data(
        load_solver_binary(
            file_path=binary_path,
        ),
    )
    result = find_shortest_path_by_titles(
        graph,
        start_title="Alpha",
        target_title="Alpha",
    )

    assert result is not None
    assert result.path_titles == ("Alpha",)
    assert result.path_length == 0


def test_bidirectional_bfs_returns_none_when_disconnected(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "toy.solver.bin"
    write_solver_binary(
        file_path=binary_path,
        data=make_toy_solver_binary_data(),
    )

    graph = BinarySolverGraph.from_solver_binary_data(
        load_solver_binary(
            file_path=binary_path,
        ),
    )

    assert (
        find_shortest_path_by_titles(
            graph,
            start_title="Alpha",
            target_title="Foxtrot",
        )
        is None
    )


def test_bidirectional_bfs_rejects_unknown_titles(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "toy.solver.bin"
    write_solver_binary(
        file_path=binary_path,
        data=make_toy_solver_binary_data(),
    )

    graph = BinarySolverGraph.from_solver_binary_data(
        load_solver_binary(
            file_path=binary_path,
        ),
    )

    with pytest.raises(
        ValueError,
        match="unknown start title",
    ):
        find_shortest_path_by_titles(
            graph,
            start_title="Missing",
            target_title="Echo",
        )


def test_find_all_shortest_paths_returns_both_paths_on_diamond_graph(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "toy.solver.bin"
    write_solver_binary(
        file_path=binary_path,
        data=make_toy_solver_binary_data(),
    )

    graph = BinarySolverGraph.from_solver_binary_data(
        load_solver_binary(
            file_path=binary_path,
        ),
    )

    result = find_all_shortest_paths_by_titles(
        graph,
        start_title="Alpha",
        target_title="Echo",
    )

    assert result is not None
    assert result.path_length == 3
    assert result.path_count == 2
    assert result.path_titles == (
        (
            "Alpha",
            "Bravo",
            "Delta",
            "Echo",
        ),
        (
            "Alpha",
            "Charlie",
            "Delta",
            "Echo",
        ),
    )


def test_find_all_shortest_paths_handles_multiple_split_nodes_without_duplicates(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "multi_split.solver.bin"
    write_solver_binary(
        file_path=binary_path,
        data=make_multi_split_solver_binary_data(),
    )

    graph = BinarySolverGraph.from_solver_binary_data(
        load_solver_binary(
            file_path=binary_path,
        ),
    )

    result = find_all_shortest_paths_by_titles(
        graph,
        start_title="Alpha",
        target_title="Foxtrot",
    )

    assert result is not None
    assert result.path_length == 3
    assert result.path_count == 4
    assert result.path_titles == (
        (
            "Alpha",
            "Bravo",
            "Delta",
            "Foxtrot",
        ),
        (
            "Alpha",
            "Bravo",
            "Echo",
            "Foxtrot",
        ),
        (
            "Alpha",
            "Charlie",
            "Delta",
            "Foxtrot",
        ),
        (
            "Alpha",
            "Charlie",
            "Echo",
            "Foxtrot",
        ),
    )


def test_find_all_shortest_paths_handles_self_case(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "toy.solver.bin"
    write_solver_binary(
        file_path=binary_path,
        data=make_toy_solver_binary_data(),
    )

    graph = BinarySolverGraph.from_solver_binary_data(
        load_solver_binary(
            file_path=binary_path,
        ),
    )

    result = find_all_shortest_paths_by_titles(
        graph,
        start_title="Alpha",
        target_title="Alpha",
    )

    assert result is not None
    assert result.path_count == 1
    assert result.path_titles == (("Alpha",),)
    assert result.path_length == 0


def test_find_all_shortest_paths_returns_none_when_disconnected(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "toy.solver.bin"
    write_solver_binary(
        file_path=binary_path,
        data=make_toy_solver_binary_data(),
    )

    graph = BinarySolverGraph.from_solver_binary_data(
        load_solver_binary(
            file_path=binary_path,
        ),
    )

    assert (
        find_all_shortest_paths_by_titles(
            graph,
            start_title="Alpha",
            target_title="Foxtrot",
        )
        is None
    )


def test_search_all_shortest_paths_reports_empty_result_when_disconnected(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "toy.solver.bin"
    write_solver_binary(
        file_path=binary_path,
        data=make_toy_solver_binary_data(),
    )

    graph = BinarySolverGraph.from_solver_binary_data(
        load_solver_binary(
            file_path=binary_path,
        ),
    )

    result = search_all_shortest_paths_by_node_ids(
        graph,
        start_node_id=0,
        target_node_id=5,
    )

    assert result.path_node_id_paths == ()
    assert result.path_count == 0
    assert result.path_length is None
