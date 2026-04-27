from __future__ import annotations

from typing import Any

import pytest

from wikiarena.wikipedia import LiveWikiService


class FakeResponse:
    def __init__(
        self,
        payload: dict[str, Any],
    ):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeAsyncClient:
    def __init__(
        self,
        responses: list[dict[str, Any]],
        recorded_params: list[dict[str, Any]],
    ):
        self.responses = list(
            responses,
        )
        self.recorded_params = recorded_params

    async def __aenter__(
        self,
    ) -> FakeAsyncClient:
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None

    async def get(
        self,
        url: str,
        params: dict[str, Any],
    ) -> FakeResponse:
        del url
        self.recorded_params.append(
            dict(
                params,
            ),
        )
        return FakeResponse(
            self.responses.pop(
                0,
            ),
        )


@pytest.mark.asyncio
async def test_get_matching_links_to_titles_uses_filtered_link_queries() -> None:
    service = LiveWikiService(
        language="en",
    )
    recorded_params: list[dict[str, Any]] = []
    responses = [
        {
            "query": {
                "pages": [
                    {
                        "title": "Philosophy",
                        "links": [
                            {
                                "title": "Science",
                            },
                        ],
                    },
                ],
            },
        },
    ]
    service._create_client = lambda timeout: FakeAsyncClient(  # type: ignore[method-assign]
        responses,
        recorded_params,
    )

    matching_links = await service.get_matching_links_to_titles(
        "Philosophy",
        ["Science", "Mathematics"],
    )

    assert matching_links == ["Science"]
    assert recorded_params == [
        {
            "action": "query",
            "format": "json",
            "prop": "links",
            "titles": "Philosophy",
            "pllimit": "max",
            "pltitles": "Science|Mathematics",
            "redirects": "1",
            "formatversion": "2",
            "plnamespace": "0",
        },
    ]


@pytest.mark.asyncio
async def test_get_matching_links_to_titles_chunks_candidate_titles() -> None:
    service = LiveWikiService(
        language="en",
    )
    recorded_params: list[dict[str, Any]] = []
    candidate_titles = [
        f"Candidate {index}"
        for index in range(
            55,
        )
    ]
    responses = [
        {
            "query": {
                "pages": [
                    {
                        "title": "Source",
                        "links": [
                            {
                                "title": "Candidate 10",
                            },
                        ],
                    },
                ],
            },
        },
        {
            "query": {
                "pages": [
                    {
                        "title": "Source",
                        "links": [
                            {
                                "title": "Candidate 54",
                            },
                        ],
                    },
                ],
            },
        },
    ]
    service._create_client = lambda timeout: FakeAsyncClient(  # type: ignore[method-assign]
        responses,
        recorded_params,
    )

    matching_links = await service.get_matching_links_to_titles(
        "Source",
        candidate_titles,
    )

    assert matching_links == ["Candidate 10", "Candidate 54"]
    assert (
        len(
            recorded_params,
        )
        == 2
    )
    assert (
        len(
            recorded_params[0]["pltitles"].split("|"),
        )
        == 50
    )
    assert (
        len(
            recorded_params[1]["pltitles"].split("|"),
        )
        == 5
    )


@pytest.mark.asyncio
async def test_has_any_link_to_titles_returns_false_for_empty_candidates() -> None:
    service = LiveWikiService(
        language="en",
    )

    assert (
        await service.has_any_link_to_titles(
            "Philosophy",
            [],
        )
        is False
    )
