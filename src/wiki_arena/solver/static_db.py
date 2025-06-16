"""
StaticSolverDB - The sole gateway to the hyper-optimized wiki_graph.sqlite database.
This service is used purely for analytical purposes and graph analysis.
"""

import sqlite3
import logging
from typing import List, Set, Optional, Tuple, Dict
from pathlib import Path
import asyncio
import aiosqlite

from wiki_arena.utils.wiki_helpers import (
    get_sanitized_page_title, 
    get_readable_page_title,
    validate_page_id,
    validate_page_title
)

logger = logging.getLogger(__name__)

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
    
    async def batch_get_page_ids(self, titles: List[str]) -> Dict[str, Optional[int]]:
        """Get page IDs for multiple titles. Returns a dict mapping original title to page_id or None."""
        if not titles:
            return {}
        
        results: Dict[str, Optional[int]] = {title: None for title in titles}
        for title in titles:
            page_id = await self.get_page_id(title)
            results[title] = page_id
        return results

    async def get_database_stats(self) -> Tuple[int, int]:
        """Get total number of pages and links."""
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

        placeholders = ",".join("?" * len(page_ids))
        if count_column_name not in ["outgoing_links_count", "incoming_links_count"]:
            raise ValueError(f"Invalid count column name: {count_column_name}")

        query = f"SELECT SUM({count_column_name}) FROM links WHERE id IN ({placeholders})"
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, page_ids) as cursor:
                row = await cursor.fetchone()
                return row[0] if row and row[0] is not None else 0


# Global instance for the static solver database
static_solver_db = StaticSolverDB() 