from __future__ import annotations

from wikiarena.adapters.wiki.graph_wikipedia import GraphWikipediaNavigator
from wikiarena.protocol.enums import LinkPolicy


class StubOfflineGraph:
    def __init__(
        self,
    ):
        self.node_ids_by_title = {
            "Apple": 0,
            "Banana": 1,
            "Cherry": 2,
        }
        self.titles_by_node_id = {
            0: "Apple",
            1: "Banana",
            2: "Cherry",
        }
        self.outgoing_neighbors_by_node_id = {
            0: (1, 2),
            1: (),
            2: (),
        }

    def find_node_id(
        self,
        title: str,
    ) -> int | None:
        return self.node_ids_by_title.get(
            title,
        )

    def title_for_node_id(
        self,
        node_id: int,
    ) -> str:
        return self.titles_by_node_id[node_id]

    def iter_outgoing_neighbors(
        self,
        node_id: int,
    ):
        return iter(
            self.outgoing_neighbors_by_node_id[node_id],
        )


async def test_graph_wikipedia_navigator_returns_graph_links() -> None:
    navigator = GraphWikipediaNavigator(
        graph=StubOfflineGraph(),
    )

    snapshot = await navigator.get_page_snapshot(
        language="en",
        page_title="Apple",
        link_policy=LinkPolicy.RAW_ORDERED,
    )

    assert snapshot.title == "Apple"
    assert snapshot.links == ["Banana", "Cherry"]


async def test_graph_wikipedia_navigator_resolves_without_redirects() -> None:
    navigator = GraphWikipediaNavigator(
        graph=StubOfflineGraph(),
    )

    resolution = await navigator.resolve_navigation(
        language="en",
        from_page_title="Apple",
        selected_link_text="Banana",
    )

    assert resolution.requested_to_page_title == "Banana"
    assert resolution.resolved_to_page_title == "Banana"
    assert resolution.was_redirect is False
