from __future__ import annotations

import gzip
import os
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from wikiarena.solver.binary.csr import build_csr_graph_arrays
from wikiarena.solver.binary.format import (
    SOLVER_BINARY_MAGIC,
    SOLVER_BINARY_VERSION,
    SOLVER_HEADER_BYTES,
    SOLVER_HEADER_STRUCT,
    pack_u24_values,
)
from wikiarena.solver.binary.io import SolverBinaryData, write_solver_binary
from wikiarena.solver.binary.titles import build_canonical_title_table

U32_STRUCT = struct.Struct("<I")


@dataclass(frozen=True)
class BinaryBuildResult:
    node_count: int
    edge_count: int
    canonical_titles: tuple[str, ...]


def build_solver_binary_from_intermediates(
    *,
    pages_file_path: Path,
    links_file_path: Path,
    output_file_path: Path,
) -> BinaryBuildResult:
    solver_binary_data = load_solver_binary_data_from_intermediates(
        pages_file_path=pages_file_path,
        links_file_path=links_file_path,
    )
    write_solver_binary(
        file_path=output_file_path,
        data=solver_binary_data,
    )
    return BinaryBuildResult(
        node_count=solver_binary_data.node_count,
        edge_count=solver_binary_data.edge_count,
        canonical_titles=solver_binary_data.canonical_titles,
    )


def build_solver_binary_from_intermediates_streaming(
    *,
    pages_file_path: Path,
    links_file_path: Path,
    output_file_path: Path,
    temp_dir_path: Path | None = None,
    sort_binary_name: str = "sort",
) -> BinaryBuildResult:
    canonical_pages = _load_canonical_pages(
        pages_file_path=Path(
            pages_file_path,
        ),
    )
    canonical_titles = tuple(page_title for _, page_title in canonical_pages)
    page_id_to_node_id = {
        page_id: node_id
        for node_id, (page_id, _) in enumerate(
            canonical_pages,
        )
    }

    sort_binary_path = shutil.which(
        sort_binary_name,
    )
    if sort_binary_path is None:
        raise RuntimeError(
            f"sort binary not found: {sort_binary_name}",
        )

    temp_root_dir = None
    if temp_dir_path is not None:
        temp_root_dir = str(
            Path(
                temp_dir_path,
            ),
        )

    with tempfile.TemporaryDirectory(
        dir=temp_root_dir,
        prefix="wikiarena-binary-build-",
    ) as temp_dir_name:
        temp_dir = Path(
            temp_dir_name,
        )
        dense_edges_path = temp_dir / "dense_edges.tsv"
        dense_edges_by_source_path = temp_dir / "dense_edges.by_source.tsv"
        dense_edges_by_target_path = temp_dir / "dense_edges.by_target.tsv"

        _write_dense_edges_file(
            links_file_path=Path(
                links_file_path,
            ),
            page_id_to_node_id=page_id_to_node_id,
            dense_edges_path=dense_edges_path,
        )
        _sort_dense_edges_file(
            input_file_path=dense_edges_path,
            output_file_path=dense_edges_by_source_path,
            primary_column=1,
            secondary_column=2,
            sort_binary_path=Path(
                sort_binary_path,
            ),
        )
        _sort_dense_edges_file(
            input_file_path=dense_edges_path,
            output_file_path=dense_edges_by_target_path,
            primary_column=2,
            secondary_column=1,
            sort_binary_path=Path(
                sort_binary_path,
            ),
        )

        return _write_solver_binary_from_sorted_dense_edges(
            output_file_path=Path(
                output_file_path,
            ),
            canonical_titles=canonical_titles,
            dense_edges_by_source_path=dense_edges_by_source_path,
            dense_edges_by_target_path=dense_edges_by_target_path,
        )


