"""
Wikipedia Page Selector

Efficiently selects random Wikipedia page pairs for games with minimal API calls.
Uses an algorithm that needs minimum 3 API calls to guarantee a valid page pair.
"""

import asyncio
import logging
import random
import requests
from typing import Optional, List, Set
from dataclasses import dataclass


@dataclass
class PagePair:
    """Represents a pair of Wikipedia pages for a game."""
    start_page: str
    target_page: str
    
    def __post_init__(self):
        """Validate that start and target pages are different."""
        if self.start_page == self.target_page:
            raise ValueError("Start page and target page must be different")


@dataclass
class LinkValidationConfig:
    """Configuration for link validation options."""
    require_outgoing_links: bool = True  # Enabled by default
    require_incoming_links: bool = True  # Enabled by default
    min_outgoing_links: int = 1
    min_incoming_links: int = 1


class WikipediaPageSelector:
    """
    Efficient Wikipedia page selector.
    
    Algorithm:
    1. Get 20 random pages (1 API call)
    2. Find first valid start page (1 API calls)
    3. Find first valid target page from remaining (1 API calls)
    
    Total: 1-3 API calls guaranteed, even with validation enabled.
    """
    
    def __init__(self, 
                 language: str = "en",
                 max_retries: int = 3,
                 excluded_prefixes: Optional[Set[str]] = None,
                 link_validation: Optional[LinkValidationConfig] = None):
        self.language = language
        self.max_retries = max_retries
        self.base_url = f"https://{language}.wikipedia.org/w/api.php"
        self.link_validation = link_validation or LinkValidationConfig()
        
        # Default excluded prefixes for special pages
        if excluded_prefixes is None:
            self.excluded_prefixes = {
                "Tag:", "Category:", "File:", "Template:", "Help:",
                "Wikipedia:", "User:", "User talk:", "Template talk:",
                "Category talk:", "Portal:", "Project:", "MediaWiki:",
                "Module:", "Draft:",
            }
        else:
            self.excluded_prefixes = excluded_prefixes
            
        self.logger = logging.getLogger(__name__)
    
    def _is_valid_page_title(self, title: str) -> bool:
        """Check if page title is valid (not a special page)."""
        if not title or not title.strip():
            return False
        return not any(title.startswith(prefix) for prefix in self.excluded_prefixes)
    
    def get_random_pages(self, count: int = 20) -> List[str]:
        """Get random pages. (1 API call)"""
        params = {
            "action": "query",
            "format": "json",
            "list": "random",
            "rnnamespace": "0",  # Main namespace only
            "rnfilterredir": "nonredirects",  # No redirects
            "rnlimit": str(count)
        }
        
        try:
            response = requests.get(self.base_url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            if "query" not in data or "random" not in data["query"]:
                raise Exception("Unexpected API response format")
                
            pages = [page["title"] for page in data["query"]["random"]]
            self.logger.debug(f"Fetched {len(pages)} random pages")
            return pages
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch random pages: {e}")
            raise Exception(f"Wikipedia API request failed: {e}")
    
    def _has_outgoing_links(self, page_title: str) -> bool:
        """Check if page has any outgoing links. (1 API call)"""
        try:
            params = {
                "action": "query",
                "format": "json",
                "prop": "links",
                "titles": page_title,
                "pllimit": "1",  # Just check if ANY exist
                "plnamespace": "0"  # Main namespace only
            }
            
            response = requests.get(self.base_url, params=params, timeout=3)
            response.raise_for_status()
            data = response.json()
            
            if "query" in data and "pages" in data["query"]:
                page_data = next(iter(data["query"]["pages"].values()))
                has_links = "links" in page_data and len(page_data["links"]) > 0
                self.logger.debug(f"Page '{page_title}' has outgoing links: {has_links}")
                return has_links
            
            return False
            
        except Exception as e:
            self.logger.debug(f"Error checking outgoing links for '{page_title}': {e}")
            return False
    
    def _has_incoming_links(self, page_title: str) -> bool:
        """Check if page has any incoming links. (1 API call)"""
        try:
            params = {
                "action": "query",
                "format": "json",
                "list": "backlinks",
                "bltitle": page_title,
                "blnamespace": "0",  # Main namespace only
                "bllimit": "1"  # Just check if ANY exist
            }
            
            response = requests.get(self.base_url, params=params, timeout=3)
            response.raise_for_status()
            data = response.json()
            
            if "query" in data and "backlinks" in data["query"]:
                has_backlinks = len(data["query"]["backlinks"]) > 0
                self.logger.debug(f"Page '{page_title}' has incoming links: {has_backlinks}")
                return has_backlinks
            
            return False
            
        except Exception as e:
            self.logger.debug(f"Error checking incoming links for '{page_title}': {e}")
            return False
    
    def _find_valid_start_page(self, candidates: List[str]) -> Optional[str]:
        """
        Find first valid start page from candidates.
        
        Makes: 1 API calls total (only if validation required)
        """
        if not self.link_validation.require_outgoing_links:
            # No validation needed - return first candidate
            if candidates:
                self.logger.debug(f"No start validation needed - using '{candidates[0]}'")
                return candidates[0]
            return None
        
        # Need to validate outgoing links - find first valid
        for page in candidates:
            if self._has_outgoing_links(page):
                self.logger.debug(f"Found valid start page: '{page}'")
                return page
        
        self.logger.debug("No valid start page found")
        return None
    
    def _find_valid_target_page(self, candidates: List[str], exclude_page: str) -> Optional[str]:
        """
        Find first valid target page from candidates (excluding the start page).
        
        Makes: 1 API calls total (only if validation required)
        """
        # Filter out the start page
        available_candidates = [page for page in candidates if page != exclude_page]
        
        if not self.link_validation.require_incoming_links:
            # No validation needed - return first available candidate
            if available_candidates:
                self.logger.debug(f"No target validation needed - using '{available_candidates[0]}'")
                return available_candidates[0]
            return None
        
        # Need to validate incoming links - find first valid
        for page in available_candidates:
            if self._has_incoming_links(page):
                self.logger.debug(f"Found valid target page: '{page}'")
                return page
        
        self.logger.debug("No valid target page found")
        return None
    
    def select_page_pair(self) -> Optional[PagePair]:
        """
        Select a random page pair with efficient validation.
        
        minimum 3 API calls:
        1. Get 20 random pages (1 API call)
        2. Find first valid start page (1 API calls)
        3. Find first valid target page from remaining (1 API calls)
        """
        self.logger.info("Selecting Wikipedia page pair...")
        
        for attempt in range(self.max_retries):
            try:
                # Step 1: Get random pages (1 API call)
                random_pages = self.get_random_pages(count=20)
                
                # Filter valid titles (no API calls)
                valid_pages = [page for page in random_pages if self._is_valid_page_title(page)]
                
                if len(valid_pages) < 2:
                    self.logger.debug(f"Not enough valid pages ({len(valid_pages)}) in attempt {attempt + 1}")
                    continue
                
                # Step 2: Find first valid start page (0-1 API calls)
                start_page = self._find_valid_start_page(valid_pages)
                if not start_page:
                    self.logger.debug(f"No valid start page found in attempt {attempt + 1}")
                    continue
                
                # Step 3: Find first valid target page from remaining (0-1 API calls)
                target_page = self._find_valid_target_page(valid_pages, exclude_page=start_page)
                if not target_page:
                    self.logger.debug(f"No valid target page found in attempt {attempt + 1}")
                    continue
                
                # Success! Create page pair
                page_pair = PagePair(start_page=start_page, target_page=target_page)
                self.logger.info(f"Selected page pair: '{start_page}' -> '{target_page}'")
                return page_pair
                
            except Exception as e:
                self.logger.warning(f"Error in attempt {attempt + 1}: {e}")
        
        self.logger.error("Failed to select valid page pair after all attempts")
        return None
    
    async def select_page_pair_async(self) -> Optional[PagePair]:
        """Async version of page pair selection."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.select_page_pair)


# Convenience functions for backward compatibility
async def get_random_page_pair_async(language: str = "en",
                                   max_retries: int = 3,
                                   excluded_prefixes: Optional[Set[str]] = None,
                                   link_validation: Optional[LinkValidationConfig] = None) -> Optional[PagePair]:
    """Get a random Wikipedia page pair with efficient validation."""
    selector = WikipediaPageSelector(
        language=language,
        max_retries=max_retries,
        excluded_prefixes=excluded_prefixes,
        link_validation=link_validation
    )
    return await selector.select_page_pair_async()


def get_random_page_pair(language: str = "en",
                        max_retries: int = 3,
                        excluded_prefixes: Optional[Set[str]] = None,
                        link_validation: Optional[LinkValidationConfig] = None) -> Optional[PagePair]:
    """Synchronous version of page pair selection."""
    selector = WikipediaPageSelector(
        language=language,
        max_retries=max_retries,
        excluded_prefixes=excluded_prefixes,
        link_validation=link_validation
    )
    return selector.select_page_pair() 