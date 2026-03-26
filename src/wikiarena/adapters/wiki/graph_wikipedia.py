from __future__ import annotations

from typing import Iterator
from typing import Protocol

from wikiarena.core.interfaces import NavigationResolution
from wikiarena.core.interfaces import PageSnapshot
from wikiarena.protocol.enums import LinkPolicy


def _normalize_title_for_comparison(title: str) -> str:
    return title.strip().replace("_", " ").casefold()


def _apply_link_policy(
    links: list[str],
    link_policy: LinkPolicy,
) -> list[str]:
    if link_policy == LinkPolicy.RAW_ORDERED:
        return links

    if link_policy == LinkPolicy.DEDUPE_KEEP_FIRST:
        seen: set[str] = set()
        deduped_links: list[str] = []
        for link in links:
            normalized_link = _normalize_title_for_comparison(
                link,
            )
            if normalized_link in seen:
                continue
            seen.add(
                normalized_link,
            )
            deduped_links.append(
                link,
            )
        return deduped_links

    return links


class GraphWikipediaNavigator:
    def __init__(
        self,
        *,
        graph: "OfflineGraph",
    ):
        self.graph = graph

    async def get_page_snapshot(
        self,
        language: str,
        page_title: str,
        link_policy: LinkPolicy,
    ) -> PageSnapshot:
        page_node_id = self.graph.find_node_id(
            page_title,
        )
        if page_node_id is None:
            raise ValueError(
                f"page does not exist in graph snapshot: {page_title}",
            )

        links = [
            self.graph.title_for_node_id(
                neighbor_node_id,
            )
            for neighbor_node_id in self.graph.iter_outgoing_neighbors(
                page_node_id,
            )
        ]
        return PageSnapshot(
            title=self.graph.title_for_node_id(
                page_node_id,
            ),
            language=language,
            links=_apply_link_policy(
                links=links,
                link_policy=link_policy,
            ),
        )

    async def resolve_navigation(
        self,
        language: str,
        from_page_title: str,
        selected_link_text: str,
    ) -> NavigationResolution:
        del language
        del from_page_title

        resolved_node_id = self.graph.find_node_id(
            selected_link_text,
        )
        if resolved_node_id is None:
            raise ValueError(
                f"page does not exist in graph snapshot: {selected_link_text}",
            )

        return NavigationResolution(
            requested_to_page_title=selected_link_text,
            resolved_to_page_title=self.graph.title_for_node_id(
                resolved_node_id,
            ),
            was_redirect=False,
        )


class OfflineGraph(Protocol):
    def find_node_id(
        self,
        title: str,
    ) -> int | None: ...

    def title_for_node_id(
        self,
        node_id: int,
    ) -> str: ...

    def iter_outgoing_neighbors(
        self,
        node_id: int,
    ) -> Iterator[int]: ...