def build_solver_binary_from_grouped_intermediates(
    *,
    pages_file_path: Path,
    grouped_links_by_source_file_path: Path,
    grouped_links_by_target_file_path: Path,
    output_file_path: Path,
    progress_callback: Callable[[str], None] | None = None,
) -> BinaryBuildResult:
    canonical_pages = _load_canonical_pages(
        pages_file_path=Path(
            pages_file_path,
        ),
    )
    canonical_titles = tuple(page_title for _, page_title in canonical_pages)
    page_id_to_node_id = {
        page_id: node_id
        for node_id, (page_id, _) in enumerate(
            canonical_pages,
        )
    }

    return _write_solver_binary_from_grouped_links(
        output_file_path=Path(
            output_file_path,
        ),
        canonical_titles=canonical_titles,
        grouped_links_by_source_file_path=Path(
            grouped_links_by_source_file_path,
        ),
        grouped_links_by_target_file_path=Path(
            grouped_links_by_target_file_path,
        ),
        page_id_to_node_id=page_id_to_node_id,
        progress_callback=progress_callback,
    )


def load_solver_binary_data_from_intermediates(
    *,
    pages_file_path: Path,
    links_file_path: Path,
) -> SolverBinaryData:
    canonical_pages = _load_canonical_pages(
        pages_file_path=Path(
            pages_file_path,
        ),
    )
    canonical_titles = tuple(page_title for _, page_title in canonical_pages)
    page_id_to_node_id = {
        page_id: node_id
        for node_id, (page_id, _) in enumerate(
            canonical_pages,
        )
    }

    dense_edges = _load_dense_edges(
        links_file_path=Path(
            links_file_path,
        ),
        page_id_to_node_id=page_id_to_node_id,
    )
    csr_graph_arrays = build_csr_graph_arrays(
        node_count=len(canonical_titles),
        edges=dense_edges,
    )
    return SolverBinaryData(
        canonical_titles=canonical_titles,
        out_offsets=csr_graph_arrays.out_offsets,
        out_neighbors=csr_graph_arrays.out_neighbors,
        in_offsets=csr_graph_arrays.in_offsets,
        in_neighbors=csr_graph_arrays.in_neighbors,
    )


def _load_canonical_pages(
    *,
    pages_file_path: Path,
) -> tuple[tuple[int, str], ...]:
    canonical_pages: list[tuple[int, str]] = []
    with gzip.open(
        pages_file_path,
        "rt",
        encoding="utf-8",
    ) as file_handle:
        for line_number, raw_line in enumerate(
            file_handle,
            start=1,
        ):
            line = raw_line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 4:
                raise ValueError(
                    f"pages file line {line_number} has {len(parts)} columns, expected 4",
                )

            page_id_text, namespace_text, page_title, is_redirect_text = parts[:4]
            if namespace_text != "0":
                raise ValueError(
                    f"pages file line {line_number} is not article namespace: {namespace_text}",
                )
            if is_redirect_text != "0":
                continue

            canonical_pages.append(
                (
                    int(page_id_text),
                    page_title,
                ),
            )

    canonical_pages.sort(
        key=lambda page_row: page_row[1],
    )

    canonical_titles = [page_title for _, page_title in canonical_pages]
    if len(set(canonical_titles)) != len(canonical_titles):
        raise ValueError(
            "canonical page titles must be unique",
        )

    return tuple(
        canonical_pages,
    )


def _load_dense_edges(
    *,
    links_file_path: Path,
    page_id_to_node_id: dict[int, int],
) -> tuple[tuple[int, int], ...]:
    dense_edges: list[tuple[int, int]] = []
    with gzip.open(
        links_file_path,
        "rt",
        encoding="utf-8",
    ) as file_handle:
        for line_number, raw_line in enumerate(
            file_handle,
            start=1,
        ):
            line = raw_line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                raise ValueError(
                    f"links file line {line_number} has {len(parts)} columns, expected 2",
                )

            source_page_id = int(parts[0])
            target_page_id = int(parts[1])
            if source_page_id not in page_id_to_node_id:
                raise ValueError(
                    f"links file line {line_number} references unknown canonical source page id {source_page_id}",
                )
            if target_page_id not in page_id_to_node_id:
                raise ValueError(
                    f"links file line {line_number} references unknown canonical target page id {target_page_id}",
                )

            source_node_id = page_id_to_node_id[source_page_id]
            target_node_id = page_id_to_node_id[target_page_id]
            if source_node_id == target_node_id:
                continue
            dense_edges.append(
                (
                    source_node_id,
                    target_node_id,
                ),
            )

    return tuple(
        dense_edges,
    )


