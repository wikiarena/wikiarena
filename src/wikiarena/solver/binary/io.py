from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from wikiarena.solver.binary.format import (
    SOLVER_BINARY_MAGIC,
    SOLVER_BINARY_VERSION,
    SOLVER_HEADER_BYTES,
    SOLVER_HEADER_STRUCT,
    U24_MAX,
    pack_u24_values,
    unpack_u24_values,
)
from wikiarena.solver.binary.titles import (
    build_canonical_title_table,
    decode_canonical_title_table,
)

U32_STRUCT = struct.Struct("<I")


@dataclass(frozen=True)
class SolverBinaryData:
    canonical_titles: tuple[str, ...]
    out_offsets: tuple[int, ...]
    out_neighbors: tuple[int, ...]
    in_offsets: tuple[int, ...]
    in_neighbors: tuple[int, ...]

    @property
    def node_count(
        self,
    ) -> int:
        return len(
            self.canonical_titles,
        )

    @property
    def edge_count(
        self,
    ) -> int:
        return len(
            self.out_neighbors,
        )


def write_solver_binary(
    *,
    file_path: Path,
    data: SolverBinaryData,
) -> None:
    validate_solver_binary_data(
        data,
    )

    output_path = file_path

    canonical_title_table = build_canonical_title_table(
        data.canonical_titles,
    )
    canonical_offsets_bytes = _pack_u32_values(
        canonical_title_table.offsets,
    )
    canonical_bytes = canonical_title_table.title_bytes
    out_offsets_bytes = _pack_u32_values(
        data.out_offsets,
    )
    out_neighbors_bytes = pack_u24_values(
        data.out_neighbors,
    )
    in_offsets_bytes = _pack_u32_values(
        data.in_offsets,
    )
    in_neighbors_bytes = pack_u24_values(
        data.in_neighbors,
    )

    canonical_offsets_off = SOLVER_HEADER_BYTES
    canonical_bytes_off = canonical_offsets_off + len(canonical_offsets_bytes)
    out_offsets_off = canonical_bytes_off + len(canonical_bytes)
    out_neighbors_off = out_offsets_off + len(out_offsets_bytes)
    in_offsets_off = out_neighbors_off + len(out_neighbors_bytes)
    in_neighbors_off = in_offsets_off + len(in_offsets_bytes)
    file_bytes = in_neighbors_off + len(in_neighbors_bytes)

    header_bytes = SOLVER_HEADER_STRUCT.pack(
        SOLVER_BINARY_MAGIC,
        SOLVER_BINARY_VERSION,
        SOLVER_HEADER_BYTES,
        data.node_count,
        data.edge_count,
        canonical_offsets_off,
        canonical_bytes_off,
        out_offsets_off,
        out_neighbors_off,
        in_offsets_off,
        in_neighbors_off,
        file_bytes,
    )

    with output_path.open(
        "wb",
    ) as file_handle:
        file_handle.write(
            b"\x00" * SOLVER_HEADER_BYTES,
        )
        file_handle.write(
            canonical_offsets_bytes,
        )
        file_handle.write(
            canonical_bytes,
        )
        file_handle.write(
            out_offsets_bytes,
        )
        file_handle.write(
            out_neighbors_bytes,
        )
        file_handle.write(
            in_offsets_bytes,
        )
        file_handle.write(
            in_neighbors_bytes,
        )
        file_handle.seek(
            0,
        )
        file_handle.write(
            header_bytes,
        )


def load_solver_binary(
    *,
    file_path: Path,
) -> SolverBinaryData:
    input_path = file_path
    file_bytes = input_path.read_bytes()
    if len(file_bytes) < SOLVER_HEADER_BYTES:
        raise ValueError(
            "solver binary is smaller than the header",
        )

    header = SOLVER_HEADER_STRUCT.unpack(
        file_bytes[:SOLVER_HEADER_BYTES],
    )
    (
        magic,
        version,
        header_bytes,
        node_count,
        edge_count,
        canonical_offsets_off,
        canonical_bytes_off,
        out_offsets_off,
        out_neighbors_off,
        in_offsets_off,
        in_neighbors_off,
        declared_file_bytes,
    ) = header

    if magic != SOLVER_BINARY_MAGIC:
        raise ValueError(
            f"unexpected solver binary magic: {magic!r}",
        )
    if version != SOLVER_BINARY_VERSION:
        raise ValueError(
            f"unsupported solver binary version: {version}",
        )
    if header_bytes != SOLVER_HEADER_BYTES:
        raise ValueError(
            f"unexpected solver header size: {header_bytes}",
        )
    if declared_file_bytes != len(file_bytes):
        raise ValueError(
            "solver binary size does not match header",
        )

    _validate_monotonic_offsets(
        [
            canonical_offsets_off,
            canonical_bytes_off,
            out_offsets_off,
            out_neighbors_off,
            in_offsets_off,
            in_neighbors_off,
            declared_file_bytes,
        ],
    )

    canonical_offsets = _unpack_u32_values(
        file_bytes[canonical_offsets_off:canonical_bytes_off],
    )
    if len(canonical_offsets) != node_count + 1:
        raise ValueError(
            "canonical title offsets length does not match node count",
        )
    canonical_bytes = file_bytes[canonical_bytes_off:out_offsets_off]
    canonical_title_table = decode_canonical_title_table(
        offsets=canonical_offsets,
        title_bytes=canonical_bytes,
    )
    canonical_titles = canonical_title_table.to_titles()

    out_offsets = _unpack_u32_values(
        file_bytes[out_offsets_off:out_neighbors_off],
    )
    if len(out_offsets) != node_count + 1:
        raise ValueError(
            "outgoing offsets length does not match node count",
        )

    out_neighbors = unpack_u24_values(
        file_bytes[out_neighbors_off:in_offsets_off],
    )
    if len(out_neighbors) != edge_count:
        raise ValueError(
            "outgoing neighbor count does not match edge count",
        )

    in_offsets = _unpack_u32_values(
        file_bytes[in_offsets_off:in_neighbors_off],
    )
    if len(in_offsets) != node_count + 1:
        raise ValueError(
            "incoming offsets length does not match node count",
        )

    in_neighbors = unpack_u24_values(
        file_bytes[in_neighbors_off:declared_file_bytes],
    )
    if len(in_neighbors) != edge_count:
        raise ValueError(
            "incoming neighbor count does not match edge count",
        )

    data = SolverBinaryData(
        canonical_titles=canonical_titles,
        out_offsets=out_offsets,
        out_neighbors=out_neighbors,
        in_offsets=in_offsets,
        in_neighbors=in_neighbors,
    )
    validate_solver_binary_data(
        data,
    )
    return data


