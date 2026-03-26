from __future__ import annotations

from typing import Protocol

from wikiarena.core.interfaces import NavigationResolution
from wikiarena.core.interfaces import PageSnapshot
from wikiarena.protocol.enums import LinkPolicy
from wikiarena.wikipedia import WikipediaPage


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


class LiveWikipediaNavigator:
    def __init__(
        self,
        wiki_service: "WikipediaPageService",
    ):
        self.wiki_service = wiki_service

    async def get_page_snapshot(
        self,
        language: str,
        page_title: str,
        link_policy: LinkPolicy,
    ) -> PageSnapshot:
        page = await self.wiki_service.get_page(
            page_title,
            include_all_namespaces=False,
        )
        links = _apply_link_policy(
            links=list(page.links),
            link_policy=link_policy,
        )
        return PageSnapshot(
            title=page.title,
            language=language,
            links=links,
        )

    async def resolve_navigation(
        self,
        language: str,
        from_page_title: str,
        selected_link_text: str,
    ) -> NavigationResolution:
        page = await self.wiki_service.get_page(
            selected_link_text,
            include_all_namespaces=False,
        )
        was_redirect = _normalize_title_for_comparison(
            page.title,
        ) != _normalize_title_for_comparison(
            selected_link_text,
        )
        return NavigationResolution(
            requested_to_page_title=selected_link_text,
            resolved_to_page_title=page.title,
            was_redirect=was_redirect,
        )


class WikipediaPageService(Protocol):
    async def get_page(
        self,
        page_title: str,
        include_all_namespaces: bool = False,
    ) -> WikipediaPage: ...
