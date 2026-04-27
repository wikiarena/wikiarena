from __future__ import annotations

from datetime import UTC, datetime

import pytest

from wikiarena.analysis.taskset_audit import audit_taskset_against_live_wikipedia
from wikiarena.protocol import PathSource, SolverShortestPath, TaskSpec


class FakeWikiService:
    def __init__(
        self,
        links_by_page_title: dict[str, list[str]],
        redirects_by_title: dict[str, list[str]] | None = None,
    ):
        self.links_by_page_title = links_by_page_title
        self.redirects_by_title = redirects_by_title or {}

    async def get_matching_links_to_titles(
        self,
        page_title: str,
        candidate_titles: list[str],
        include_all_namespaces: bool = False,
    ) -> list[str]:
        available_links = self.links_by_page_title.get(
            page_title,
            [],
        )
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
        available_links = self.links_by_page_title.get(
            page_title,
            [],
        )
        candidate_title_set = set(
            candidate_titles,
        )
        return any(link_title in candidate_title_set for link_title in available_links)

    async def get_redirect_titles(
        self,
        page_title: str,
    ) -> list[str]:
        return list(
            self.redirects_by_title.get(
                page_title,
                [],
            ),
        )


class FailingWikiService(FakeWikiService):
    async def has_any_link_to_titles(
        self,
        page_title: str,
        candidate_titles: list[str],
        include_all_namespaces: bool = False,
    ) -> bool:
        raise ValueError(
            f"Page does not exist: {page_title}",
        )


@pytest.mark.asyncio
async def test_audit_taskset_against_live_wikipedia_audits_solver_shortest_paths() -> (
    None
):
    tasks = [
        TaskSpec(
            language="en",
            start_page_title="Apple",
            target_page_title="Fruit",
            solver_shortest_path=_solver_shortest_path(
                ["Apple", "Fruit"],
            ),
        ),
        TaskSpec(
            language="en",
            start_page_title="Source",
            target_page_title="Target",
            solver_shortest_path=_solver_shortest_path(
                ["Source", "Target"],
            ),
        ),
        TaskSpec(
            language="en",
            start_page_title="No",
            target_page_title="Path",
        ),
    ]
    wiki_service = FakeWikiService(
        links_by_page_title={
            "Apple": ["Fruit"],
            "Source": ["Redirect Title"],
        },
        redirects_by_title={
            "Target": ["Redirect Title"],
        },
    )

    result = await audit_taskset_against_live_wikipedia(
        tasks,
        wiki_service=wiki_service,
    )

    assert len(result.rows) == 3
    assert result.rows[0].audit_status == "audited"
    assert result.rows[0].all_edges_directly_visible is True
    assert result.rows[0].all_edges_visible_with_redirects is True
    assert result.rows[1].audit_status == "audited"
    assert result.rows[1].all_edges_directly_visible is False
    assert result.rows[1].all_edges_visible_with_redirects is True
    assert result.rows[2].audit_status == "missing_solver_shortest_path"
    assert result.rows[2].strict_audit is None

    summary = result.build_summary()
    assert summary == {
        "total_tasks": 3,
        "audited_tasks": 2,
        "missing_solver_shortest_path": 1,
        "audit_error_count": 0,
        "strict_pass_count": 1,
        "redirect_pass_count": 2,
    }


@pytest.mark.asyncio
async def test_audit_taskset_against_live_wikipedia_records_task_errors() -> None:
    tasks = [
        TaskSpec(
            language="en",
            start_page_title="Missing",
            target_page_title="Target",
            solver_shortest_path=_solver_shortest_path(
                ["Missing", "Target"],
            ),
        ),
    ]

    result = await audit_taskset_against_live_wikipedia(
        tasks,
        wiki_service=FailingWikiService(
            links_by_page_title={},
        ),
    )

    assert len(result.rows) == 1
    assert result.rows[0].audit_status == "audit_error"
    assert result.rows[0].audit_error_type == "ValueError"
    assert result.rows[0].audit_error == "Page does not exist: Missing"
    assert result.build_summary() == {
        "total_tasks": 1,
        "audited_tasks": 0,
        "missing_solver_shortest_path": 0,
        "audit_error_count": 1,
        "strict_pass_count": 0,
        "redirect_pass_count": 0,
    }


def _solver_shortest_path(
    page_titles: list[str],
) -> SolverShortestPath:
    return SolverShortestPath(
        page_titles=page_titles,
        computed_at=datetime(2026, 4, 19, 18, 30, tzinfo=UTC),
        solver_snapshot_id="enwiki-20260401",
        source=PathSource.LOCAL_GRAPH,
    )
