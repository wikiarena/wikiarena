from __future__ import annotations

import pytest

from wikiarena.solver.binary.titles import (
    build_canonical_title_table,
    decode_canonical_title_table,
)


def test_canonical_title_table_builder_produces_deterministic_offsets_and_bytes() -> (
    None
):
    title_table = build_canonical_title_table(
        (
            "Alpha",
            "Bravo",
            "Charlie",
            "Delta",
        ),
    )

    assert title_table.offsets == (
        0,
        5,
        10,
        17,
        22,
    )
    assert title_table.title_bytes == b"AlphaBravoCharlieDelta"


def test_canonical_title_table_supports_node_id_and_title_lookup() -> None:
    title_table = build_canonical_title_table(
        (
            "Alpha",
            "Bravo",
            "Charlie",
            "Delta",
        ),
    )

    assert (
        title_table.title_for_node_id(
            0,
        )
        == "Alpha"
    )
    assert (
        title_table.title_for_node_id(
            2,
        )
        == "Charlie"
    )
    assert (
        title_table.find_node_id(
            "Bravo",
        )
        == 1
    )
    assert (
        title_table.find_node_id(
            "Echo",
        )
        is None
    )


def test_decode_canonical_title_table_rejects_unsorted_titles() -> None:
    with pytest.raises(
        ValueError,
        match="decoded canonical titles must be lexicographically sorted",
    ):
        decode_canonical_title_table(
            offsets=(0, 5, 10),
            title_bytes=b"BravoAlpha",
        )
