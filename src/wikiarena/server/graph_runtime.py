from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from pathlib import Path
from typing import Protocol

from wikiarena.graph import parse_standard_graph_file_name
from wikiarena.server.config import ServerConfig
from wikiarena.server.errors import GraphNotReadyError, UnknownTitleError
from wikiarena.server.models import (
    MetaResponse,
    RandomPageTitlesResponse,
    SolveResponse,
)
from wikiarena.solver.binary import (
    MappedBinarySolverGraph,
    search_shortest_path_by_node_ids,
)

logger = logging.getLogger(
    __name__,
)

SNAPSHOT_ID_PATTERN = re.compile(
    r"^(?P<wiki>[A-Za-z0-9_-]+)-(?P<dump_date>\d{8})(?:-.+)?$",
)


class SolverRuntime(Protocol):
    async def startup(
        self,
    ) -> None: ...

    async def shutdown(
        self,
    ) -> None: ...

    def is_ready(
        self,
    ) -> bool: ...

    def get_health_status(
        self,
    ) -> str: ...

    def get_meta(
        self,
    ) -> MetaResponse: ...

    async def random_page_titles(
        self,
        *,
        count: int,
    ) -> RandomPageTitlesResponse: ...

    async def solve(
        self,
        *,
        start_title: str,
        target_title: str,
    ) -> SolveResponse: ...


