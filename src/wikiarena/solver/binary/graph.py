from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from wikiarena.solver.binary.io import SolverBinaryData
from wikiarena.solver.binary.titles import (
    CanonicalTitleTable,
    build_canonical_title_table,
)


@dataclass(frozen=True)
class BinarySolverGraph:
    title_table: CanonicalTitleTable
    out_offsets: tuple[int, ...]
    out_neighbors: tuple[int, ...]
    in_offsets: tuple[int, ...]
    in_neighbors: tuple[int, ...]

    @classmethod
    def from_solver_binary_data(
        cls,
        data: SolverBinaryData,
    ) -> "BinarySolverGraph":
        return cls(
            title_table=build_canonical_title_table(
                data.canonical_titles,
            ),
            out_offsets=data.out_offsets,
            out_neighbors=data.out_neighbors,
            in_offsets=data.in_offsets,
            in_neighbors=data.in_neighbors,
        )

    @property
    def node_count(
        self,
    ) -> int:
        return self.title_table.node_count

    @property
    def edge_count(
        self,
    ) -> int:
        return len(
            self.out_neighbors,
        )

    def find_node_id(
        self,
        title: str,
    ) -> int | None:
        for normalized_title in _lookup_title_candidates(
            title,
        ):
            node_id = self.title_table.find_node_id(
                normalized_title,
            )
            if node_id is not None:
                return node_id
        return None

    def title_for_node_id(
        self,
        node_id: int,
    ) -> str:
        return _denormalize_stored_title(
            self.title_table.title_for_node_id(
                node_id,
            ),
        )

    def outgoing_neighbors(
        self,
        node_id: int,
    ) -> tuple[int, ...]:
        start = self.out_offsets[node_id]
        end = self.out_offsets[node_id + 1]
        return self.out_neighbors[start:end]

    def incoming_neighbors(
        self,
        node_id: int,
    ) -> tuple[int, ...]:
        start = self.in_offsets[node_id]
        end = self.in_offsets[node_id + 1]
        return self.in_neighbors[start:end]

    def iter_outgoing_neighbors(
        self,
        node_id: int,
    ) -> Iterator[int]:
        return iter(
            self.outgoing_neighbors(
                node_id,
            ),
        )

    def iter_incoming_neighbors(
        self,
        node_id: int,
    ) -> Iterator[int]:
        return iter(
            self.incoming_neighbors(
                node_id,
            ),
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
    sql_escaped_title = (
        normalized_title.replace(
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
    if sql_escaped_title == normalized_title:
        return (normalized_title,)
    return (
        normalized_title,
        sql_escaped_title,
    )


def _denormalize_stored_title(
    title: str,
) -> str:
    return (
        title.replace(
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