def _write_dense_edges_file(
    *,
    links_file_path: Path,
    page_id_to_node_id: dict[int, int],
    dense_edges_path: Path,
) -> None:
    with (
        gzip.open(
            links_file_path,
            "rt",
            encoding="utf-8",
        ) as input_file_handle,
        dense_edges_path.open(
            "wt",
            encoding="utf-8",
        ) as output_file_handle,
    ):
        for line_number, raw_line in enumerate(
            input_file_handle,
            start=1,
        ):
            line = raw_line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                raise ValueError(
                    f"links file line {line_number} has {len(parts)} columns, expected 2",
                )

            source_page_id = int(parts[0])
            target_page_id = int(parts[1])
            if source_page_id not in page_id_to_node_id:
                raise ValueError(
                    f"links file line {line_number} references unknown canonical source page id {source_page_id}",
                )
            if target_page_id not in page_id_to_node_id:
                raise ValueError(
                    f"links file line {line_number} references unknown canonical target page id {target_page_id}",
                )

            source_node_id = page_id_to_node_id[source_page_id]
            target_node_id = page_id_to_node_id[target_page_id]
            if source_node_id == target_node_id:
                continue

            output_file_handle.write(
                f"{source_node_id}\t{target_node_id}\n",
            )


def _sort_dense_edges_file(
    *,
    input_file_path: Path,
    output_file_path: Path,
    primary_column: int,
    secondary_column: int,
    sort_binary_path: Path,
) -> None:
    environment = os.environ.copy()
    environment["LC_ALL"] = "C"
    with output_file_path.open(
        "wb",
    ) as output_file_handle:
        subprocess.run(
            [
                str(sort_binary_path),
                "-t",
                "\t",
                "-k",
                f"{primary_column},{primary_column}n",
                "-k",
                f"{secondary_column},{secondary_column}n",
                "-u",
                str(input_file_path),
            ],
            check=True,
            stdout=output_file_handle,
            env=environment,
        )


def _write_solver_binary_from_sorted_dense_edges(
    *,
    output_file_path: Path,
    canonical_titles: tuple[str, ...],
    dense_edges_by_source_path: Path,
    dense_edges_by_target_path: Path,
) -> BinaryBuildResult:
    node_count = len(canonical_titles)
    canonical_title_table = build_canonical_title_table(
        canonical_titles,
    )
    canonical_offsets_bytes = _pack_u32_values(
        canonical_title_table.offsets,
    )
    canonical_bytes = canonical_title_table.title_bytes

    out_offsets, edge_count = _build_offsets_from_sorted_dense_edges(
        sorted_dense_edges_path=dense_edges_by_source_path,
        node_count=node_count,
        primary_column_index=0,
    )
    in_offsets, incoming_edge_count = _build_offsets_from_sorted_dense_edges(
        sorted_dense_edges_path=dense_edges_by_target_path,
        node_count=node_count,
        primary_column_index=1,
    )
    if incoming_edge_count != edge_count:
        raise ValueError(
            "incoming edge count does not match outgoing edge count",
        )

    out_offsets_bytes = _pack_u32_values(
        out_offsets,
    )
    in_offsets_bytes = _pack_u32_values(
        in_offsets,
    )

    canonical_offsets_off = SOLVER_HEADER_BYTES
    canonical_bytes_off = canonical_offsets_off + len(canonical_offsets_bytes)
    out_offsets_off = canonical_bytes_off + len(canonical_bytes)
    out_neighbors_off = out_offsets_off + len(out_offsets_bytes)
    in_offsets_off = out_neighbors_off + (edge_count * 3)
    in_neighbors_off = in_offsets_off + len(in_offsets_bytes)
    file_bytes = in_neighbors_off + (edge_count * 3)

    header_bytes = SOLVER_HEADER_STRUCT.pack(
        SOLVER_BINARY_MAGIC,
        SOLVER_BINARY_VERSION,
        SOLVER_HEADER_BYTES,
        node_count,
        edge_count,
        canonical_offsets_off,
        canonical_bytes_off,
        out_offsets_off,
        out_neighbors_off,
        in_offsets_off,
        in_neighbors_off,
        file_bytes,
    )

    with output_file_path.open(
        "wb",
    ) as output_file_handle:
        output_file_handle.write(
            b"\x00" * SOLVER_HEADER_BYTES,
        )
        output_file_handle.write(
            canonical_offsets_bytes,
        )
        output_file_handle.write(
            canonical_bytes,
        )
        output_file_handle.write(
            out_offsets_bytes,
        )
        _write_neighbor_column_as_u24(
            sorted_dense_edges_path=dense_edges_by_source_path,
            output_file_handle=output_file_handle,
            neighbor_column_index=1,
        )
        output_file_handle.write(
            in_offsets_bytes,
        )
        _write_neighbor_column_as_u24(
            sorted_dense_edges_path=dense_edges_by_target_path,
            output_file_handle=output_file_handle,
            neighbor_column_index=0,
        )
        output_file_handle.seek(
            0,
        )
        output_file_handle.write(
            header_bytes,
        )

    return BinaryBuildResult(
        node_count=node_count,
        edge_count=edge_count,
        canonical_titles=canonical_titles,
    )


