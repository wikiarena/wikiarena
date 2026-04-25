from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from wikiarena.graph.naming import (
    graph_metadata_file_name,
    graph_snapshot_id,
    parse_standard_graph_file_name,
)
from wikiarena.graph.release import load_graph_release_metadata, sha256_file
from wikiarena.solver.binary import MappedBinarySolverGraph


@dataclass(frozen=True)
class GraphInfoResult:
    graph_path: Path
    metadata_path: Path
    metadata_present: bool
    selected_via: str
    snapshot_id: str | None
    wiki: str | None
    dump_date: str | None
    release_tag: str | None
    node_count: int
    edge_count: int
    file_size_bytes: int
    graph_sha256: str | None
    metadata_generated_at_utc: str | None
    metadata_git_sha: str | None
    verified: bool

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "graph_path": str(self.graph_path),
            "metadata_path": str(self.metadata_path),
            "metadata_present": self.metadata_present,
            "selected_via": self.selected_via,
            "snapshot_id": self.snapshot_id,
            "wiki": self.wiki,
            "dump_date": self.dump_date,
            "release_tag": self.release_tag,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "file_size_bytes": self.file_size_bytes,
            "graph_sha256": self.graph_sha256,
            "metadata_generated_at_utc": self.metadata_generated_at_utc,
            "metadata_git_sha": self.metadata_git_sha,
            "verified": self.verified,
        }


def load_graph_info(
    *,
    graph_path: Path | None = None,
    verify: bool = False,
) -> GraphInfoResult:
    from wikiarena.wiki_runtime import resolve_graph_selection

    graph_selection = resolve_graph_selection(
        graph_path,
    )
    metadata_path = infer_graph_metadata_path(
        graph_selection.graph_path,
    )
    metadata_present = metadata_path.exists()
    if verify and not metadata_present:
        raise FileNotFoundError(
            f"graph metadata file not found: {metadata_path}",
        )

    metadata = None
    if metadata_present:
        metadata = load_graph_release_metadata(
            metadata_path,
        )
        if metadata.graph.file_name != graph_selection.graph_path.name:
            raise ValueError(
                "graph metadata file_name does not match the selected graph file",
            )

    parsed_graph_file_name = parse_standard_graph_file_name(
        graph_selection.graph_path.name,
    )
    inferred_wiki = None
    inferred_dump_date = None
    if parsed_graph_file_name is not None:
        inferred_wiki, inferred_dump_date = parsed_graph_file_name

    wiki = metadata.wiki if metadata is not None else inferred_wiki
    dump_date = metadata.dump_date if metadata is not None else inferred_dump_date
    snapshot_id = _resolve_snapshot_id(
        metadata_snapshot_id=(metadata.snapshot_id if metadata is not None else None),
        wiki=wiki,
        dump_date=dump_date,
    )

    with MappedBinarySolverGraph(
        file_path=graph_selection.graph_path,
    ) as graph:
        node_count = graph.node_count
        edge_count = graph.edge_count

    file_size_bytes = graph_selection.graph_path.stat().st_size
    graph_sha256 = None
    if verify:
        graph_sha256 = sha256_file(
            graph_selection.graph_path,
        )
        assert metadata is not None
        if metadata.graph.bytes != file_size_bytes:
            raise ValueError(
                "graph file size does not match the metadata",
            )
        if metadata.graph.sha256 != graph_sha256:
            raise ValueError(
                "graph checksum does not match the metadata",
            )
        if metadata.graph.node_count != node_count:
            raise ValueError(
                "graph node_count does not match the metadata",
            )
        if metadata.graph.edge_count != edge_count:
            raise ValueError(
                "graph edge_count does not match the metadata",
            )

    release_tag = None
    if wiki is not None and dump_date is not None:
        release_tag = f"graph-{wiki}-{dump_date}"

    return GraphInfoResult(
        graph_path=graph_selection.graph_path,
        metadata_path=metadata_path.resolve(),
        metadata_present=metadata_present,
        selected_via=graph_selection.selected_via,
        snapshot_id=snapshot_id,
        wiki=wiki,
        dump_date=dump_date,
        release_tag=release_tag,
        node_count=node_count,
        edge_count=edge_count,
        file_size_bytes=file_size_bytes,
        graph_sha256=graph_sha256,
        metadata_generated_at_utc=(
            metadata.generated_at_utc if metadata is not None else None
        ),
        metadata_git_sha=(metadata.git_sha if metadata is not None else None),
        verified=verify,
    )


def infer_graph_metadata_path(
    graph_path: Path,
) -> Path:
    parsed = parse_standard_graph_file_name(
        graph_path.name,
    )
    if parsed is not None:
        wiki, dump_date = parsed
        return (
            graph_path.parent / graph_metadata_file_name(wiki=wiki, dump_date=dump_date)
        ).resolve()
    metadata_file_name = (
        graph_path.name.removesuffix(graph_path.suffix) + ".metadata.json"
    )
    return graph_path.with_name(
        metadata_file_name,
    ).resolve()


def _resolve_snapshot_id(
    *,
    metadata_snapshot_id: str | None,
    wiki: str | None,
    dump_date: str | None,
) -> str | None:
    if metadata_snapshot_id is not None:
        return metadata_snapshot_id
    if wiki is None or dump_date is None:
        return None
    return graph_snapshot_id(
        wiki=wiki,
        dump_date=dump_date,
    )
