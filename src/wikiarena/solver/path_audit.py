from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, Field


class WikipediaAuditPageService(Protocol):
    async def get_matching_links_to_titles(
        self,
        page_title: str,
        candidate_titles: list[str],
        include_all_namespaces: bool = False,
    ) -> list[str]: ...

    async def has_any_link_to_titles(
        self,
        page_title: str,
        candidate_titles: list[str],
        include_all_namespaces: bool = False,
    ) -> bool: ...

    async def get_redirect_titles(
        self,
        page_title: str,
    ) -> list[str]: ...


@dataclass
class PathAuditCache:
    redirect_titles_by_target: dict[str, list[str]] = field(
        default_factory=dict,
    )
    has_any_link_to_titles_by_source_and_candidates: dict[
        tuple[str, tuple[str, ...]], bool
    ] = field(
        default_factory=dict,
    )
    matching_links_by_source_and_candidates: dict[
        tuple[str, tuple[str, ...]], list[str]
    ] = field(
        default_factory=dict,
    )


class PathEdgeAuditResult(BaseModel):
    source_title: str
    target_title: str
    direct_visible: bool
    redirect_visible: bool
    matching_visible_links: list[str] = Field(
        default_factory=list,
    )


class PathAuditResult(BaseModel):
    backend_id: str
    path: list[str] = Field(
        default_factory=list,
    )
    edge_results: list[PathEdgeAuditResult] = Field(
        default_factory=list,
    )

    @property
    def all_edges_directly_visible(self) -> bool:
        return all(edge_result.direct_visible for edge_result in self.edge_results)

    @property
    def all_edges_visible_with_redirects(self) -> bool:
        return all(
            edge_result.direct_visible or edge_result.redirect_visible
            for edge_result in self.edge_results
        )


async def audit_solver_path_against_live_wikipedia(
    *,
    backend_id: str,
    path: list[str],
    wiki_service: WikipediaAuditPageService,
    allow_redirects: bool = False,
    cache: PathAuditCache | None = None,
) -> PathAuditResult:
    audit_cache = cache or PathAuditCache()
    edge_results: list[PathEdgeAuditResult] = []
    for source_title, target_title in zip(path, path[1:]):
        normalized_source_title = _normalize_live_wikipedia_title(
            source_title,
        )
        normalized_target_title = _normalize_live_wikipedia_title(
            target_title,
        )
        direct_visible = await _has_any_link_to_titles(
            wiki_service=wiki_service,
            cache=audit_cache,
            source_title=normalized_source_title,
            candidate_titles=[normalized_target_title],
        )
        matching_visible_links: list[str] = []
        if allow_redirects and not direct_visible:
            target_redirect_titles = await _get_redirect_titles(
                wiki_service=wiki_service,
                cache=audit_cache,
                target_title=normalized_target_title,
            )
            matching_visible_links = await _get_matching_links_to_titles(
                wiki_service=wiki_service,
                cache=audit_cache,
                source_title=normalized_source_title,
                candidate_titles=target_redirect_titles,
            )

        edge_results.append(
            PathEdgeAuditResult(
                source_title=source_title,
                target_title=target_title,
                direct_visible=direct_visible,
                redirect_visible=bool(matching_visible_links),
                matching_visible_links=matching_visible_links,
            ),
        )

    return PathAuditResult(
        backend_id=backend_id,
        path=path,
        edge_results=edge_results,
    )


async def _get_redirect_titles(
    *,
    wiki_service: WikipediaAuditPageService,
    cache: PathAuditCache,
    target_title: str,
) -> list[str]:
    cached_redirect_titles = cache.redirect_titles_by_target.get(
        target_title,
    )
    if cached_redirect_titles is not None:
        return cached_redirect_titles

    redirect_titles = await wiki_service.get_redirect_titles(
        target_title,
    )
    cache.redirect_titles_by_target[target_title] = list(
        redirect_titles,
    )
    return cache.redirect_titles_by_target[target_title]


async def _has_any_link_to_titles(
    *,
    wiki_service: WikipediaAuditPageService,
    cache: PathAuditCache,
    source_title: str,
    candidate_titles: list[str],
) -> bool:
    normalized_candidate_titles = tuple(
        _dedupe_titles_preserving_order(
            candidate_titles,
        ),
    )
    if not normalized_candidate_titles:
        return False

    cache_key = (
        source_title,
        normalized_candidate_titles,
    )
    cached_value = cache.has_any_link_to_titles_by_source_and_candidates.get(
        cache_key,
    )
    if cached_value is not None:
        return cached_value

    has_any_link = await wiki_service.has_any_link_to_titles(
        source_title,
        list(
            normalized_candidate_titles,
        ),
        include_all_namespaces=False,
    )
    cache.has_any_link_to_titles_by_source_and_candidates[cache_key] = has_any_link
    return has_any_link


async def _get_matching_links_to_titles(
    *,
    wiki_service: WikipediaAuditPageService,
    cache: PathAuditCache,
    source_title: str,
    candidate_titles: list[str],
) -> list[str]:
    normalized_candidate_titles = tuple(
        _dedupe_titles_preserving_order(
            candidate_titles,
        ),
    )
    if not normalized_candidate_titles:
        return []

    cache_key = (
        source_title,
        normalized_candidate_titles,
    )
    cached_matches = cache.matching_links_by_source_and_candidates.get(
        cache_key,
    )
    if cached_matches is not None:
        return list(
            cached_matches,
        )

    matching_links = await wiki_service.get_matching_links_to_titles(
        source_title,
        list(
            normalized_candidate_titles,
        ),
        include_all_namespaces=False,
    )
    deduped_matching_links = _dedupe_titles_preserving_order(
        matching_links,
    )
    cache.matching_links_by_source_and_candidates[cache_key] = deduped_matching_links
    return list(
        deduped_matching_links,
    )


def _dedupe_titles_preserving_order(
    candidate_titles: list[str],
) -> list[str]:
    seen_titles: set[str] = set()
    deduped_titles: list[str] = []
    for candidate_title in candidate_titles:
        if candidate_title in seen_titles:
            continue
        seen_titles.add(
            candidate_title,
        )
        deduped_titles.append(
            candidate_title,
        )
    return deduped_titles


def _normalize_live_wikipedia_title(
    title: str,
) -> str:
    return title.replace(
        "\\'",
        "'",
    )
