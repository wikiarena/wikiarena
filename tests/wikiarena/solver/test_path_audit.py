from __future__ import annotations

import pytest

from wikiarena.solver import PathAuditCache, audit_solver_path_against_live_wikipedia


class FakeWikiService:
    def __init__(
        self,
        links_by_page_title: dict[str, list[str]],
        redirects_by_title: dict[str, list[str]] | None = None,
    ):
        self.links_by_page_title = links_by_page_title
        self.redirects_by_title = redirects_by_title or {}
        self.has_any_link_to_titles_call_count = 0
        self.get_matching_links_to_titles_call_count = 0
        self.get_redirect_titles_call_count = 0

    async def get_matching_links_to_titles(
        self,
        page_title: str,
        candidate_titles: list[str],
        include_all_namespaces: bool = False,
    ) -> list[str]:
        self.get_matching_links_to_titles_call_count += 1
        available_links = self.links_by_page_title[page_title]
        candidate_title_set = set(
            candidate_titles,
        )
        return [
            link_title
            for link_title in available_links
            if link_title in candidate_title_set
        ]

    async def has_any_link_to_titles(
        self,
        page_title: str,
        candidate_titles: list[str],
        include_all_namespaces: bool = False,
    ) -> bool:
        self.has_any_link_to_titles_call_count += 1
        available_links = self.links_by_page_title[page_title]
        candidate_title_set = set(
            candidate_titles,
        )
        return any(link_title in candidate_title_set for link_title in available_links)

    async def get_redirect_titles(
        self,
        page_title: str,
    ) -> list[str]:
        self.get_redirect_titles_call_count += 1
        return list(
            self.redirects_by_title.get(
                page_title,
                [],
            ),
        )


@pytest.mark.asyncio
async def test_audit_solver_path_is_strict_by_default() -> None:
    wiki_service = FakeWikiService(
        links_by_page_title={
            "Apple": ["Fruit", "Malus domestica"],
            "Source": ["Redirect Title"],
        },
    )

    direct_audit = await audit_solver_path_against_live_wikipedia(
        backend_id="test",
        path=["Apple", "Fruit"],
        wiki_service=wiki_service,
    )
    strict_redirect_audit = await audit_solver_path_against_live_wikipedia(
        backend_id="test",
        path=["Source", "Target"],
        wiki_service=wiki_service,
    )

    assert direct_audit.all_edges_directly_visible is True
    assert strict_redirect_audit.all_edges_directly_visible is False
    assert strict_redirect_audit.all_edges_visible_with_redirects is False
    assert strict_redirect_audit.edge_results[0].matching_visible_links == []


@pytest.mark.asyncio
async def test_audit_solver_path_can_optionally_follow_redirects() -> None:
    wiki_service = FakeWikiService(
        links_by_page_title={
            "Source": ["Redirect Title"],
        },
        redirects_by_title={
            "Target": ["Redirect Title"],
        },
    )

    redirect_audit = await audit_solver_path_against_live_wikipedia(
        backend_id="test",
        path=["Source", "Target"],
        wiki_service=wiki_service,
        allow_redirects=True,
    )

    assert redirect_audit.all_edges_directly_visible is False
    assert redirect_audit.all_edges_visible_with_redirects is True
    assert redirect_audit.edge_results[0].matching_visible_links == ["Redirect Title"]


@pytest.mark.asyncio
async def test_audit_solver_path_uses_target_redirect_aliases_not_other_pages() -> None:
    wiki_service = FakeWikiService(
        links_by_page_title={
            "Source": ["Intermediate Page", "Redirect Title"],
        },
        redirects_by_title={
            "Target": ["Redirect Title"],
        },
    )

    redirect_audit = await audit_solver_path_against_live_wikipedia(
        backend_id="test",
        path=["Source", "Target"],
        wiki_service=wiki_service,
        allow_redirects=True,
    )

    assert redirect_audit.edge_results[0].matching_visible_links == ["Redirect Title"]


@pytest.mark.asyncio
async def test_audit_solver_path_reuses_cache_across_calls() -> None:
    wiki_service = FakeWikiService(
        links_by_page_title={
            "Source": ["Redirect Title"],
        },
        redirects_by_title={
            "Target": ["Redirect Title"],
        },
    )
    cache = PathAuditCache()

    first_audit = await audit_solver_path_against_live_wikipedia(
        backend_id="test",
        path=["Source", "Target"],
        wiki_service=wiki_service,
        allow_redirects=True,
        cache=cache,
    )
    second_audit = await audit_solver_path_against_live_wikipedia(
        backend_id="test",
        path=["Source", "Target"],
        wiki_service=wiki_service,
        allow_redirects=True,
        cache=cache,
    )

    assert first_audit.all_edges_visible_with_redirects is True
    assert second_audit.all_edges_visible_with_redirects is True
    assert wiki_service.has_any_link_to_titles_call_count == 1
    assert wiki_service.get_matching_links_to_titles_call_count == 1
    assert wiki_service.get_redirect_titles_call_count == 1


@pytest.mark.asyncio
async def test_audit_solver_path_normalizes_sql_escaped_apostrophes() -> None:
    wiki_service = FakeWikiService(
        links_by_page_title={
            "Any Old Arms Won't Do": ["Willie Nelson"],
        },
    )

    audit = await audit_solver_path_against_live_wikipedia(
        backend_id="test",
        path=["Any Old Arms Won\\'t Do", "Willie Nelson"],
        wiki_service=wiki_service,
    )

    assert audit.all_edges_directly_visible is True
    assert wiki_service.has_any_link_to_titles_call_count == 1
