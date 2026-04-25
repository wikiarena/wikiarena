from __future__ import annotations

from wikiarena.adapters.wiki.live_wikipedia import LiveWikipediaNavigator
from wikiarena.protocol.enums import LinkPolicy
from wikiarena.wikipedia import WikipediaPage


class StubLiveWikiService:
    def __init__(
        self,
        pages_by_title: dict[str, WikipediaPage],
    ):
        self.pages_by_title = pages_by_title

    async def get_page(
        self,
        page_title: str,
        include_all_namespaces: bool = False,
    ) -> WikipediaPage:
        return self.pages_by_title[page_title]


class MissingPageStubLiveWikiService:
    async def get_page(
        self,
        page_title: str,
        include_all_namespaces: bool = False,
    ) -> WikipediaPage:
        raise ValueError(
            f"Page does not exist: {page_title}",
        )


async def test_live_wikipedia_navigator_applies_dedupe_policy() -> None:
    wiki_service = StubLiveWikiService(
        pages_by_title={
            "Apple": WikipediaPage(
                title="Apple",
                url="https://en.wikipedia.org/wiki/Apple",
                links=["Banana", "banana", "Cherry", "Banana"],
                text=None,
            ),
        },
    )
    navigator = LiveWikipediaNavigator(
        wiki_service=wiki_service,
    )

    raw_snapshot = await navigator.get_page_snapshot(
        language="en",
        page_title="Apple",
        link_policy=LinkPolicy.RAW_ORDERED,
    )
    deduped_snapshot = await navigator.get_page_snapshot(
        language="en",
        page_title="Apple",
        link_policy=LinkPolicy.DEDUPE_KEEP_FIRST,
    )

    assert raw_snapshot.links == ["Banana", "banana", "Cherry", "Banana"]
    assert deduped_snapshot.links == ["Banana", "Cherry"]


async def test_live_wikipedia_navigator_marks_redirect_resolution() -> None:
    wiki_service = StubLiveWikiService(
        pages_by_title={
            "Old Title": WikipediaPage(
                title="New Title",
                url="https://en.wikipedia.org/wiki/New_Title",
                links=[],
                text=None,
            ),
        },
    )
    navigator = LiveWikipediaNavigator(
        wiki_service=wiki_service,
    )

    resolution = await navigator.resolve_navigation(
        language="en",
        from_page_title="Start",
        selected_link_text="Old Title",
    )

    assert resolution.requested_to_page_title == "Old Title"
    assert resolution.resolved_to_page_title == "New Title"
    assert resolution.was_redirect is True


async def test_live_wikipedia_navigator_returns_missing_target_resolution() -> None:
    navigator = LiveWikipediaNavigator(
        wiki_service=MissingPageStubLiveWikiService(),
    )

    resolution = await navigator.resolve_navigation(
        language="en",
        from_page_title="List of moths of Canada",
        selected_link_text="List of moths of Canada (Micromoths)",
    )

    assert resolution.requested_to_page_title == "List of moths of Canada (Micromoths)"
    assert resolution.resolved_to_page_title is None
    assert resolution.was_redirect is False