def validate_solver_binary_data(
    data: SolverBinaryData,
) -> None:
    node_count = data.node_count
    edge_count = data.edge_count

    if node_count > U24_MAX:
        raise ValueError(
            f"node count exceeds u24 capacity: {node_count}",
        )

    if len(set(data.canonical_titles)) != node_count:
        raise ValueError(
            "canonical titles must be unique",
        )

    if tuple(sorted(data.canonical_titles)) != data.canonical_titles:
        raise ValueError(
            "canonical titles must be lexicographically sorted",
        )

    if len(data.out_offsets) != node_count + 1:
        raise ValueError(
            "outgoing offsets length must equal node count plus one",
        )

    if len(data.in_offsets) != node_count + 1:
        raise ValueError(
            "incoming offsets length must equal node count plus one",
        )

    _validate_offsets(
        offsets=data.out_offsets,
        expected_last=edge_count,
        label="outgoing",
    )
    _validate_offsets(
        offsets=data.in_offsets,
        expected_last=edge_count,
        label="incoming",
    )

    _validate_neighbors(
        node_count=node_count,
        offsets=data.out_offsets,
        neighbors=data.out_neighbors,
        label="outgoing",
    )
    _validate_neighbors(
        node_count=node_count,
        offsets=data.in_offsets,
        neighbors=data.in_neighbors,
        label="incoming",
    )


def _pack_u32_values(
    values: tuple[int, ...],
) -> bytes:
    return b"".join(
        U32_STRUCT.pack(
            value,
        )
        for value in values
    )


def _unpack_u32_values(
    buffer: bytes,
) -> tuple[int, ...]:
    if len(buffer) % U32_STRUCT.size != 0:
        raise ValueError(
            "u32 buffer length must be divisible by 4",
        )
    return tuple(
        value[0]
        for value in U32_STRUCT.iter_unpack(
            buffer,
        )
    )


def _validate_offsets(
    *,
    offsets: tuple[int, ...],
    expected_last: int,
    label: str,
) -> None:
    if not offsets:
        raise ValueError(
            f"{label} offsets cannot be empty",
        )
    if offsets[0] != 0:
        raise ValueError(
            f"{label} offsets must start at zero",
        )
    if offsets[-1] != expected_last:
        raise ValueError(
            f"{label} offsets must end at edge count {expected_last}",
        )
    for previous, current in zip(offsets, offsets[1:]):
        if current < previous:
            raise ValueError(
                f"{label} offsets must be monotonic",
            )


def _validate_neighbors(
    *,
    node_count: int,
    offsets: tuple[int, ...],
    neighbors: tuple[int, ...],
    label: str,
) -> None:
    for node_id, (start, end) in enumerate(
        zip(offsets, offsets[1:]),
    ):
        adjacency = neighbors[start:end]
        previous_neighbor = -1
        for neighbor in adjacency:
            if neighbor < 0 or neighbor >= node_count:
                raise ValueError(
                    f"{label} neighbor id out of range for node {node_id}: {neighbor}",
                )
            if neighbor <= previous_neighbor:
                raise ValueError(
                    f"{label} adjacency must be strictly sorted for node {node_id}",
                )
            previous_neighbor = neighbor


def _validate_monotonic_offsets(
    offsets: list[int],
) -> None:
    previous = SOLVER_HEADER_BYTES
    for offset in offsets:
        if offset < previous:
            raise ValueError(
                "solver binary section offsets must be monotonic",
            )
        previous = offset
