from __future__ import annotations

from pathlib import Path

import pytest

from wikiarena.solver.binary.format import (
    SOLVER_BINARY_MAGIC,
    SOLVER_BINARY_VERSION,
    SOLVER_HEADER_BYTES,
    SOLVER_HEADER_STRUCT,
)
from wikiarena.solver.binary.io import (
    SolverBinaryData,
    load_solver_binary,
    write_solver_binary,
)

from .fixtures import make_toy_solver_binary_data


def test_solver_binary_round_trip_preserves_toy_graph(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "toy.solver.bin"
    expected_data = make_toy_solver_binary_data()

    write_solver_binary(
        file_path=binary_path,
        data=expected_data,
    )

    loaded_data = load_solver_binary(
        file_path=binary_path,
    )

    assert loaded_data == expected_data

    header = SOLVER_HEADER_STRUCT.unpack(
        binary_path.read_bytes()[:SOLVER_HEADER_BYTES],
    )
    assert header[0] == SOLVER_BINARY_MAGIC
    assert header[1] == SOLVER_BINARY_VERSION
    assert header[2] == SOLVER_HEADER_BYTES
    assert header[3] == expected_data.node_count
    assert header[4] == expected_data.edge_count
    assert header[11] == binary_path.stat().st_size


def test_solver_binary_loader_rejects_invalid_magic(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "bad-magic.solver.bin"
    expected_data = make_toy_solver_binary_data()

    write_solver_binary(
        file_path=binary_path,
        data=expected_data,
    )

    file_bytes = bytearray(
        binary_path.read_bytes(),
    )
    file_bytes[:8] = b"NOTMAGIC"
    binary_path.write_bytes(
        bytes(file_bytes),
    )

    with pytest.raises(
        ValueError,
        match="unexpected solver binary magic",
    ):
        load_solver_binary(
            file_path=binary_path,
        )


def test_solver_binary_writer_rejects_unsorted_adjacency() -> None:
    invalid_data = SolverBinaryData(
        canonical_titles=(
            "Alpha",
            "Bravo",
        ),
        out_offsets=(0, 2, 2),
        out_neighbors=(1, 0),
        in_offsets=(0, 1, 2),
        in_neighbors=(0, 0),
    )

    with pytest.raises(
        ValueError,
        match="outgoing adjacency must be strictly sorted",
    ):
        write_solver_binary(
            file_path=Path("/dev/null"),
            data=invalid_data,
        )
