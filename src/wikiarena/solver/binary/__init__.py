"""Binary graph format and solver implementation for WikiArena."""

from wikiarena.solver.binary.builder import (
    BinaryBuildResult,
    build_solver_binary_from_grouped_intermediates,
    build_solver_binary_from_intermediates,
    build_solver_binary_from_intermediates_streaming,
    load_solver_binary_data_from_intermediates,
)
from wikiarena.solver.binary.csr import CsrGraphArrays, build_csr_graph_arrays
from wikiarena.solver.binary.graph import BinarySolverGraph
from wikiarena.solver.binary.io import (
    SolverBinaryData,
    load_solver_binary,
    validate_solver_binary_data,
    write_solver_binary,
)
from wikiarena.solver.binary.mapped_graph import (
    MappedBinarySolverGraph,
    SolverBinaryHeader,
)
from wikiarena.solver.binary.search import (
    BinaryShortestPathResult,
    find_shortest_path_by_node_ids,
    find_shortest_path_by_titles,
)
from wikiarena.solver.binary.titles import (
    CanonicalTitleTable,
    build_canonical_title_table,
    decode_canonical_title_table,
)

__all__ = [
    "CanonicalTitleTable",
    "CsrGraphArrays",
    "BinaryShortestPathResult",
    "BinarySolverGraph",
    "MappedBinarySolverGraph",
    "SolverBinaryData",
    "SolverBinaryHeader",
    "BinaryBuildResult",
    "build_canonical_title_table",
    "build_csr_graph_arrays",
    "build_solver_binary_from_grouped_intermediates",
    "build_solver_binary_from_intermediates",
    "build_solver_binary_from_intermediates_streaming",
    "decode_canonical_title_table",
    "find_shortest_path_by_node_ids",
    "find_shortest_path_by_titles",
    "load_solver_binary_data_from_intermediates",
    "load_solver_binary",
    "validate_solver_binary_data",
    "write_solver_binary",
]