def _write_solver_binary_from_grouped_links(
    *,
    output_file_path: Path,
    canonical_titles: tuple[str, ...],
    grouped_links_by_source_file_path: Path,
    grouped_links_by_target_file_path: Path,
    page_id_to_node_id: dict[int, int],
    progress_callback: Callable[[str], None] | None,
) -> BinaryBuildResult:
    node_count = len(canonical_titles)
    _log_progress(
        progress_callback,
        f"Loading grouped graph inputs for {node_count:,} canonical pages",
    )
    canonical_title_table = build_canonical_title_table(
        canonical_titles,
    )
    canonical_offsets_bytes = _pack_u32_values(
        canonical_title_table.offsets,
    )
    canonical_bytes = canonical_title_table.title_bytes

    out_offsets, edge_count = _build_offsets_from_grouped_links(
        grouped_links_file_path=grouped_links_by_source_file_path,
        page_id_to_node_id=page_id_to_node_id,
        node_count=node_count,
        primary_is_source=True,
        progress_label="count outgoing grouped edges",
        progress_callback=progress_callback,
    )
    in_offsets, incoming_edge_count = _build_offsets_from_grouped_links(
        grouped_links_file_path=grouped_links_by_target_file_path,
        page_id_to_node_id=page_id_to_node_id,
        node_count=node_count,
        primary_is_source=False,
        progress_label="count incoming grouped edges",
        progress_callback=progress_callback,
    )
    if incoming_edge_count != edge_count:
        raise ValueError(
            "incoming edge count does not match outgoing edge count",
        )

    out_offsets_bytes = _pack_u32_values(
        out_offsets,
    )
    in_offsets_bytes = _pack_u32_values(
        in_offsets,
    )

    canonical_offsets_off = SOLVER_HEADER_BYTES
    canonical_bytes_off = canonical_offsets_off + len(canonical_offsets_bytes)
    out_offsets_off = canonical_bytes_off + len(canonical_bytes)
    out_neighbors_off = out_offsets_off + len(out_offsets_bytes)
    in_offsets_off = out_neighbors_off + (edge_count * 3)
    in_neighbors_off = in_offsets_off + len(in_offsets_bytes)
    file_bytes = in_neighbors_off + (edge_count * 3)

    header_bytes = SOLVER_HEADER_STRUCT.pack(
        SOLVER_BINARY_MAGIC,
        SOLVER_BINARY_VERSION,
        SOLVER_HEADER_BYTES,
        node_count,
        edge_count,
        canonical_offsets_off,
        canonical_bytes_off,
        out_offsets_off,
        out_neighbors_off,
        in_offsets_off,
        in_neighbors_off,
        file_bytes,
    )

    with output_file_path.open(
        "wb",
    ) as output_file_handle:
        _log_progress(
            progress_callback,
            f"Allocating {output_file_path.name} at {file_bytes:,} bytes",
        )
        output_file_handle.write(
            b"\x00" * SOLVER_HEADER_BYTES,
        )
        output_file_handle.write(
            canonical_offsets_bytes,
        )
        output_file_handle.write(
            canonical_bytes,
        )
        output_file_handle.write(
            out_offsets_bytes,
        )
        output_file_handle.truncate(
            file_bytes,
        )

    with output_file_path.open(
        "r+b",
    ) as output_file_handle:
        _log_progress(
            progress_callback,
            "Writing outgoing neighbor section",
        )
        _write_grouped_neighbors_section(
            grouped_links_file_path=grouped_links_by_source_file_path,
            page_id_to_node_id=page_id_to_node_id,
            offsets=out_offsets,
            section_offset=out_neighbors_off,
            primary_is_source=True,
            output_file_handle=output_file_handle,
            progress_label="write outgoing grouped neighbors",
            progress_callback=progress_callback,
        )
        output_file_handle.seek(
            in_offsets_off,
        )
        output_file_handle.write(
            in_offsets_bytes,
        )
        _log_progress(
            progress_callback,
            "Writing incoming neighbor section",
        )
        _write_grouped_neighbors_section(
            grouped_links_file_path=grouped_links_by_target_file_path,
            page_id_to_node_id=page_id_to_node_id,
            offsets=in_offsets,
            section_offset=in_neighbors_off,
            primary_is_source=False,
            output_file_handle=output_file_handle,
            progress_label="write incoming grouped neighbors",
            progress_callback=progress_callback,
        )
        output_file_handle.seek(
            0,
        )
        output_file_handle.write(
            header_bytes,
        )
    _log_progress(
        progress_callback,
        f"Finished writing {output_file_path.name} with {edge_count:,} directed edges",
    )

    return BinaryBuildResult(
        node_count=node_count,
        edge_count=edge_count,
        canonical_titles=canonical_titles,
    )


