from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from wikiarena.solver.binary import build_solver_binary_from_grouped_intermediates


@dataclass(frozen=True)
class GraphBuildResult:
    output_path: Path
    node_count: int
    edge_count: int


def build_graph_binary(
    *,
    pages_file_path: Path,
    grouped_links_by_source_file_path: Path,
    grouped_links_by_target_file_path: Path,
    output_file_path: Path,
    progress_callback: Callable[[str], None] | None = None,
) -> GraphBuildResult:
    output_path = output_file_path
    build_result = build_solver_binary_from_grouped_intermediates(
        pages_file_path=pages_file_path,
        grouped_links_by_source_file_path=grouped_links_by_source_file_path,
        grouped_links_by_target_file_path=grouped_links_by_target_file_path,
        output_file_path=output_path,
        progress_callback=progress_callback,
    )
    return GraphBuildResult(
        output_path=output_path,
        node_count=build_result.node_count,
        edge_count=build_result.edge_count,
    )
