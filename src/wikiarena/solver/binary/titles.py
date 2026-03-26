from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CanonicalTitleTable:
    offsets: tuple[int, ...]
    title_bytes: bytes

    @property
    def node_count(
        self,
    ) -> int:
        return (
            len(
                self.offsets,
            )
            - 1
        )

    def title_for_node_id(
        self,
        node_id: int,
    ) -> str:
        if node_id < 0 or node_id >= self.node_count:
            raise IndexError(
                f"node id out of range: {node_id}",
            )
        return self._decode_title_slice(
            self.offsets[node_id],
            self.offsets[node_id + 1],
        )

    def find_node_id(
        self,
        title: str,
    ) -> int | None:
        low = 0
        high = self.node_count - 1

        while low <= high:
            middle = low + ((high - low) // 2)
            middle_title = self.title_for_node_id(
                middle,
            )
            if middle_title == title:
                return middle
            if middle_title < title:
                low = middle + 1
            else:
                high = middle - 1

        return None

    def to_titles(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            self.title_for_node_id(
                node_id,
            )
            for node_id in range(
                self.node_count,
            )
        )

    def _decode_title_slice(
        self,
        start: int,
        end: int,
    ) -> str:
        return self.title_bytes[start:end].decode(
            "utf-8",
        )


def build_canonical_title_table(
    canonical_titles: tuple[str, ...],
) -> CanonicalTitleTable:
    if tuple(sorted(canonical_titles)) != canonical_titles:
        raise ValueError(
            "canonical titles must be lexicographically sorted",
        )
    if len(set(canonical_titles)) != len(canonical_titles):
        raise ValueError(
            "canonical titles must be unique",
        )

    offsets = [0]
    title_bytes = bytearray()
    for title in canonical_titles:
        encoded_title = title.encode(
            "utf-8",
        )
        title_bytes.extend(
            encoded_title,
        )
        offsets.append(
            len(title_bytes),
        )

    return CanonicalTitleTable(
        offsets=tuple(offsets),
        title_bytes=bytes(title_bytes),
    )


def decode_canonical_title_table(
    *,
    offsets: tuple[int, ...],
    title_bytes: bytes,
) -> CanonicalTitleTable:
    if not offsets:
        raise ValueError(
            "canonical title offsets cannot be empty",
        )
    if offsets[0] != 0:
        raise ValueError(
            "canonical title offsets must start at zero",
        )
    if offsets[-1] != len(title_bytes):
        raise ValueError(
            "canonical title bytes length does not match offsets",
        )

    previous_offset = 0
    for offset in offsets[1:]:
        if offset < previous_offset:
            raise ValueError(
                "canonical title offsets must be monotonic",
            )
        previous_offset = offset

    title_table = CanonicalTitleTable(
        offsets=offsets,
        title_bytes=title_bytes,
    )
    titles = title_table.to_titles()
    if tuple(sorted(titles)) != titles:
        raise ValueError(
            "decoded canonical titles must be lexicographically sorted",
        )
    if len(set(titles)) != len(titles):
        raise ValueError(
            "decoded canonical titles must be unique",
        )
    return title_table
