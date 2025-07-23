import logging
import httpx
import urllib.parse
from typing import List

from wiki_arena.types import Page

class LiveWikiService:
    """
    Service for interacting directly with the live Wikipedia API.
    All methods are asynchronous.
    """
    def __init__(self, language: str = "en"):
        self.language = language
        self.base_url = f"https://{language}.wikipedia.org/w/api.php"
        self.logger = logging.getLogger(__name__)

    async def get_random_pages(self, count: int = 20) -> List[str]:
        """Get random pages."""
        params = {
            "action": "query", "format": "json", "list": "random",
            "rnnamespace": "0", "rnfilterredir": "nonredirects", "rnlimit": str(count)
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
            data = response.json()
            if "query" not in data or "random" not in data["query"]:
                raise ConnectionError("Unexpected API response format for get_random_pages")
            pages = [page["title"] for page in data["query"]["random"]]
            self.logger.debug(f"Fetched {len(pages)} random pages")
            return pages
        except httpx.RequestError as e:
            self.logger.error(f"Failed to fetch random pages: {e}")
            raise ConnectionError(f"Wikipedia API request failed: {e}")

    async def has_outgoing_links(self, page_title: str) -> bool:
        """Check if page has any outgoing links."""
        params = {
            "action": "query", "format": "json", "prop": "links",
            "titles": page_title, "pllimit": "1", "plnamespace": "0"
        }
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
            data = response.json()
            if "query" in data and "pages" in data["query"]:
                page_data = next(iter(data["query"]["pages"].values()))
                has_links = "links" in page_data and len(page_data["links"]) > 0
                self.logger.debug(f"Page '{page_title}' has outgoing links: {has_links}")
                return has_links
            return False
        except httpx.RequestError as e:
            self.logger.debug(f"Error checking outgoing links for '{page_title}': {e}")
            return False

    async def has_incoming_links(self, page_title: str) -> bool:
        """Check if page has any incoming links."""
        params = {
            "action": "query", "format": "json", "list": "backlinks",
            "bltitle": page_title, "blnamespace": "0", "bllimit": "1"
        }
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
            data = response.json()
            if "query" in data and "backlinks" in data["query"]:
                has_backlinks = len(data["query"]["backlinks"]) > 0
                self.logger.debug(f"Page '{page_title}' has incoming links: {has_backlinks}")
                return has_backlinks
            return False
        except httpx.RequestError as e:
            self.logger.debug(f"Error checking incoming links for '{page_title}': {e}")
            return False

    async def get_page(self, page_title: str, include_all_namespaces: bool = False) -> Page:
        """
        Fetch a full Wikipedia page, including all its links using pagination.
        """
        all_links = []
        plcontinue = None
        page_info = {}
        
        while True:
            params = {
                "action": "query", "format": "json", "prop": "info|links",
                "titles": page_title, "pllimit": "500", "inprop": "url",
                "redirects": "1", "formatversion": "2"
            }
            if not include_all_namespaces:
                params["plnamespace"] = "0"
            if plcontinue:
                params["plcontinue"] = plcontinue
            
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(self.base_url, params=params)
                    response.raise_for_status()
                data = response.json()
            except httpx.RequestError as e:
                self.logger.error(f"Failed to fetch page '{page_title}': {e}")
                raise ConnectionError(f"Wikipedia API request failed for '{page_title}': {e}")

            if "error" in data:
                raise ValueError(f"Wikipedia API error: {data['error']['info']}")
            pages = data.get("query", {}).get("pages", [])
            if not pages: raise ValueError(f"Page not found: {page_title}")
            page = pages[0]
            if "missing" in page: raise ValueError(f"Page does not exist: {page_title}")
            
            if not page_info:
                page_info = {
                    "title": page["title"],
                    "url": page.get("fullurl", f"https://en.wikipedia.org/wiki/{urllib.parse.quote(page['title'])}")
                }
            
            links_batch = page.get("links", [])
            all_links.extend(link["title"] for link in links_batch)
            
            continue_data = data.get("continue", {})
            if "plcontinue" in continue_data:
                plcontinue = continue_data["plcontinue"]
            else:
                break
        
        return Page(
            title=page_info["title"],
            url=page_info["url"],
            links=all_links,
            text=None  # This method doesn't fetch page text content
        )
