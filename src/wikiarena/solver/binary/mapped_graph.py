from __future__ import annotations

import mmap
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from wikiarena.solver.binary.format import (
    SOLVER_BINARY_MAGIC,
    SOLVER_BINARY_VERSION,
    SOLVER_HEADER_BYTES,
    SOLVER_HEADER_STRUCT,
)

U32_STRUCT = struct.Struct("<I")


@dataclass(frozen=True)
class SolverBinaryHeader:
    node_count: int
    edge_count: int
    canonical_offsets_off: int
    canonical_bytes_off: int
    out_offsets_off: int
    out_neighbors_off: int
    in_offsets_off: int
    in_neighbors_off: int
    file_bytes: int


class MappedBinarySolverGraph:
    def __init__(
        self,
        *,
        file_path: Path,
    ):
        self.file_path = file_path
        self._file_handle = self.file_path.open(
            "rb",
        )
        self._mapped_bytes = mmap.mmap(
            self._file_handle.fileno(),
            0,
            access=mmap.ACCESS_READ,
        )
        self.header = self._load_header()

    def close(
        self,
    ) -> None:
        self._mapped_bytes.close()
        self._file_handle.close()

    def __enter__(
        self,
    ) -> "MappedBinarySolverGraph":
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> None:
        self.close()

    @property
    def node_count(
        self,
    ) -> int:
        return self.header.node_count

    @property
    def edge_count(
        self,
    ) -> int:
        return self.header.edge_count

    def find_node_id(
        self,
        title: str,
    ) -> int | None:
        for normalized_title in _lookup_title_candidates(
            title,
        ):
            node_id = self._find_node_id_for_stored_title(
                normalized_title,
            )
            if node_id is not None:
                return node_id

        return None

    def _find_node_id_for_stored_title(
        self,
        normalized_title: str,
    ) -> int | None:
        low = 0
        high = self.node_count - 1

        while low <= high:
            middle = low + ((high - low) // 2)
            middle_title = self._stored_title_for_node_id(
                middle,
            )
            if middle_title == normalized_title:
                return middle
            if middle_title < normalized_title:
                low = middle + 1
            else:
                high = middle - 1

        return None

    def title_for_node_id(
        self,
        node_id: int,
    ) -> str:
        return _denormalize_stored_title(
            self._stored_title_for_node_id(
                node_id,
            ),
        )

    def _stored_title_for_node_id(
        self,
        node_id: int,
    ) -> str:
        if node_id < 0 or node_id >= self.node_count:
            raise IndexError(
                f"node id out of range: {node_id}",
            )
        start = self._u32_at(
            self.header.canonical_offsets_off,
            node_id,
        )
        end = self._u32_at(
            self.header.canonical_offsets_off,
            node_id + 1,
        )
        return self._mapped_bytes[
            self.header.canonical_bytes_off + start : self.header.canonical_bytes_off
            + end
        ].decode(
            "utf-8",
        )

    def outgoing_neighbors(
        self,
        node_id: int,
    ) -> tuple[int, ...]:
        return tuple(
            self.iter_outgoing_neighbors(
                node_id,
            ),
        )

    def incoming_neighbors(
        self,
        node_id: int,
    ) -> tuple[int, ...]:
        return tuple(
            self.iter_incoming_neighbors(
                node_id,
            ),
        )

    def outgoing_degree(
        self,
        node_id: int,
    ) -> int:
        start = self._u32_at(
            self.header.out_offsets_off,
            node_id,
        )
        end = self._u32_at(
            self.header.out_offsets_off,
            node_id + 1,
        )
        return end - start

    def incoming_degree(
        self,
        node_id: int,
    ) -> int:
        start = self._u32_at(
            self.header.in_offsets_off,
            node_id,
        )
        end = self._u32_at(
            self.header.in_offsets_off,
            node_id + 1,
        )
        return end - start

    def iter_outgoing_neighbors(
        self,
        node_id: int,
    ) -> Iterator[int]:
        start = self._u32_at(
            self.header.out_offsets_off,
            node_id,
        )
        end = self._u32_at(
            self.header.out_offsets_off,
            node_id + 1,
        )
        for edge_index in range(
            start,
            end,
        ):
            yield self._u24_at(
                self.header.out_neighbors_off,
                edge_index,
            )

    def iter_incoming_neighbors(
        self,
        node_id: int,
    ) -> Iterator[int]:
        start = self._u32_at(
            self.header.in_offsets_off,
            node_id,
        )
        end = self._u32_at(
            self.header.in_offsets_off,
            node_id + 1,
        )
        for edge_index in range(
            start,
            end,
        ):
            yield self._u24_at(
                self.header.in_neighbors_off,
                edge_index,
            )

    def _load_header(
        self,
    ) -> SolverBinaryHeader:
        if len(self._mapped_bytes) < SOLVER_HEADER_BYTES:
            raise ValueError(
                "solver binary is smaller than the header",
            )
        header = SOLVER_HEADER_STRUCT.unpack(
            self._mapped_bytes[:SOLVER_HEADER_BYTES],
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
            file_bytes,
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
        if file_bytes != len(self._mapped_bytes):
            raise ValueError(
                "solver binary size does not match header",
            )

        return SolverBinaryHeader(
            node_count=node_count,
            edge_count=edge_count,
            canonical_offsets_off=canonical_offsets_off,
            canonical_bytes_off=canonical_bytes_off,
            out_offsets_off=out_offsets_off,
            out_neighbors_off=out_neighbors_off,
            in_offsets_off=in_offsets_off,
            in_neighbors_off=in_neighbors_off,
            file_bytes=file_bytes,
        )

    def _u32_at(
        self,
        base_offset: int,
        index: int,
    ) -> int:
        return U32_STRUCT.unpack_from(
            self._mapped_bytes,
            base_offset + (index * U32_STRUCT.size),
        )[0]

    def _u24_at(
        self,
        base_offset: int,
        index: int,
    ) -> int:
        byte_offset = base_offset + (index * 3)
        return (
            self._mapped_bytes[byte_offset]
            | (self._mapped_bytes[byte_offset + 1] << 8)
            | (self._mapped_bytes[byte_offset + 2] << 16)
        )


def _lookup_title_candidates(
    title: str,
) -> tuple[str, ...]:
    normalized_title = title.replace(
        " ",
        "_",
    )
    # TODO: Remove the legacy SQL-escaped fallback once snapshots before
    # 20260401 are no longer supported.
    sql_escaped_title = _escape_sql_title(
        normalized_title,
    )
    if sql_escaped_title == normalized_title:
        return (normalized_title,)
    return (
        normalized_title,
        sql_escaped_title,
    )


def _escape_sql_title(
    title: str,
) -> str:
    return (
        title.replace(
            "\\",
            "\\\\",
        )
        .replace(
            "'",
            "\\'",
        )
        .replace(
            '"',
            '\\"',
        )
    )


def _denormalize_stored_title(
    stored_title: str,
) -> str:
    return (
        stored_title.replace(
            "_",
            " ",
        )
        # TODO: Remove this legacy SQL-unescape path once snapshots before
        # 20260401 are no longer supported.
        .replace(
            '\\"',
            '"',
        )
        .replace(
            "\\'",
            "'",
        )
        .replace(
            "\\\\",
            "\\",
        )
    )
