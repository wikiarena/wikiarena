"""
Wikipedia Task Selector

Efficiently selects random Wikipedia tasks for games.
"""

import asyncio
import logging
from typing import Optional, List, Set

from wiki_arena.types import Task
from wiki_arena.wikipedia.live_service import LiveWikiService

class WikipediaTaskSelector:
    """
    Efficient Wikipedia task selector that relies on a LiveWikiService.
    
    Algorithm:
    1. Get a batch of random pages from the service.
    2. Find a valid start page from the batch (must have outgoing links).
    3. Find a valid target page from the remaining candidates (must have incoming links).
    
    This process minimizes direct API calls by using the dedicated service.
    """
    
    def __init__(
            self, 
            live_wiki_service: LiveWikiService,
            max_retries: int = 3,
            excluded_prefixes: Optional[Set[str]] = None
        ):
        self.service = live_wiki_service
        self.max_retries = max_retries
        
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
    
    async def _find_valid_start_page(self, candidates: List[str]) -> Optional[str]:
        """Find first valid start page from candidates by checking for outgoing links."""
        for page in candidates:
            if await self.service.has_outgoing_links(page):
                self.logger.debug(f"Found valid start page: '{page}'")
                return page
        
        self.logger.debug("No valid start page found in candidate batch.")
        return None
    
    async def _find_valid_target_page(self, candidates: List[str], exclude_page: str) -> Optional[str]:
        """Find first valid target page from candidates by checking for incoming links."""
        available_candidates = [p for p in candidates if p != exclude_page]
        for page in available_candidates:
            if await self.service.has_incoming_links(page):
                self.logger.debug(f"Found valid target page: '{page}'")
                return page
        
        self.logger.debug("No valid target page found in candidate batch.")
        return None
    
    async def select_task_async(self) -> Optional[Task]:
        """
        Select a random task with efficient validation via the LiveWikiService.
        """
        self.logger.info("Selecting Wikipedia task...")
        
        for attempt in range(self.max_retries):
            try:
                # Step 1: Get random pages from the service
                random_pages = await self.service.get_random_pages(count=20)
                
                # Filter valid titles locally
                valid_pages = [page for page in random_pages if self._is_valid_page_title(page)]
                
                if len(valid_pages) < 2:
                    self.logger.debug(f"Not enough valid pages ({len(valid_pages)}) in attempt {attempt + 1}")
                    continue
                
                # Step 2: Find a valid start page
                start_page = await self._find_valid_start_page(valid_pages)
                if not start_page:
                    self.logger.debug(f"No valid start page found in attempt {attempt + 1}")
                    continue
                
                # Step 3: Find a valid target page from the remaining candidates
                target_page = await self._find_valid_target_page(valid_pages, exclude_page=start_page)
                if not target_page:
                    self.logger.debug(f"No valid target page found in attempt {attempt + 1}")
                    continue
                
                # Success! Create and return a Task object
                task = Task(start_page_title=start_page, target_page_title=target_page)
                self.logger.info(f"Selected task: '{start_page}' -> '{target_page}'")
                return task
                
            except Exception as e:
                self.logger.warning(f"Error in attempt {attempt + 1} to select task: {e}")
        
        self.logger.error("Failed to select valid task after all attempts")
        return None

async def get_random_task_async(
        language: str = "en",
        max_retries: int = 3,
        excluded_prefixes: Optional[Set[str]] = None
    ) -> Optional[Task]:
    """Get a random Wikipedia task with efficient validation."""
    service = LiveWikiService(language=language)
    selector = WikipediaTaskSelector(
        live_wiki_service=service,
        max_retries=max_retries,
        excluded_prefixes=excluded_prefixes
    )
    return await selector.select_task_async()

def get_random_task(
        language: str = "en",
        max_retries: int = 3,
        excluded_prefixes: Optional[Set[str]] = None
    ) -> Optional[Task]:
    """Synchronous version of task selection. Runs the async version in a new event loop."""
    return asyncio.run(get_random_task_async(language, max_retries, excluded_prefixes)) 