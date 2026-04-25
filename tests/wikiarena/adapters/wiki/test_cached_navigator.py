from __future__ import annotations

import asyncio

import pytest

from wikiarena.adapters.wiki import CachedWikiNavigator
from wikiarena.core import NavigationResolution
from wikiarena.core import PageSnapshot
from wikiarena.protocol import LinkPolicy


class StubWikiNavigator:
    def __init__(
        self,
    ):
        self.page_call_count = 0
        self.resolve_call_count = 0

    async def get_page_snapshot(
        self,
        language,
        page_title,
        link_policy,
    ) -> PageSnapshot:
        self.page_call_count += 1
        await asyncio.sleep(
            0.05,
        )
        return PageSnapshot(
            title=page_title,
            language=language,
            links=["Banana"],
        )

    async def resolve_navigation(
        self,
        language,
        from_page_title,
        selected_link_text,
    ) -> NavigationResolution:
        self.resolve_call_count += 1
        await asyncio.sleep(
            0.05,
        )
        return NavigationResolution(
            requested_to_page_title=selected_link_text,
            resolved_to_page_title=selected_link_text,
            was_redirect=False,
        )


@pytest.mark.asyncio
async def test_cached_navigator_dedupes_concurrent_page_fetches() -> None:
    inner = StubWikiNavigator()
    cached_navigator = CachedWikiNavigator(
        inner,
    )

    results = await asyncio.gather(
        *[
            cached_navigator.get_page_snapshot(
                language="en",
                page_title="Apple",
                link_policy=LinkPolicy.RAW_ORDERED,
            )
            for _ in range(5)
        ],
    )

    assert inner.page_call_count == 1
    assert len(results) == 5
    assert all(result.title == "Apple" for result in results)


@pytest.mark.asyncio
async def test_cached_navigator_dedupes_concurrent_navigation_resolution() -> None:
    inner = StubWikiNavigator()
    cached_navigator = CachedWikiNavigator(
        inner,
    )

    results = await asyncio.gather(
        *[
            cached_navigator.resolve_navigation(
                language="en",
                from_page_title="Apple",
                selected_link_text="Banana",
            )
            for _ in range(4)
        ],
    )

    assert inner.resolve_call_count == 1
    assert len(results) == 4
    assert all(result.resolved_to_page_title == "Banana" for result in results)
