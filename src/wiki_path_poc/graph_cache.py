"""
Graph cache for Wikipedia path finding POC.
Manages in-memory graph storage with target-based invalidation.
"""
from typing import Dict, Set, Optional
from models import WikiPage
import logging

logger = logging.getLogger(__name__)


class GraphCache:
    """
    Manages in-memory graph storage for Wikipedia pages and their links.
    
    Key features:
    - Target-based cache invalidation (clear when target changes)
    - Separate storage for outgoing and incoming links
    - Track fetch status to avoid duplicate API calls
    """
    
    def __init__(self):
        self.pages: Dict[str, WikiPage] = {}
        self.outgoing_graph: Dict[str, Set[str]] = {}
        self.incoming_graph: Dict[str, Set[str]] = {}
        self.current_target: Optional[str] = None
        
    def set_target(self, target: str):
        """
        Set new target page, clear cache if target changed.
        This is key for the "game continuation" optimization.
        """
        if self.current_target != target:
            logger.info(f"Target changed from '{self.current_target}' to '{target}' - clearing cache")
            self.clear()
            self.current_target = target
        else:
            logger.info(f"Target unchanged: '{target}' - keeping cache")
    
    def clear(self):
        """Clear all cached data."""
        self.pages.clear()
        self.outgoing_graph.clear()
        self.incoming_graph.clear()
        self.current_target = None
        logger.debug("Cache cleared")
    
    def add_page_links(self, title: str, outgoing: Optional[Set[str]] = None, 
                      incoming: Optional[Set[str]] = None):
        """
        Add/update links for a page.
        
        Args:
            title: Page title (canonical)
            outgoing: Set of pages this page links to
            incoming: Set of pages that link to this page
        """
        # Create or update WikiPage
        if title not in self.pages:
            self.pages[title] = WikiPage(title=title)
            
        page = self.pages[title]
        
        # Update outgoing links
        if outgoing is not None:
            page.outgoing_links = outgoing.copy()
            self.outgoing_graph[title] = outgoing.copy()
            logger.debug(f"Cached {len(outgoing)} outgoing links for '{title}'")
            
        # Update incoming links  
        if incoming is not None:
            page.incoming_links = incoming.copy()
            self.incoming_graph[title] = incoming.copy()
            logger.debug(f"Cached {len(incoming)} incoming links for '{title}'")
            
        # Update fetch status
        if outgoing is not None or incoming is not None:
            page.fetch_status = "completed"
    
    def get_neighbors(self, title: str, direction: str) -> Set[str]:
        """
        Get neighbors in specified direction.
        
        Args:
            title: Page title
            direction: "forward" (outgoing links) or "backward" (incoming links)
            
        Returns:
            Set of neighbor page titles, empty set if not found
        """
        if direction == "forward":
            return self.outgoing_graph.get(title, set())
        elif direction == "backward":
            return self.incoming_graph.get(title, set())
        else:
            raise ValueError(f"Invalid direction: {direction}. Must be 'forward' or 'backward'")
    
    def is_fetched(self, title: str, direction: str) -> bool:
        """
        Check if links for page in direction are already fetched.
        
        Args:
            title: Page title
            direction: "forward" or "backward"
            
        Returns:
            True if already fetched, False otherwise
        """
        if title not in self.pages:
            return False
            
        page = self.pages[title]
        
        if direction == "forward":
            return page.outgoing_links is not None
        elif direction == "backward":
            return page.incoming_links is not None
        else:
            raise ValueError(f"Invalid direction: {direction}")
    
    def mark_fetching(self, title: str):
        """Mark page as currently being fetched to avoid duplicate requests."""
        if title not in self.pages:
            self.pages[title] = WikiPage(title=title)
        self.pages[title].fetch_status = "fetching"
        logger.debug(f"Marked '{title}' as fetching")
    
    def mark_error(self, title: str, error_msg: str = ""):
        """Mark page as having an error during fetch."""
        if title not in self.pages:
            self.pages[title] = WikiPage(title=title)
        self.pages[title].fetch_status = f"error: {error_msg}"
        logger.warning(f"Marked '{title}' as error: {error_msg}")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get statistics about current cache state."""
        total_pages = len(self.pages)
        pages_with_outgoing = sum(1 for p in self.pages.values() if p.outgoing_links is not None)
        pages_with_incoming = sum(1 for p in self.pages.values() if p.incoming_links is not None)
        total_outgoing_links = sum(len(links) for links in self.outgoing_graph.values())
        total_incoming_links = sum(len(links) for links in self.incoming_graph.values())
        
        return {
            "total_pages": total_pages,
            "pages_with_outgoing": pages_with_outgoing,
            "pages_with_incoming": pages_with_incoming,
            "total_outgoing_links": total_outgoing_links,
            "total_incoming_links": total_incoming_links,
            "current_target": self.current_target
        }
    
    def __repr__(self):
        stats = self.get_cache_stats()
        return (f"GraphCache(pages={stats['total_pages']}, "
                f"outgoing_links={stats['total_outgoing_links']}, "
                f"incoming_links={stats['total_incoming_links']}, "
                f"target='{stats['current_target']}')") 