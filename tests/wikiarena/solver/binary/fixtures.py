from __future__ import annotations

from wikiarena.solver.binary.io import SolverBinaryData


def make_toy_canonical_titles() -> tuple[str, ...]:
    return (
        "Alpha",
        "Bravo",
        "Charlie",
        "Delta",
        "Echo",
        "Foxtrot",
    )


def make_toy_dense_edges_with_duplicates() -> tuple[tuple[int, int], ...]:
    return (
        (0, 2),
        (0, 1),
        (0, 2),
        (1, 3),
        (2, 3),
        (3, 4),
    )


def make_toy_solver_binary_data() -> SolverBinaryData:
    return SolverBinaryData(
        canonical_titles=make_toy_canonical_titles(),
        out_offsets=(0, 2, 3, 4, 5, 5, 5),
        out_neighbors=(1, 2, 3, 3, 4),
        in_offsets=(0, 0, 1, 2, 4, 5, 5),
        in_neighbors=(0, 0, 1, 2, 3),
    )


def make_multi_split_solver_binary_data() -> SolverBinaryData:
    return SolverBinaryData(
        canonical_titles=(
            "Alpha",
            "Bravo",
            "Charlie",
            "Delta",
            "Echo",
            "Foxtrot",
        ),
        out_offsets=(0, 2, 4, 6, 7, 8, 8),
        out_neighbors=(1, 2, 3, 4, 3, 4, 5, 5),
        in_offsets=(0, 0, 1, 2, 4, 6, 8),
        in_neighbors=(0, 0, 1, 2, 1, 2, 3, 4),
    )
