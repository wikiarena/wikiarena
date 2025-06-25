"""
StaticSolverDB - The sole gateway to the hyper-optimized wiki_graph.sqlite database.
This service is used purely for analytical purposes and graph analysis.
"""

import sqlite3
import logging
from typing import List, Set, Optional, Tuple, Dict, Any
from pathlib import Path
import asyncio
import aiosqlite
import math
import time
from dataclasses import dataclass, field

from wiki_arena.utils.wiki_helpers import (
    get_sanitized_page_title, 
    get_readable_page_title,
    validate_page_id,
    validate_page_title
)

logger = logging.getLogger(__name__)

@dataclass
class CacheStats:
    """Track cache hit/miss statistics for measurement."""
    hits: int = 0
    misses: int = 0
    total_requests: int = 0
    start_time: float = field(default_factory=time.time)
    
    @property
    def hit_rate(self) -> float:
        """Calculate hit rate as percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.hits / self.total_requests) * 100
    
    @property
    def runtime_minutes(self) -> float:
        """Calculate runtime in minutes."""
        return (time.time() - self.start_time) / 60
    
    def reset(self):
        """Reset all statistics and restart timing."""
        self.hits = 0
        self.misses = 0
        self.total_requests = 0
        self.start_time = time.time()
    
    def log_stats(self, operation_name: str):
        """Log current statistics."""
        logger.info(
            f"Cooperative cache stats for {operation_name}: "
            f"{self.hits}/{self.total_requests} hits ({self.hit_rate:.1f}%) "
            f"over {self.runtime_minutes:.1f} minutes"
        )

class CooperativeCache:
    """Manages cooperative caching for database operations to prevent duplicate work."""
    
    def __init__(self):
        self.ongoing_operations: Dict[str, asyncio.Task] = {}
        self.operation_lock = asyncio.Lock()
        self.stats = CacheStats()
        
    async def get_or_execute(self, key: str, operation_func, *args, **kwargs) -> Any:
        """
        Get result from ongoing operation or start new one.
        
        Args:
            key: Unique identifier for this operation
            operation_func: The actual database operation to execute
            *args, **kwargs: Arguments for operation_func
            
        Returns:
            Result of the operation
        """
        self.stats.total_requests += 1
        
        # Check if operation is already running
        async with self.operation_lock:
            if key in self.ongoing_operations:
                self.stats.hits += 1
                logger.debug(f"Cooperative cache HIT for operation: {key}")
                try:
                    result = await self.ongoing_operations[key]
                    return result
                except Exception as e:
                    # If the ongoing operation failed, remove it and we'll start a new one
                    logger.warning(f"Ongoing operation {key} failed: {e}")
                    self.ongoing_operations.pop(key, None)
                    # Fall through to start new operation
            
            # Start new operation
            self.stats.misses += 1
            logger.debug(f"Cooperative cache MISS for operation: {key}")
            task = asyncio.create_task(operation_func(*args, **kwargs))
            self.ongoing_operations[key] = task
        
        try:
            result = await task
            return result
        except Exception as e:
            logger.error(f"Operation {key} failed: {e}")
            raise
        finally:
            # Clean up completed operation
            async with self.operation_lock:
                self.ongoing_operations.pop(key, None)
    
    def get_stats(self) -> CacheStats:
        """Get current cache statistics."""
        return self.stats
    
    def reset_stats(self):
        """Reset cache statistics."""
        self.stats.reset()
    
    def log_stats(self, operation_name: str = "all_operations"):
        """Log current cache statistics."""
        self.stats.log_stats(operation_name)

class StaticSolverDB:
    """
    The sole gateway to the hyper-optimized wiki_graph.sqlite database.
    
    This service provides access to Wikipedia link graph data for analytical purposes,
    including pathfinding and graph analysis. It's completely independent of the 
    GameManager and LiveWikiService.
    
    Key methods:
    - get_shortest_path_length(from_title: str, to_title: str) -> int: 
      Returns the number of steps in the optimal path between two pages.
    """
    
    def __init__(self, db_path: str = "database/wiki_graph.sqlite"):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            logger.error(f"Database file not found at {self.db_path.resolve()}")
            # Consider raising an error here if the DB is essential for startup
            # For now, proceeding will likely lead to errors in DB operations.
        self._connection_pool = {}
        
        self.max_variables = 32766 # Safe default for 3.32.0 and later, will be updated from PRAGMA
        self._initialize_variable_limit()
        
        # Cooperative caching for preventing duplicate operations
        self.cooperative_cache = CooperativeCache()
        
    def _initialize_variable_limit(self):
        """Initialize the SQLite variable limit by reading from PRAGMA compile_options."""
        try:
            # Use sync connection for initialization
            with sqlite3.connect(self.db_path) as db:
                cursor = db.execute("PRAGMA compile_options")
                for row in cursor:
                    option = row[0]
                    if option.startswith("MAX_VARIABLE_NUMBER="):
                        max_vars = int(option.split("=")[1])
                        self.max_variables = int(max_vars)
                        logger.info(f"SQLite MAX_VARIABLE_NUMBER: {max_vars}, using limit: {self.max_variables}")
                        break
                else:
                    logger.warning(f"Could not find MAX_VARIABLE_NUMBER in PRAGMA, using default: {self.max_variables}")
        except Exception as e:
            logger.warning(f"Failed to read SQLite variable limit: {e}, using default: {self.max_variables}")
        
    async def get_page_id(self, title: str, namespace: int = 0) -> Optional[int]:
        """
        Get the page ID for a given title, optionally filtering by namespace.
        Handles redirects and capitalization.

        Args:
            title (str): The page title to look up.
            namespace (int): Namespace to restrict search to. Use -1 to search across all namespaces.
                            Default is 0 (main/article namespace).

        Returns:
            Optional[int]: The resolved page ID, or None if not found.
        """
        validate_page_title(title)
        sanitized_title = get_sanitized_page_title(title)
        
        # Create cache key for this operation
        cache_key = f"page_id_{sanitized_title}_{namespace}"
        return await self.cooperative_cache.get_or_execute(
            cache_key, self._get_page_id_impl, title, namespace
        )
    
    async def _get_page_id_impl(self, title: str, namespace: int = 0) -> Optional[int]:
        """Internal implementation of get_page_id without caching."""
        validate_page_title(title)
        sanitized_title = get_sanitized_page_title(title)

        async with aiosqlite.connect(self.db_path) as db:
            if namespace == -1:
                query = """
                    SELECT id, title, is_redirect
                    FROM pages
                    WHERE title = ? COLLATE NOCASE
                """
                args = (sanitized_title,)
            else:
                query = """
                    SELECT id, title, is_redirect
                    FROM pages
                    WHERE title = ? COLLATE NOCASE AND namespace = ?
                """
                args = (sanitized_title, namespace)

            async with db.execute(query, args) as cursor:
                results = await cursor.fetchall()

            if not results:
                logger.warning(f"No page found for title: '{title}' in namespace={namespace} (sanitized: '{sanitized_title}')")
                return None

            for page_id, db_title, is_redirect in results:
                if db_title == sanitized_title and not is_redirect:
                    return page_id

            for page_id, db_title, is_redirect in results:
                if not is_redirect:
                    return page_id

            first_result_id, _, _ = results[0]
            redirect_query = "SELECT target_id FROM redirects WHERE source_id = ?"
            async with db.execute(redirect_query, (first_result_id,)) as cursor:
                redirect_row = await cursor.fetchone()
                if redirect_row:
                    return redirect_row[0]
                else:
                    logger.warning(
                        f"Page '{title}' (namespace={namespace}) is a redirect but no target found for ID {first_result_id}."
                    )
                    return None

        return None

    async def get_page_title(self, page_id: int) -> Optional[str]:
        """Get the readable title for a given page ID."""
        validate_page_id(page_id)
        
        cache_key = f"page_title_{page_id}"
        return await self.cooperative_cache.get_or_execute(
            cache_key, self._get_page_title_impl, page_id
        )
    
    async def _get_page_title_impl(self, page_id: int) -> Optional[str]:
        """Internal implementation of get_page_title without caching."""
        async with aiosqlite.connect(self.db_path) as db:
            query = "SELECT title FROM pages WHERE id = ?"
            async with db.execute(query, (page_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return get_readable_page_title(row[0]) 
                return None
    
    async def get_outgoing_links(self, page_id: int) -> List[int]:
        """Get all page IDs that this page links to.
        The 'links' table in wiki_graph.sqlite has 'id' (source_page_id) 
        and 'outgoing_links' (pipe-separated string of target_page_ids).
        """
        validate_page_id(page_id)
        
        cache_key = f"outgoing_{page_id}"
        return await self.cooperative_cache.get_or_execute(
            cache_key, self._get_outgoing_links_impl, page_id
        )
    
    async def _get_outgoing_links_impl(self, page_id: int) -> List[int]:
        """Internal implementation of get_outgoing_links without caching."""
        async with aiosqlite.connect(self.db_path) as db:
            query = "SELECT outgoing_links FROM links WHERE id = ?"
            async with db.execute(query, (page_id,)) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    return [int(target_id) for target_id in row[0].split('|') if target_id]
                return []

    async def get_incoming_links(self, page_id: int) -> List[int]:
        """Get all page IDs that link to this page.
        The 'links' table in wiki_graph.sqlite has 'id' (target_page_id for this query's purpose) 
        and 'incoming_links' (pipe-separated string of source_page_ids).
        """
        validate_page_id(page_id)
        
        cache_key = f"incoming_{page_id}"
        return await self.cooperative_cache.get_or_execute(
            cache_key, self._get_incoming_links_impl, page_id
        )
    
    async def _get_incoming_links_impl(self, page_id: int) -> List[int]:
        """Internal implementation of get_incoming_links without caching."""
        async with aiosqlite.connect(self.db_path) as db:
            query = "SELECT incoming_links FROM links WHERE id = ?"
            async with db.execute(query, (page_id,)) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    return [int(source_id) for source_id in row[0].split('|') if source_id]
                return []
                
    async def batch_get_page_titles(self, page_ids: List[int]) -> List[str]:
        """Get titles for multiple page IDs. Titles are returned in the same order as page_ids.
        Missing IDs will result in None at the corresponding position.
        """
        if not page_ids:
            return []
        
        for pid in page_ids:
            validate_page_id(pid)

        # Handle large batches by splitting them
        if len(page_ids) > self.max_variables:
            return await self._batch_get_page_titles_chunked(page_ids)

        # Create cache key based on sorted page_ids to handle different orderings
        cache_key = f"batch_titles_{hash(tuple(sorted(page_ids)))}"
        cached_result = await self.cooperative_cache.get_or_execute(
            cache_key, self._batch_get_page_titles_impl, page_ids
        )
        
        # The cached result might be in different order, so we need to reorder
        if isinstance(cached_result, dict):
            # If implementation returned dict, convert to ordered list
            return [cached_result.get(page_id) for page_id in page_ids]
        else:
            # If implementation returned ordered list, use as-is
            return cached_result

    async def _batch_get_page_titles_impl(self, page_ids: List[int]) -> List[str]:
        """Internal implementation of batch_get_page_titles without caching."""
        id_to_index = {page_id: i for i, page_id in enumerate(page_ids)}
        results = [None] * len(page_ids)
            
        placeholders = ",".join("?" * len(page_ids))
        query = f"SELECT id, title FROM pages WHERE id IN ({placeholders})"
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, page_ids) as cursor:
                async for row_id, sanitized_title in cursor:
                    if row_id in id_to_index:
                        readable_title = get_readable_page_title(sanitized_title)
                        results[id_to_index[row_id]] = readable_title
        return results

    async def _batch_get_page_titles_chunked(self, page_ids: List[int]) -> List[str]:
        """Handle large page_ids lists by chunking them into smaller batches."""
        results = [None] * len(page_ids)
        chunk_size = self.max_variables

        logger.debug(f"Chunking {len(page_ids)} page IDs into batches of {chunk_size}")
        
        for i in range(0, len(page_ids), chunk_size):
            chunk = page_ids[i:i + chunk_size]
            chunk_results = await self.batch_get_page_titles(chunk)
            
            # Copy chunk results to the correct positions in the full results
            for j, result in enumerate(chunk_results):
                results[i + j] = result
                
        return results
    
    async def batch_get_page_ids(self, titles: List[str]) -> Dict[str, Optional[int]]:
        """Get page IDs for multiple titles. Returns a dict mapping original title to page_id or None."""
        if not titles:
            return {}
        
        # Create cache key for batch operation
        cache_key = f"batch_ids_{hash(tuple(sorted(titles)))}"
        return await self.cooperative_cache.get_or_execute(
            cache_key, self._batch_get_page_ids_impl, titles
        )
    
    async def _batch_get_page_ids_impl(self, titles: List[str]) -> Dict[str, Optional[int]]:
        """Internal implementation of batch_get_page_ids without caching."""
        results: Dict[str, Optional[int]] = {title: None for title in titles}
        for title in titles:
            page_id = await self.get_page_id(title)
            results[title] = page_id
        return results

    async def get_database_stats(self) -> Tuple[int, int]:
        """Get total number of pages and links."""
        cache_key = "database_stats"
        return await self.cooperative_cache.get_or_execute(
            cache_key, self._get_database_stats_impl
        )
    
    async def _get_database_stats_impl(self) -> Tuple[int, int]:
        """Internal implementation of get_database_stats without caching."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM pages") as cursor:
                page_count_row = await cursor.fetchone()
                page_count = page_count_row[0] if page_count_row else 0
            
            async with db.execute("SELECT SUM(outgoing_links_count) FROM links") as cursor:
                link_count_row = await cursor.fetchone()
                link_count = link_count_row[0] if link_count_row and link_count_row[0] is not None else 0
                
            return page_count, int(link_count)
    
    async def page_exists(self, title: str) -> bool:
        """Check if a page exists in the database (after handling redirects)."""
        page_id = await self.get_page_id(title)
        return page_id is not None

    async def fetch_outgoing_links_count(self, page_ids: List[int]) -> int:
        """Returns the sum of outgoing links of the provided page IDs."""
        return await self._fetch_links_count_helper(page_ids, "outgoing_links_count")

    async def fetch_incoming_links_count(self, page_ids: List[int]) -> int:
        """Returns the sum of incoming links for the provided page IDs."""
        return await self._fetch_links_count_helper(page_ids, "incoming_links_count")

    async def _fetch_links_count_helper(self, page_ids: List[int], count_column_name: str) -> int:
        """Helper to sum link counts from the specified column for given page IDs."""
        if not page_ids:
            return 0
        
        for pid in page_ids:
            validate_page_id(pid)

        if count_column_name not in ["outgoing_links_count", "incoming_links_count"]:
            raise ValueError(f"Invalid count column name: {count_column_name}")

        # Handle large batches by chunking them
        if len(page_ids) > self.max_variables:
            return await self._fetch_links_count_chunked(page_ids, count_column_name)

        # Create cache key for this operation
        cache_key = f"{count_column_name}_{hash(tuple(sorted(page_ids)))}"
        return await self.cooperative_cache.get_or_execute(
            cache_key, self._fetch_links_count_impl, page_ids, count_column_name
        )
    
    async def _fetch_links_count_impl(self, page_ids: List[int], count_column_name: str) -> int:
        """Internal implementation of fetch links count without caching."""
        placeholders = ",".join("?" * len(page_ids))
        query = f"SELECT SUM({count_column_name}) FROM links WHERE id IN ({placeholders})"
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, page_ids) as cursor:
                row = await cursor.fetchone()
                return row[0] if row and row[0] is not None else 0

    async def _fetch_links_count_chunked(self, page_ids: List[int], count_column_name: str) -> int:
        """Handle large page_ids lists by chunking them and summing the results."""
        total_count = 0
        chunk_size = self.max_variables
        
        logger.debug(f"Chunking {len(page_ids)} page IDs into batches of {chunk_size}")
        
        for i in range(0, len(page_ids), chunk_size):
            chunk = page_ids[i:i + chunk_size]
            chunk_count = await self._fetch_links_count_helper(chunk, count_column_name)
            total_count += chunk_count
            
        return total_count
    
    def get_cache_stats(self) -> CacheStats:
        """Get current cooperative cache statistics."""
        return self.cooperative_cache.get_stats()
    
    def reset_cache_stats(self):
        """Reset cooperative cache statistics."""
        self.cooperative_cache.reset_stats()
    
    def log_cache_stats(self):
        """Log current cooperative cache statistics."""
        self.cooperative_cache.log_stats("StaticSolverDB")


# Global instance for the static solver database
static_solver_db = StaticSolverDB() 