from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

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