def _build_offsets_from_sorted_dense_edges(
    *,
    sorted_dense_edges_path: Path,
    node_count: int,
    primary_column_index: int,
) -> tuple[tuple[int, ...], int]:
    counts = [0] * node_count
    edge_count = 0
    with sorted_dense_edges_path.open(
        "rt",
        encoding="utf-8",
    ) as file_handle:
        for line_number, raw_line in enumerate(
            file_handle,
            start=1,
        ):
            line = raw_line.rstrip("\n")
            if not line:
                continue
            source_node_id, target_node_id = _parse_dense_edge_line(
                line=line,
                line_number=line_number,
            )
            primary_node_id = (
                source_node_id if primary_column_index == 0 else target_node_id
            )
            if primary_node_id < 0 or primary_node_id >= node_count:
                raise ValueError(
                    f"dense edge line {line_number} references node id out of range: {primary_node_id}",
                )
            counts[primary_node_id] += 1
            edge_count += 1

    offsets = [0]
    running_total = 0
    for count in counts:
        running_total += count
        offsets.append(
            running_total,
        )

    return tuple(offsets), edge_count


def _build_offsets_from_grouped_links(
    *,
    grouped_links_file_path: Path,
    page_id_to_node_id: dict[int, int],
    node_count: int,
    primary_is_source: bool,
    progress_label: str,
    progress_callback: Callable[[str], None] | None,
) -> tuple[tuple[int, ...], int]:
    counts = [0] * node_count
    edge_count = 0
    with gzip.open(
        grouped_links_file_path,
        "rt",
        encoding="utf-8",
    ) as file_handle:
        for line_number, raw_line in enumerate(
            file_handle,
            start=1,
        ):
            line = raw_line.rstrip("\n")
            if not line:
                continue
            primary_node_id, neighbor_node_ids = _parse_grouped_links_line_to_dense_ids(
                line=line,
                line_number=line_number,
                page_id_to_node_id=page_id_to_node_id,
                primary_is_source=primary_is_source,
            )
            if primary_node_id < 0 or primary_node_id >= node_count:
                raise ValueError(
                    f"grouped links line {line_number} references node id out of range: {primary_node_id}",
                )
            counts[primary_node_id] = len(
                neighbor_node_ids,
            )
            edge_count += len(
                neighbor_node_ids,
            )
            if line_number % 250_000 == 0:
                _log_progress(
                    progress_callback,
                    f"{progress_label}: processed {line_number:,} grouped rows and {edge_count:,} edges",
                )

    offsets = [0]
    running_total = 0
    for count in counts:
        running_total += count
        offsets.append(
            running_total,
        )

    return tuple(offsets), edge_count


