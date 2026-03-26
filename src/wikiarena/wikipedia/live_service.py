from __future__ import annotations

import logging
import urllib.parse

import httpx
from pydantic import BaseModel, Field


class WikipediaPage(BaseModel):
    title: str
    url: str
    links: list[str] = Field(
        default_factory=list,
    )
    text: str | None = None


class LiveWikiService:
    def __init__(
        self,
        language: str = "en",
        user_agent: str | None = None,
    ):
        self.language = language
        self.base_url = f"https://{language}.wikipedia.org/w/api.php"
        self.logger = logging.getLogger(__name__)
        self.user_agent = user_agent or (
            "WikiArena/0.1 "
            "(https://github.com/wikiarena/wikiarena; "
            "hunterwpaulson@gmail.com)"
        )

    def _create_client(
        self,
        timeout: float,
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=timeout,
            headers={
                "User-Agent": self.user_agent,
            },
        )

    async def get_random_pages(
        self,
        count: int = 20,
    ) -> list[str]:
        params = {
            "action": "query",
            "format": "json",
            "list": "random",
            "rnnamespace": "0",
            "rnfilterredir": "nonredirects",
            "rnlimit": str(count),
        }
        try:
            async with self._create_client(timeout=5.0) as client:
                response = await client.get(
                    self.base_url,
                    params=params,
                )
                response.raise_for_status()
        except httpx.RequestError as error:
            self.logger.error(
                "Failed to fetch random pages: %s",
                error,
            )
            raise ConnectionError(
                f"Wikipedia API request failed: {error}",
            ) from error

        data = response.json()
        random_pages = data.get(
            "query",
            {},
        ).get(
            "random",
            [],
        )
        if not random_pages:
            raise ConnectionError(
                "Unexpected API response format for get_random_pages",
            )
        return [page["title"] for page in random_pages]

    async def has_outgoing_links(
        self,
        page_title: str,
    ) -> bool:
        params = {
            "action": "query",
            "format": "json",
            "prop": "links",
            "titles": page_title,
            "pllimit": "1",
            "plnamespace": "0",
            "formatversion": "2",
        }
        try:
            async with self._create_client(timeout=3.0) as client:
                response = await client.get(
                    self.base_url,
                    params=params,
                )
                response.raise_for_status()
        except httpx.RequestError:
            return False

        data = response.json()
        pages = data.get(
            "query",
            {},
        ).get(
            "pages",
            [],
        )
        if not pages:
            return False
        return bool(
            pages[0].get("links", []),
        )

    async def has_incoming_links(
        self,
        page_title: str,
    ) -> bool:
        params = {
            "action": "query",
            "format": "json",
            "list": "backlinks",
            "bltitle": page_title,
            "blnamespace": "0",
            "bllimit": "1",
            "formatversion": "2",
        }
        try:
            async with self._create_client(timeout=3.0) as client:
                response = await client.get(
                    self.base_url,
                    params=params,
                )
                response.raise_for_status()
        except httpx.RequestError:
            return False

        data = response.json()
        backlinks = data.get(
            "query",
            {},
        ).get(
            "backlinks",
            [],
        )
        return bool(
            backlinks,
        )

    async def get_redirect_titles(
        self,
        page_title: str,
    ) -> list[str]:
        all_redirect_titles: list[str] = []
        rdcontinue: str | None = None

        while True:
            params = {
                "action": "query",
                "format": "json",
                "prop": "redirects",
                "titles": page_title,
                "rdlimit": "500",
                "rdnamespace": "0",
                "redirects": "1",
                "formatversion": "2",
            }
            if rdcontinue is not None:
                params["rdcontinue"] = rdcontinue

            try:
                async with self._create_client(timeout=10.0) as client:
                    response = await client.get(
                        self.base_url,
                        params=params,
                    )
                    response.raise_for_status()
            except httpx.RequestError as error:
                self.logger.error(
                    "Failed to fetch redirects for '%s': %s",
                    page_title,
                    error,
                )
                raise ConnectionError(
                    f"Wikipedia API request failed for redirects of '{page_title}': {error}",
                ) from error

            data = response.json()
            if "error" in data:
                raise ValueError(
                    f"Wikipedia API error: {data['error']['info']}",
                )

            pages = data.get(
                "query",
                {},
            ).get(
                "pages",
                [],
            )
            if not pages:
                raise ValueError(
                    f"Page not found: {page_title}",
                )

            page_data = pages[0]
            if page_data.get("missing"):
                raise ValueError(
                    f"Page does not exist: {page_title}",
                )

            all_redirect_titles.extend(
                redirect["title"]
                for redirect in page_data.get(
                    "redirects",
                    [],
                )
            )

            rdcontinue = data.get(
                "continue",
                {},
            ).get(
                "rdcontinue",
            )
            if rdcontinue is None:
                break

        return all_redirect_titles

    async def get_matching_links_to_titles(
        self,
        page_title: str,
        candidate_titles: list[str],
        include_all_namespaces: bool = False,
    ) -> list[str]:
        normalized_candidate_titles = _dedupe_titles_preserving_order(
            candidate_titles,
        )
        if not normalized_candidate_titles:
            return []

        matching_links: list[str] = []
        try:
            async with self._create_client(timeout=10.0) as client:
                for candidate_title_chunk in _chunk_titles(
                    normalized_candidate_titles,
                    chunk_size=50,
                ):
                    params = {
                        "action": "query",
                        "format": "json",
                        "prop": "links",
                        "titles": page_title,
                        "pllimit": "max",
                        "pltitles": "|".join(candidate_title_chunk),
                        "redirects": "1",
                        "formatversion": "2",
                    }
                    if not include_all_namespaces:
                        params["plnamespace"] = "0"

                    response = await client.get(
                        self.base_url,
                        params=params,
                    )
                    response.raise_for_status()

                    data = response.json()
                    if "error" in data:
                        raise ValueError(
                            f"Wikipedia API error: {data['error']['info']}",
                        )

                    pages = data.get(
                        "query",
                        {},
                    ).get(
                        "pages",
                        [],
                    )
                    if not pages:
                        raise ValueError(
                            f"Page not found: {page_title}",
                        )

                    page_data = pages[0]
                    if page_data.get("missing"):
                        raise ValueError(
                            f"Page does not exist: {page_title}",
                        )

                    matching_links.extend(
                        link["title"]
                        for link in page_data.get(
                            "links",
                            [],
                        )
                    )
        except httpx.RequestError as error:
            self.logger.error(
                "Failed to fetch matching links for '%s': %s",
                page_title,
                error,
            )
            raise ConnectionError(
                f"Wikipedia API request failed for matching links of '{page_title}': {error}",
            ) from error

        return _dedupe_titles_preserving_order(
            matching_links,
        )

    async def has_any_link_to_titles(
        self,
        page_title: str,
        candidate_titles: list[str],
        include_all_namespaces: bool = False,
    ) -> bool:
        matching_links = await self.get_matching_links_to_titles(
            page_title,
            candidate_titles,
            include_all_namespaces=include_all_namespaces,
        )
        return bool(
            matching_links,
        )

    async def get_page(
        self,
        page_title: str,
        include_all_namespaces: bool = False,
    ) -> WikipediaPage:
        all_links: list[str] = []
        plcontinue: str | None = None
        resolved_title: str | None = None
        resolved_url: str | None = None

        while True:
            params = {
                "action": "query",
                "format": "json",
                "prop": "info|links",
                "titles": page_title,
                "pllimit": "500",
                "inprop": "url",
                "redirects": "1",
                "formatversion": "2",
            }
            if not include_all_namespaces:
                params["plnamespace"] = "0"
            if plcontinue is not None:
                params["plcontinue"] = plcontinue

            try:
                async with self._create_client(timeout=10.0) as client:
                    response = await client.get(
                        self.base_url,
                        params=params,
                    )
                    response.raise_for_status()
            except httpx.RequestError as error:
                self.logger.error(
                    "Failed to fetch page '%s': %s",
                    page_title,
                    error,
                )
                raise ConnectionError(
                    f"Wikipedia API request failed for '{page_title}': {error}",
                ) from error

            data = response.json()
            if "error" in data:
                raise ValueError(
                    f"Wikipedia API error: {data['error']['info']}",
                )

            pages = data.get(
                "query",
                {},
            ).get(
                "pages",
                [],
            )
            if not pages:
                raise ValueError(
                    f"Page not found: {page_title}",
                )

            page_data = pages[0]
            if page_data.get("missing"):
                raise ValueError(
                    f"Page does not exist: {page_title}",
                )

            if resolved_title is None:
                resolved_title = page_data["title"]
                resolved_url = page_data.get(
                    "fullurl",
                    f"https://{self.language}.wikipedia.org/wiki/{urllib.parse.quote(page_data['title'])}",
                )

            all_links.extend(
                link["title"]
                for link in page_data.get(
                    "links",
                    [],
                )
            )

            plcontinue = data.get(
                "continue",
                {},
            ).get(
                "plcontinue",
            )
            if plcontinue is None:
                break

        if resolved_title is None or resolved_url is None:
            raise ValueError(
                f"Page resolution failed for: {page_title}",
            )

        return WikipediaPage(
            title=resolved_title,
            url=resolved_url,
            links=all_links,
            text=None,
        )


def _chunk_titles(
    titles: list[str],
    *,
    chunk_size: int,
) -> list[list[str]]:
    return [
        titles[index : index + chunk_size]
        for index in range(
            0,
            len(titles),
            chunk_size,
        )
    ]


def _dedupe_titles_preserving_order(
    titles: list[str],
) -> list[str]:
    seen_titles: set[str] = set()
    deduped_titles: list[str] = []
    for title in titles:
        if title in seen_titles:
            continue
        seen_titles.add(
            title,
        )
        deduped_titles.append(
            title,
        )
    return deduped_titles
