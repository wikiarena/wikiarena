"""
Wikipedia path finder using bidirectional BFS.
Core component that orchestrates the search algorithm.
"""
import asyncio
from collections import deque
from typing import List, Optional, Set, Dict
import time
import logging

from models import SearchState
from wikipedia_client import WikipediaClient
from graph_cache import GraphCache

logger = logging.getLogger(__name__)


class WikipediaPathFinder:
    """
    Finds shortest path between Wikipedia pages using bidirectional BFS.
    
    Key optimizations:
    - Bidirectional search to minimize search space
    - Level-wise expansion with batched API calls
    - Cache reuse for game continuation scenarios
    - Serial API requests to respect Wikipedia's guidelines
    """
    
    def __init__(self):
        self.client = WikipediaClient()
        self.cache = GraphCache()
        
    async def __aenter__(self):
        await self.client.__aenter__()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.__aexit__(exc_type, exc_val, exc_tb)
    
    async def find_path(self, start: str, target: str) -> Optional[List[str]]:
        """
        Find shortest path between start and target pages.
        
        Args:
            start: Starting page title
            target: Target page title
            
        Returns:
            List of page titles representing the path, or None if no path found
        """
        start_time = time.time()
        logger.info(f"Finding path from '{start}' to '{target}'")
        
        # Resolve redirects first
        redirects = await self.client.resolve_redirects([start, target])
        canonical_start = redirects[start]
        canonical_target = redirects[target]
        
        logger.info(f"Canonical titles: '{canonical_start}' → '{canonical_target}'")
        
        # Set target in cache (triggers cache clear if different)
        self.cache.set_target(canonical_target)
        
        # Check if start == target
        if canonical_start == canonical_target:
            return [canonical_start]
        
        # Initialize bidirectional search
        forward_state = SearchState(
            visited=set([canonical_start]),
            queue=deque([canonical_start]),
            distances={canonical_start: 0},
            parents={},
            direction="forward"
        )
        
        backward_state = SearchState(
            visited=set([canonical_target]),
            queue=deque([canonical_target]),
            distances={canonical_target: 0},
            parents={},
            direction="backward"
        )
        
        # Main search loop
        max_iterations = 10  # Reasonable limit to avoid infinite loops
        iteration = 0
        
        while forward_state.queue and backward_state.queue and iteration < max_iterations:
            iteration += 1
            logger.info(f"Iteration {iteration}: Forward queue={len(forward_state.queue)}, "
                       f"Backward queue={len(backward_state.queue)}")
            
            # Choose smaller frontier to expand (optimization)
            if len(forward_state.queue) <= len(backward_state.queue):
                intersection = await self._expand_level(forward_state, backward_state)
            else:
                intersection = await self._expand_level(backward_state, forward_state)
            
            if intersection:
                path = self._reconstruct_path(intersection, forward_state, backward_state)
                elapsed = time.time() - start_time
                logger.info(f"Path found in {elapsed:.2f}s, {iteration} iterations, "
                           f"path length: {len(path)}")
                logger.info(f"Cache stats: {self.cache.get_cache_stats()}")
                return path
        
        elapsed = time.time() - start_time
        logger.warning(f"No path found after {iteration} iterations in {elapsed:.2f}s")
        logger.info(f"Final cache stats: {self.cache.get_cache_stats()}")
        return None
    
    async def _expand_level(self, expanding_state: SearchState, 
                          other_state: SearchState) -> Optional[str]:
        """
        Expand one level of BFS and check for intersection.
        
        Args:
            expanding_state: The search state to expand
            other_state: The other search state to check intersection with
            
        Returns:
            Page title where searches meet, or None if no intersection
        """
        if not expanding_state.queue:
            return None
            
        # Get all pages at current level
        current_level = list(expanding_state.queue)
        expanding_state.queue.clear()
        
        logger.debug(f"Expanding {expanding_state.direction} level with {len(current_level)} pages")
        
        # Get neighbors for all pages in this level
        neighbors_data = await self._get_neighbors_batch(current_level, expanding_state.direction)
        
        # Process each page and its neighbors
        for page in current_level:
            neighbors = neighbors_data.get(page, set())
            current_distance = expanding_state.distances[page]
            
            for neighbor in neighbors:
                # Skip if already visited in this direction
                if neighbor in expanding_state.visited:
                    continue
                    
                # Add to search state
                expanding_state.visited.add(neighbor)
                expanding_state.queue.append(neighbor)
                expanding_state.distances[neighbor] = current_distance + 1
                expanding_state.parents[neighbor] = page
                
                # Check for intersection with other search
                if neighbor in other_state.visited:
                    logger.info(f"Intersection found at '{neighbor}' "
                              f"(distance {expanding_state.distances[neighbor]} + "
                              f"{other_state.distances[neighbor]})")
                    return neighbor
        
        logger.debug(f"After expansion: {expanding_state.direction} visited={len(expanding_state.visited)}, "
                    f"queue={len(expanding_state.queue)}")
        return None
    
    async def _get_neighbors_batch(self, pages: List[str], direction: str) -> Dict[str, Set[str]]:
        """
        Get neighbors for a batch of pages, using cache when possible.
        
        Args:
            pages: List of page titles
            direction: "forward" or "backward"
            
        Returns:
            Dict mapping page title to set of neighbor titles
        """
        results = {}
        pages_to_fetch = []
        
        # Check cache first
        for page in pages:
            if self.cache.is_fetched(page, direction):
                results[page] = self.cache.get_neighbors(page, direction)
                logger.debug(f"Cache hit for {direction} links of '{page}': {len(results[page])} links")
            else:
                pages_to_fetch.append(page)
        
        # Fetch missing pages from API
        if pages_to_fetch:
            logger.info(f"Fetching {direction} links for {len(pages_to_fetch)} pages from API")
            
            if direction == "forward":
                api_results = await self.client.get_forward_links(pages_to_fetch)
            else:  # backward
                api_results = await self.client.get_backward_links(pages_to_fetch)
            
            # Update cache and results
            for page, links in api_results.items():
                if direction == "forward":
                    self.cache.add_page_links(page, outgoing=links)
                else:
                    self.cache.add_page_links(page, incoming=links)
                results[page] = links
        
        return results
    
    def _reconstruct_path(self, meeting_point: str, forward_state: SearchState, 
                         backward_state: SearchState) -> List[str]:
        """
        Reconstruct the path when bidirectional searches meet.
        
        Args:
            meeting_point: Page where searches intersected
            forward_state: Forward search state
            backward_state: Backward search state
            
        Returns:
            Complete path from start to target
        """
        # Build path from start to meeting point
        forward_path = []
        current = meeting_point
        while current in forward_state.parents:
            forward_path.append(current)
            current = forward_state.parents[current]
        forward_path.append(current)  # Add the start page
        forward_path.reverse()
        
        # Build path from meeting point to target
        backward_path = []
        current = meeting_point
        while current in backward_state.parents:
            current = backward_state.parents[current]
            backward_path.append(current)
        
        # Combine paths (avoid duplicating meeting point)
        complete_path = forward_path + backward_path
        
        logger.info(f"Reconstructed path: {' → '.join(complete_path)}")
        return complete_path
    
    async def close(self):
        """Close resources if not using context manager."""
        await self.client.close() 