def _write_grouped_neighbors_section(
    *,
    grouped_links_file_path: Path,
    page_id_to_node_id: dict[int, int],
    offsets: tuple[int, ...],
    section_offset: int,
    primary_is_source: bool,
    output_file_handle,
    progress_label: str,
    progress_callback: Callable[[str], None] | None,
) -> None:
    with gzip.open(
        grouped_links_file_path,
        "rt",
        encoding="utf-8",
    ) as file_handle:
        for line_number, raw_line in enumerate(
            file_handle,
            start=1,
        ):
            line = raw_line.rstrip("\n")
            if not line:
                continue
            primary_node_id, neighbor_node_ids = _parse_grouped_links_line_to_dense_ids(
                line=line,
                line_number=line_number,
                page_id_to_node_id=page_id_to_node_id,
                primary_is_source=primary_is_source,
            )
            if not neighbor_node_ids:
                continue
            output_file_handle.seek(
                section_offset + (offsets[primary_node_id] * 3),
            )
            output_file_handle.write(
                pack_u24_values(
                    list(neighbor_node_ids),
                ),
            )
            if line_number % 250_000 == 0:
                _log_progress(
                    progress_callback,
                    f"{progress_label}: processed {line_number:,} grouped rows",
                )


def _write_neighbor_column_as_u24(
    *,
    sorted_dense_edges_path: Path,
    output_file_handle,
    neighbor_column_index: int,
) -> None:
    with sorted_dense_edges_path.open(
        "rt",
        encoding="utf-8",
    ) as file_handle:
        for line_number, raw_line in enumerate(
            file_handle,
            start=1,
        ):
            line = raw_line.rstrip("\n")
            if not line:
                continue
            source_node_id, target_node_id = _parse_dense_edge_line(
                line=line,
                line_number=line_number,
            )
            neighbor_node_id = (
                target_node_id if neighbor_column_index == 1 else source_node_id
            )
            output_file_handle.write(
                _pack_single_u24(
                    neighbor_node_id,
                ),
            )


def _parse_dense_edge_line(
    *,
    line: str,
    line_number: int,
) -> tuple[int, int]:
    parts = line.split("\t")
    if len(parts) < 2:
        raise ValueError(
            f"dense edge line {line_number} has {len(parts)} columns, expected 2",
        )
    return int(parts[0]), int(parts[1])


def _parse_grouped_links_line_to_dense_ids(
    *,
    line: str,
    line_number: int,
    page_id_to_node_id: dict[int, int],
    primary_is_source: bool,
) -> tuple[int, tuple[int, ...]]:
    parts = line.split("\t")
    if len(parts) < 2:
        raise ValueError(
            f"grouped links line {line_number} has {len(parts)} columns, expected 2",
        )

    primary_page_id = int(parts[0])
    if primary_page_id not in page_id_to_node_id:
        role = "source" if primary_is_source else "target"
        raise ValueError(
            f"grouped links line {line_number} references unknown canonical {role} page id {primary_page_id}",
        )

    neighbor_page_ids = [
        int(page_id_text) for page_id_text in parts[1].split("|") if page_id_text
    ]
    neighbor_node_ids = []
    for neighbor_page_id in neighbor_page_ids:
        if neighbor_page_id not in page_id_to_node_id:
            role = "target" if primary_is_source else "source"
            raise ValueError(
                f"grouped links line {line_number} references unknown canonical {role} page id {neighbor_page_id}",
            )
        neighbor_node_ids.append(
            page_id_to_node_id[neighbor_page_id],
        )

    deduped_neighbor_node_ids = tuple(
        sorted(
            set(neighbor_node_ids),
        ),
    )
    primary_node_id = page_id_to_node_id[primary_page_id]
    filtered_neighbor_node_ids = tuple(
        neighbor_node_id
        for neighbor_node_id in deduped_neighbor_node_ids
        if neighbor_node_id != primary_node_id
    )
    return primary_node_id, filtered_neighbor_node_ids


def _pack_u32_values(
    values: tuple[int, ...],
) -> bytes:
    return b"".join(
        U32_STRUCT.pack(
            value,
        )
        for value in values
    )


def _pack_single_u24(
    value: int,
) -> bytes:
    return pack_u24_values(
        [value],
    )


def _log_progress(
    progress_callback: Callable[[str], None] | None,
    message: str,
) -> None:
    if progress_callback is None:
        return
    progress_callback(
        message,
    )
