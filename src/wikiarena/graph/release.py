from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from wikiarena.solver.binary import MappedBinarySolverGraph


@dataclass(frozen=True)
class GraphArtifactMetadata:
    file_name: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class GraphCoreMetadata(GraphArtifactMetadata):
    node_count: int
    edge_count: int


@dataclass(frozen=True)
class GraphReleaseMetadata:
    wiki: str
    dump_date: str
    snapshot_id: str | None
    generated_at_utc: str
    git_sha: str | None
    graph: GraphCoreMetadata
    compressed: GraphArtifactMetadata

    def to_dict(
        self,
    ) -> dict[str, object]:
        return asdict(
            self,
        )


def graph_release_metadata_from_dict(
    payload: Mapping[str, Any],
) -> GraphReleaseMetadata:
    graph_payload = _require_mapping(
        payload,
        "graph",
    )
    compressed_payload = _require_mapping(
        payload,
        "compressed",
    )
    return GraphReleaseMetadata(
        wiki=_require_str(
            payload,
            "wiki",
        ),
        dump_date=_require_str(
            payload,
            "dump_date",
        ),
        snapshot_id=_optional_str(
            payload,
            "snapshot_id",
        ),
        generated_at_utc=_require_str(
            payload,
            "generated_at_utc",
        ),
        git_sha=_optional_str(
            payload,
            "git_sha",
        ),
        graph=GraphCoreMetadata(
            file_name=_require_str(
                graph_payload,
                "file_name",
            ),
            bytes=_require_int(
                graph_payload,
                "bytes",
            ),
            sha256=_require_str(
                graph_payload,
                "sha256",
            ),
            node_count=_require_int(
                graph_payload,
                "node_count",
            ),
            edge_count=_require_int(
                graph_payload,
                "edge_count",
            ),
        ),
        compressed=GraphArtifactMetadata(
            file_name=_require_str(
                compressed_payload,
                "file_name",
            ),
            bytes=_require_int(
                compressed_payload,
                "bytes",
            ),
            sha256=_require_str(
                compressed_payload,
                "sha256",
            ),
        ),
    )


def load_graph_release_metadata(
    metadata_path: Path,
) -> GraphReleaseMetadata:
    return graph_release_metadata_from_dict(
        json.loads(
            metadata_path.read_text(
                encoding="utf-8",
            ),
        ),
    )


def build_graph_release_metadata(
    *,
    graph_file_path: Path,
    compressed_file_path: Path,
    dump_date: str,
    snapshot_id: str | None = None,
    wiki: str = "enwiki",
    git_sha: str | None = None,
) -> GraphReleaseMetadata:
    graph_path = graph_file_path
    compressed_path = compressed_file_path
    with MappedBinarySolverGraph(
        file_path=graph_path,
    ) as graph:
        return GraphReleaseMetadata(
            wiki=wiki,
            dump_date=dump_date,
            snapshot_id=snapshot_id,
            generated_at_utc=datetime.now(
                UTC,
            ).isoformat(),
            git_sha=git_sha if git_sha is not None else os.getenv("GITHUB_SHA"),
            graph=GraphCoreMetadata(
                file_name=graph_path.name,
                bytes=graph_path.stat().st_size,
                sha256=sha256_file(
                    graph_path,
                ),
                node_count=graph.node_count,
                edge_count=graph.edge_count,
            ),
            compressed=GraphArtifactMetadata(
                file_name=compressed_path.name,
                bytes=compressed_path.stat().st_size,
                sha256=sha256_file(
                    compressed_path,
                ),
            ),
        )


def sha256_file(
    file_path: Path,
) -> str:
    digest = hashlib.sha256()
    with file_path.open(
        "rb",
    ) as file_handle:
        while True:
            chunk = file_handle.read(
                1024 * 1024,
            )
            if not chunk:
                break
            digest.update(
                chunk,
            )
    return digest.hexdigest()


def _require_mapping(
    payload: Mapping[str, Any],
    key: str,
) -> Mapping[str, Any]:
    value = payload.get(
        key,
    )
    if not isinstance(value, Mapping):
        raise ValueError(f"metadata field {key} must be an object")
    return value


def _require_str(
    payload: Mapping[str, Any],
    key: str,
) -> str:
    value = payload.get(
        key,
    )
    if not isinstance(value, str) or not value:
        raise ValueError(f"metadata field {key} must be a non-empty string")
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
            f"metadata field {key} must be a non-empty string when present",
        )
    return value


def _require_int(
    payload: Mapping[str, Any],
    key: str,
) -> int:
    value = payload.get(
        key,
    )
    if not isinstance(value, int):
        raise ValueError(f"metadata field {key} must be an integer")
    return value
