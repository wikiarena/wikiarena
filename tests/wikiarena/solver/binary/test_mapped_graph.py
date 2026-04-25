from __future__ import annotations

from pathlib import Path

from wikiarena.solver.binary.io import write_solver_binary
from wikiarena.solver.binary.mapped_graph import MappedBinarySolverGraph
from wikiarena.solver.binary.search import find_shortest_path_by_titles

from .fixtures import make_toy_solver_binary_data


def test_mapped_binary_graph_reads_header_titles_and_adjacency(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "toy.solver.bin"
    write_solver_binary(
        file_path=binary_path,
        data=make_toy_solver_binary_data(),
    )

    with MappedBinarySolverGraph(
        file_path=binary_path,
    ) as graph:
        assert graph.node_count == 6
        assert graph.edge_count == 5
        assert graph.header.file_bytes == binary_path.stat().st_size
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
        assert (
            graph.outgoing_degree(
                0,
            )
            == 2
        )
        assert (
            graph.outgoing_degree(
                5,
            )
            == 0
        )
        assert graph.incoming_neighbors(
            3,
        ) == (
            1,
            2,
        )
        assert (
            graph.incoming_degree(
                3,
            )
            == 2
        )
        assert (
            graph.incoming_degree(
                0,
            )
            == 0
        )


def test_mapped_binary_graph_works_with_bidirectional_search(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "toy.solver.bin"
    write_solver_binary(
        file_path=binary_path,
        data=make_toy_solver_binary_data(),
    )

    with MappedBinarySolverGraph(
        file_path=binary_path,
    ) as graph:
        result = find_shortest_path_by_titles(
            graph,
            start_title="Alpha",
            target_title="Echo",
        )

    assert result is not None
    assert result.path_titles == (
        "Alpha",
        "Bravo",
        "Delta",
        "Echo",
    )


def test_mapped_binary_graph_handles_sql_escaped_titles(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "escaped_titles.solver.bin"
    write_solver_binary(
        file_path=binary_path,
        data=make_toy_solver_binary_data().__class__(
            canonical_titles=("Girls\\'_Generation_(2011_album)",),
            out_offsets=(0, 0),
            out_neighbors=(),
            in_offsets=(0, 0),
            in_neighbors=(),
        ),
    )

    with MappedBinarySolverGraph(
        file_path=binary_path,
    ) as graph:
        assert (
            graph.find_node_id(
                "Girls' Generation (2011 album)",
            )
            == 0
        )
        assert (
            graph.title_for_node_id(
                0,
            )
            == "Girls' Generation (2011 album)"
        )
