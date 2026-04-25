from __future__ import annotations

import pytest

from wikiarena.solver.binary.csr import build_csr_graph_arrays

from .fixtures import make_toy_canonical_titles, make_toy_dense_edges_with_duplicates


def test_csr_builder_sorts_and_deduplicates_dense_edges() -> None:
    csr_arrays = build_csr_graph_arrays(
        node_count=len(
            make_toy_canonical_titles(),
        ),
        edges=make_toy_dense_edges_with_duplicates(),
    )

    assert csr_arrays.out_offsets == (
        0,
        2,
        3,
        4,
        5,
        5,
        5,
    )
    assert csr_arrays.out_neighbors == (
        1,
        2,
        3,
        3,
        4,
    )
    assert csr_arrays.in_offsets == (
        0,
        0,
        1,
        2,
        4,
        5,
        5,
    )
    assert csr_arrays.in_neighbors == (
        0,
        0,
        1,
        2,
        3,
    )


def test_csr_builder_reconstructs_expected_in_and_out_degrees() -> None:
    csr_arrays = build_csr_graph_arrays(
        node_count=len(
            make_toy_canonical_titles(),
        ),
        edges=make_toy_dense_edges_with_duplicates(),
    )

    out_degrees = tuple(
        end - start
        for start, end in zip(
            csr_arrays.out_offsets,
            csr_arrays.out_offsets[1:],
        )
    )
    in_degrees = tuple(
        end - start
        for start, end in zip(
            csr_arrays.in_offsets,
            csr_arrays.in_offsets[1:],
        )
    )

    assert out_degrees == (
        2,
        1,
        1,
        1,
        0,
        0,
    )
    assert in_degrees == (
        0,
        1,
        1,
        2,
        1,
        0,
    )
    assert csr_arrays.out_offsets[-1] == len(
        csr_arrays.out_neighbors,
    )
    assert csr_arrays.in_offsets[-1] == len(
        csr_arrays.in_neighbors,
    )


def test_csr_builder_rejects_out_of_range_node_ids() -> None:
    with pytest.raises(
        ValueError,
        match="target node id out of range",
    ):
        build_csr_graph_arrays(
            node_count=3,
            edges=((0, 3),),
        )