class GraphSolverRuntime:
    def __init__(
        self,
        config: ServerConfig,
    ):
        self.config = config
        self._graph: MappedBinarySolverGraph | None = None
        self._meta_response: MetaResponse | None = None
        self._health_status = "starting"
        self._startup_error: Exception | None = None

    async def startup(
        self,
    ) -> None:
        if self._graph is not None:
            self._health_status = "ok"
            return

        self._health_status = "starting"
        self._startup_error = None
        try:
            graph, meta_response = await asyncio.to_thread(
                self._load_graph_resources,
            )
        except Exception as error:
            self._health_status = "error"
            self._startup_error = error
            logger.exception(
                "Failed to load solver graph",
            )
            return

        self._graph = graph
        self._meta_response = meta_response
        self._health_status = "ok"
        logger.info(
            "Loaded solver graph for snapshot %s (%s nodes, %s edges)",
            meta_response.snapshot_id,
            meta_response.node_count,
            meta_response.edge_count,
        )

    async def shutdown(
        self,
    ) -> None:
        if self._graph is not None:
            self._graph.close()
        self._graph = None
        self._meta_response = None
        if self._startup_error is None:
            self._health_status = "starting"

    def is_ready(
        self,
    ) -> bool:
        return self._graph is not None and self._meta_response is not None

    def get_health_status(
        self,
    ) -> str:
        return self._health_status

    def get_meta(
        self,
    ) -> MetaResponse:
        if self._meta_response is None:
            raise GraphNotReadyError(
                "Graph is not ready.",
            )
        return self._meta_response

    async def random_page_titles(
        self,
        *,
        count: int,
    ) -> RandomPageTitlesResponse:
        if self._graph is None or self._meta_response is None:
            raise GraphNotReadyError(
                "Graph is not ready.",
            )
        return await asyncio.to_thread(
            self._random_page_titles_sync,
            count,
        )

    async def solve(
        self,
        *,
        start_title: str,
        target_title: str,
    ) -> SolveResponse:
        if self._graph is None or self._meta_response is None:
            raise GraphNotReadyError(
                "Graph is not ready.",
            )
        return await asyncio.to_thread(
            self._solve_sync,
            start_title,
            target_title,
        )

    def _solve_sync(
        self,
        start_title: str,
        target_title: str,
    ) -> SolveResponse:
        graph = self._require_graph()
        meta_response = self._require_meta()

        start_node_id = graph.find_node_id(
            start_title,
        )
        if start_node_id is None:
            raise UnknownTitleError(
                title_role="start",
                title=start_title,
            )

        target_node_id = graph.find_node_id(
            target_title,
        )
        if target_node_id is None:
            raise UnknownTitleError(
                title_role="target",
                title=target_title,
            )

        canonical_start_title = graph.title_for_node_id(
            start_node_id,
        )
        canonical_target_title = graph.title_for_node_id(
            target_node_id,
        )

        started_at = time.perf_counter()
        search_result = search_shortest_path_by_node_ids(
            graph,
            start_node_id=start_node_id,
            target_node_id=target_node_id,
        )
        solve_ms = (time.perf_counter() - started_at) * 1000.0

        if search_result.path_node_ids is None:
            return SolveResponse(
                snapshot_id=meta_response.snapshot_id,
                start_title=canonical_start_title,
                target_title=canonical_target_title,
                path_length=None,
                paths=[],
                solve_ms=solve_ms,
                pages_visited=search_result.pages_visited,
                links_scanned=search_result.links_scanned,
            )

        path_titles = [
            graph.title_for_node_id(
                node_id,
            )
            for node_id in search_result.path_node_ids
        ]
        return SolveResponse(
            snapshot_id=meta_response.snapshot_id,
            start_title=canonical_start_title,
            target_title=canonical_target_title,
            path_length=len(path_titles) - 1,
            paths=[path_titles],
            solve_ms=solve_ms,
            pages_visited=search_result.pages_visited,
            links_scanned=search_result.links_scanned,
        )

    def _random_page_titles_sync(
        self,
        count: int,
    ) -> RandomPageTitlesResponse:
        graph = self._require_graph()
        meta_response = self._require_meta()

        sample_size = min(
            count,
            graph.node_count,
        )
        sampled_node_ids = random.sample(
            range(
                graph.node_count,
            ),
            sample_size,
        )
        sampled_titles = [
            graph.title_for_node_id(
                node_id,
            )
            for node_id in sampled_node_ids
        ]
        return RandomPageTitlesResponse(
            snapshot_id=meta_response.snapshot_id,
            titles=sampled_titles,
        )

    def _load_graph_resources(
        self,
    ) -> tuple[MappedBinarySolverGraph, MetaResponse]:
        graph_path = _require_existing_file(
            self.config.graph_path,
            label="graph",
        )
        metadata_payload = _load_metadata_payload(
            self.config.graph_metadata_path,
        )
        graph = MappedBinarySolverGraph(
            file_path=graph_path,
        )
        try:
            snapshot_id = _resolve_public_snapshot_id(
                graph_path=graph_path,
                metadata_payload=metadata_payload,
                configured_snapshot_id=self.config.snapshot_id,
            )
            dump_date = _resolve_dump_date(
                graph_path=graph_path,
                metadata_payload=metadata_payload,
                snapshot_id=snapshot_id,
            )
            return graph, MetaResponse(
                service_version=self.config.service_version,
                snapshot_id=snapshot_id,
                dump_date=dump_date,
                node_count=graph.node_count,
                edge_count=graph.edge_count,
            )
        except Exception:
            graph.close()
            raise

    def _require_graph(
        self,
    ) -> MappedBinarySolverGraph:
        if self._graph is None:
            raise GraphNotReadyError(
                "Graph is not ready.",
            )
        return self._graph

    def _require_meta(
        self,
    ) -> MetaResponse:
        if self._meta_response is None:
            raise GraphNotReadyError(
                "Graph is not ready.",
            )
        return self._meta_response


def _require_existing_file(
    file_path: Path | None,
    *,
    label: str,
) -> Path:
    if file_path is None:
        raise FileNotFoundError(
            f"{label} path is not configured",
        )
    if file_path.is_dir():
        raise FileNotFoundError(
            f"{label} path is a directory: {file_path}",
        )
    if not file_path.exists():
        raise FileNotFoundError(
            f"{label} file does not exist: {file_path}",
        )
    return file_path.resolve()


