from __future__ import annotations

import struct

SOLVER_BINARY_MAGIC = b"WASOLV1\0"
SOLVER_BINARY_VERSION = 1
U24_MAX = (1 << 24) - 1

SOLVER_HEADER_STRUCT = struct.Struct(
    "<8sIIIIQQQQQQQ",
)
SOLVER_HEADER_BYTES = SOLVER_HEADER_STRUCT.size


def pack_u24_values(
    values: list[int] | tuple[int, ...],
) -> bytes:
    buffer = bytearray()
    for value in values:
        if value < 0 or value > U24_MAX:
            raise ValueError(
                f"u24 value out of range: {value}",
            )
        buffer.extend(
            (
                value & 0xFF,
                (value >> 8) & 0xFF,
                (value >> 16) & 0xFF,
            ),
        )
    return bytes(
        buffer,
    )


def unpack_u24_values(
    buffer: bytes,
) -> tuple[int, ...]:
    if len(buffer) % 3 != 0:
        raise ValueError(
            "u24 buffer length must be divisible by 3",
        )

    values: list[int] = []
    for index in range(
        0,
        len(buffer),
        3,
    ):
        values.append(
            buffer[index] | (buffer[index + 1] << 8) | (buffer[index + 2] << 16),
        )
    return tuple(
        values,
    )
