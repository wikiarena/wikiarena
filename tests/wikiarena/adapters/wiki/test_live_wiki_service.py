from wikiarena.wikipedia.live_service import LiveWikiService


def test_live_wiki_service_sets_required_user_agent_header() -> None:
    service = LiveWikiService(
        language="en",
    )

    client = service._create_client(
        timeout=5.0,
    )
    try:
        assert client.headers["User-Agent"].startswith(
            "WikiArena/0.1",
        )
    finally:
        import asyncio

        asyncio.run(
            client.aclose(),
        )