def _load_metadata_payload(
    metadata_path: Path | None,
) -> dict[str, object] | None:
    if metadata_path is None:
        return None
    resolved_metadata_path = _require_existing_file(
        metadata_path,
        label="graph metadata",
    )
    return json.loads(
        resolved_metadata_path.read_text(
            encoding="utf-8",
        ),
    )


def _resolve_public_snapshot_id(
    *,
    graph_path: Path,
    metadata_payload: dict[str, object] | None,
    configured_snapshot_id: str | None,
) -> str:
    if configured_snapshot_id is not None:
        return _normalize_public_snapshot_id(
            configured_snapshot_id,
        )

    parsed_metadata = _parse_graph_metadata(
        metadata_payload,
    )
    if (
        parsed_metadata is not None
        and parsed_metadata[0] is not None
        and parsed_metadata[1] is not None
    ):
        wiki, dump_date = parsed_metadata
        assert wiki is not None
        assert dump_date is not None
        return _build_public_snapshot_id(
            wiki=wiki,
            dump_date=dump_date,
        )

    if metadata_payload is not None:
        raw_snapshot_id = metadata_payload.get(
            "snapshot_id",
        )
        if (
            isinstance(
                raw_snapshot_id,
                str,
            )
            and raw_snapshot_id
        ):
            return _normalize_public_snapshot_id(
                raw_snapshot_id,
            )

    parsed_file_name = parse_standard_graph_file_name(
        graph_path.name,
    )
    if parsed_file_name is not None:
        wiki, dump_date = parsed_file_name
        return _build_public_snapshot_id(
            wiki=wiki,
            dump_date=dump_date,
        )

    raise ValueError(
        "Could not determine a public snapshot_id from config, metadata, or graph file name.",
    )


def _resolve_dump_date(
    *,
    graph_path: Path,
    metadata_payload: dict[str, object] | None,
    snapshot_id: str,
) -> str:
    parsed_metadata = _parse_graph_metadata(
        metadata_payload,
    )
    if parsed_metadata is not None and parsed_metadata[1] is not None:
        _, dump_date = parsed_metadata
        assert dump_date is not None
        return dump_date

    inferred_dump_date = _parse_snapshot_id(
        snapshot_id,
    )[1]
    if inferred_dump_date is not None:
        return inferred_dump_date

    parsed_file_name = parse_standard_graph_file_name(
        graph_path.name,
    )
    if parsed_file_name is not None:
        _, dump_date = parsed_file_name
        return dump_date

    raise ValueError(
        "Could not determine dump_date from metadata, snapshot_id, or graph file name.",
    )


def _parse_graph_metadata(
    metadata_payload: dict[str, object] | None,
) -> tuple[str | None, str | None] | None:
    if metadata_payload is None:
        return None

    wiki = metadata_payload.get(
        "wiki",
    )
    dump_date = metadata_payload.get(
        "dump_date",
    )
    return (
        wiki if isinstance(wiki, str) and wiki else None,
        dump_date if isinstance(dump_date, str) and dump_date else None,
    )


def _build_public_snapshot_id(
    *,
    wiki: str,
    dump_date: str,
) -> str:
    return f"{wiki}-{dump_date}"


def _normalize_public_snapshot_id(
    snapshot_id: str,
) -> str:
    wiki, dump_date = _parse_snapshot_id(
        snapshot_id,
    )
    if wiki is None or dump_date is None:
        return snapshot_id
    return _build_public_snapshot_id(
        wiki=wiki,
        dump_date=dump_date,
    )


def _parse_snapshot_id(
    snapshot_id: str,
) -> tuple[str | None, str | None]:
    match = SNAPSHOT_ID_PATTERN.fullmatch(
        snapshot_id,
    )
    if match is None:
        return None, None
    return match.group(
        "wiki",
    ), match.group(
        "dump_date",
    )
