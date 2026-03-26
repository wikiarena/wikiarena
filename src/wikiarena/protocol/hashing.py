from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(
    value: Any,
) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def stable_sha256(
    value: Any,
) -> str:
    canonical = canonical_json(
        value,
    ).encode(
        "utf-8",
    )
    return hashlib.sha256(
        canonical,
    ).hexdigest()
