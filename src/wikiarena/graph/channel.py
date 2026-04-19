from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from wikiarena.graph.naming import graph_snapshot_id
from wikiarena.graph.release import GraphReleaseMetadata


@dataclass(frozen=True)
class GraphChannelManifest:
    channel: str
    wiki: str
    dump_date: str
    snapshot_id: str
    graph_key: str
    checksum_key: str
    metadata_key: str
    promoted_at_utc: str
    promoted_by: str | None = None
    source_release_tag: str | None = None
    source_run_id: str | None = None

    def to_dict(
        self,
    ) -> dict[str, object]:
        return asdict(
            self,
        )


def build_graph_channel_manifest(
    *,
    channel: str,
    release_metadata: GraphReleaseMetadata,
    graph_key: str,
    checksum_key: str,
    metadata_key: str,
    promoted_at_utc: str | None = None,
    promoted_by: str | None = None,
    source_release_tag: str | None = None,
    source_run_id: str | None = None,
) -> GraphChannelManifest:
    snapshot_id = release_metadata.snapshot_id
    if snapshot_id is None:
        snapshot_id = graph_snapshot_id(
            wiki=release_metadata.wiki,
            dump_date=release_metadata.dump_date,
        )

    resolved_source_release_tag = source_release_tag
    if resolved_source_release_tag is None:
        resolved_source_release_tag = (
            f"graph-{release_metadata.wiki}-{release_metadata.dump_date}"
        )

    return GraphChannelManifest(
        channel=channel,
        wiki=release_metadata.wiki,
        dump_date=release_metadata.dump_date,
        snapshot_id=snapshot_id,
        graph_key=graph_key,
        checksum_key=checksum_key,
        metadata_key=metadata_key,
        promoted_at_utc=(
            promoted_at_utc
            if promoted_at_utc is not None
            else datetime.now(
                UTC,
            ).isoformat()
        ),
        promoted_by=promoted_by,
        source_release_tag=resolved_source_release_tag,
        source_run_id=source_run_id,
    )


def graph_channel_manifest_from_dict(
    payload: Mapping[str, Any],
) -> GraphChannelManifest:
    return GraphChannelManifest(
        channel=_require_str(
            payload,
            "channel",
        ),
        wiki=_require_str(
            payload,
            "wiki",
        ),
        dump_date=_require_str(
            payload,
            "dump_date",
        ),
        snapshot_id=_require_str(
            payload,
            "snapshot_id",
        ),
        graph_key=_require_str(
            payload,
            "graph_key",
        ),
        checksum_key=_require_str(
            payload,
            "checksum_key",
        ),
        metadata_key=_require_str(
            payload,
            "metadata_key",
        ),
        promoted_at_utc=_require_str(
            payload,
            "promoted_at_utc",
        ),
        promoted_by=_optional_str(
            payload,
            "promoted_by",
        ),
        source_release_tag=_optional_str(
            payload,
            "source_release_tag",
        ),
        source_run_id=_optional_str(
            payload,
            "source_run_id",
        ),
    )


def load_graph_channel_manifest(
    manifest_path: Path,
) -> GraphChannelManifest:
    return graph_channel_manifest_from_dict(
        json.loads(
            manifest_path.read_text(
                encoding="utf-8",
            ),
        ),
    )


def graph_channel_manifest_key(
    *,
    wiki: str,
    channel: str,
) -> str:
    return f"graphs/{wiki}/channels/{channel}.json"


def _require_str(
    payload: Mapping[str, Any],
    key: str,
) -> str:
    value = payload.get(
        key,
    )
    if not isinstance(value, str) or not value:
        raise ValueError(f"channel manifest field {key} must be a non-empty string")
    return value


def _optional_str(
    payload: Mapping[str, Any],
    key: str,
) -> str | None:
    value = payload.get(
        key,
    )
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"channel manifest field {key} must be a non-empty string when present",
        )
    return value
