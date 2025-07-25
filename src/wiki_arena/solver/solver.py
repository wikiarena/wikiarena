"""
WikiTaskSolver - Service for finding shortest paths between Wikipedia pages.

This service uses bidirectional BFS with intelligent caching to efficiently find
the shortest paths between Wikipedia pages using the static wiki graph database.
"""

import asyncio
import time
import logging
from typing import List, Dict, Set, Optional, Tuple

from .static_db import StaticSolverDB
from .models import SolverResponse

logger = logging.getLogger(__name__)


class WikiTaskSolver:
    """Service for finding shortest paths between Wikipedia pages using bidirectional BFS."""
    
    def __init__(self, db: Optional[StaticSolverDB] = None, cache_ttl_seconds: int = 30):
        """
        Initialize the task solver.
        
        Args:
            db: StaticSolverDB instance. If None, uses the global static_solver_db.
            cache_ttl_seconds: Time-to-live for all cache entries (default: 30 seconds)
        """
        if db is None:
            from .static_db import static_solver_db
            self.db = static_solver_db
        else:
            self.db = db
            
        self.cache_ttl = cache_ttl_seconds
        
        # Individual item caches - persistent across all targets with TTL
        self.title_to_page_id: Dict[str, Optional[int]] = {}
        self.page_id_to_title: Dict[int, Optional[str]] = {}
        self.outgoing_links: Dict[int, List[int]] = {}
        self.incoming_links: Dict[int, List[int]] = {}
        self.outgoing_links_count: Dict[int, int] = {}
        self.incoming_links_count: Dict[int, int] = {}
        
        # TTL tracking - separate dictionaries for each cache type
        self._title_to_id_times: Dict[str, float] = {}
        self._id_to_title_times: Dict[int, float] = {}
        self._outgoing_times: Dict[int, float] = {}
        self._incoming_times: Dict[int, float] = {}
        self._backward_bfs_times: Dict[int, float] = {}
        
        # --- Cooperative fetch state ---
        # page_id -> Future that will resolve to List[int]
        self._pending_outgoing: Dict[int, asyncio.Future[List[int]]] = {}
        self._pending_incoming: Dict[int, asyncio.Future[List[int]]] = {}
        
        # --- Backward BFS caches per target with TTL ---
        # target_id -> {"visited": Dict[int, List[Optional[int]]],
        #               "unvisited": Dict[int, List[Optional[int]]]}
        self.backward_bfs_cache: Dict[int, Dict[str, Dict[int, List[Optional[int]]]]] = {}
        
        # --- Per-target locks for backward BFS coordination ---
        # Ensures only one backward expansion per target at a time
        self._target_locks: Dict[int, asyncio.Lock] = {}
        
        # Cache cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._start_cleanup_task()

        """
        Instead of counting the incoming and outgoing links before choosing which direction to expand
        we use a 'so trivial you would think it is only way' heuristic based on frontier size to choose which direction to expand.
        
        TECHNICAL NOTE: The "theoretically correct" approach would be to count actual outgoing/incoming links
        for each frontier and expand the direction with fewer total links. However, this requires
        expensive database queries on every BFS level, often costing more time than the expansion itself.
        
        In theory, the whole graph of wikipedia pages has the same the number of incoming and outgoing links
        In reality this is actually true: avg incoming links ≈ avg outgoing links (both ~38)
        so frontier_size is exactly proportional to total_links in expectation. 
        This gives near-optimal direction selection with O(1) cost instead of O(frontier_size) database queries.
        """

    def _start_cleanup_task(self):
        """Start the background cache cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def _periodic_cleanup(self):
        """Periodically clean up expired cache entries."""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                await self._cleanup_expired_entries()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cache cleanup: {e}", exc_info=True)

    async def _cleanup_expired_entries(self):
        """Remove expired entries from all caches."""
        current_time = time.time()
        total_expired = 0
        
        # Clean title_to_page_id cache
        expired_titles = [title for title, last_access in self._title_to_id_times.items() 
                         if current_time - last_access > self.cache_ttl]
        for title in expired_titles:
            self.title_to_page_id.pop(title, None)
            self._title_to_id_times.pop(title, None)
        total_expired += len(expired_titles)
        
        # Clean page_id_to_title cache
        expired_ids = [page_id for page_id, last_access in self._id_to_title_times.items()
                      if current_time - last_access > self.cache_ttl]
        for page_id in expired_ids:
            self.page_id_to_title.pop(page_id, None)
            self._id_to_title_times.pop(page_id, None)
        total_expired += len(expired_ids)
        
        # Clean outgoing links cache
        expired_outgoing = [page_id for page_id, last_access in self._outgoing_times.items()
                           if current_time - last_access > self.cache_ttl]
        for page_id in expired_outgoing:
            self.outgoing_links.pop(page_id, None)
            self.outgoing_links_count.pop(page_id, None)
            self._outgoing_times.pop(page_id, None)
        total_expired += len(expired_outgoing)
        
        # Clean incoming links cache
        expired_incoming = [page_id for page_id, last_access in self._incoming_times.items()
                           if current_time - last_access > self.cache_ttl]
        for page_id in expired_incoming:
            self.incoming_links.pop(page_id, None)
            self.incoming_links_count.pop(page_id, None)
            self._incoming_times.pop(page_id, None)
        total_expired += len(expired_incoming)
        
        # Clean backward BFS cache
        expired_bfs = [target_id for target_id, last_access in self._backward_bfs_times.items()
                      if current_time - last_access > self.cache_ttl]
        for target_id in expired_bfs:
            self.backward_bfs_cache.pop(target_id, None)
            self._backward_bfs_times.pop(target_id, None)
        total_expired += len(expired_bfs)
        
        if total_expired > 0:
            logger.info(f"Cleaned up {total_expired} expired cache entries")

    def _touch_title_to_id(self, title: str):
        """Update the last access time for a title_to_id cache entry."""
        self._title_to_id_times[title] = time.time()

    def _touch_id_to_title(self, page_id: int):
        """Update the last access time for an id_to_title cache entry."""
        self._id_to_title_times[page_id] = time.time()

    def _touch_outgoing(self, page_id: int):
        """Update the last access time for an outgoing links cache entry."""
        self._outgoing_times[page_id] = time.time()

    def _touch_incoming(self, page_id: int):
        """Update the last access time for an incoming links cache entry."""
        self._incoming_times[page_id] = time.time()

    def _touch_backward_bfs(self, target_id: int):
        """Update the last access time for a backward BFS cache entry."""
        self._backward_bfs_times[target_id] = time.time()

    async def _get_page_id(self, title: str) -> Optional[int]:
        """Get page ID with caching and TTL."""
        if title in self.title_to_page_id:
            self._touch_title_to_id(title)
            return self.title_to_page_id[title]
        
        result = await self.db.get_page_id(title)
        self.title_to_page_id[title] = result
        self._touch_title_to_id(title)
        return result

    async def _get_page_title(self, page_id: int) -> Optional[str]:
        """Get page title with caching and TTL."""
        if page_id in self.page_id_to_title:
            self._touch_id_to_title(page_id)
            return self.page_id_to_title[page_id]
        
        result = await self.db.get_page_title(page_id)
        self.page_id_to_title[page_id] = result
        self._touch_id_to_title(page_id)
        return result

    async def _batch_get_page_titles(self, page_ids: List[int]) -> Dict[int, Optional[str]]:
        """Get page titles for multiple IDs with caching and TTL."""
        result_map = {}
        missing_ids = []
        
        # Check cache first
        for page_id in page_ids:
            if page_id in self.page_id_to_title:
                self._touch_id_to_title(page_id)
                result_map[page_id] = self.page_id_to_title[page_id]
            else:
                missing_ids.append(page_id)
        
        # Fetch missing IDs from database
        if missing_ids:
            titles = await self.db.batch_get_page_titles(missing_ids)
            for page_id, title in zip(missing_ids, titles):
                self.page_id_to_title[page_id] = title
                self._touch_id_to_title(page_id)
                result_map[page_id] = title
        
        return result_map

    async def _get_outgoing_links(self, page_id: int) -> List[int]:
        """Get outgoing links with cooperative caching and TTL."""
        if page_id in self.outgoing_links:
            self._touch_outgoing(page_id)
            return self.outgoing_links[page_id]

        # Cooperative fetch: if another coroutine is already fetching, await it
        fut = self._pending_outgoing.get(page_id)
        if fut is not None:
            return await fut

        # We are the first – create a future and perform the DB call
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending_outgoing[page_id] = fut
        try:
            result = await self.db.get_outgoing_links(page_id)
            # store in permanent cache
            self.outgoing_links[page_id] = result
            self.outgoing_links_count[page_id] = len(result)
            self._touch_outgoing(page_id)
            fut.set_result(result)
            return result
        except Exception as exc:
            fut.set_exception(exc)
            raise
        finally:
            # Clean pending entry regardless of outcome
            self._pending_outgoing.pop(page_id, None)

    async def _get_incoming_links(self, page_id: int) -> List[int]:
        """Get incoming links with cooperative caching and TTL."""
        if page_id in self.incoming_links:
            self._touch_incoming(page_id)
            return self.incoming_links[page_id]

        fut = self._pending_incoming.get(page_id)
        if fut is not None:
            return await fut

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending_incoming[page_id] = fut
        try:
            result = await self.db.get_incoming_links(page_id)
            self.incoming_links[page_id] = result
            self.incoming_links_count[page_id] = len(result)
            self._touch_incoming(page_id)
            fut.set_result(result)
            return result
        except Exception as exc:
            fut.set_exception(exc)
            raise
        finally:
            self._pending_incoming.pop(page_id, None)

    async def _fetch_outgoing_links_count(self, page_ids: List[int]) -> int:
        """Get sum of outgoing link counts with caching."""
        total_count = 0
        missing_ids = []
        
        # Check cache first
        for page_id in page_ids:
            if page_id in self.outgoing_links_count:
                self._touch_outgoing(page_id)
                total_count += self.outgoing_links_count[page_id]
            else:
                missing_ids.append(page_id)
        
        # For missing IDs, fetch only counts from database (not expensive links)
        if missing_ids:
            # Use database sum method for missing pages
            missing_count = await self.db.fetch_outgoing_links_count(missing_ids)
            total_count += missing_count
            # Note: We don't cache individual counts from the sum since we can't break it down
        
        return total_count

    async def _fetch_incoming_links_count(self, page_ids: List[int]) -> int:
        """Get sum of incoming link counts with caching."""
        total_count = 0
        missing_ids = []
        
        # Check cache first
        for page_id in page_ids:
            if page_id in self.incoming_links_count:
                self._touch_incoming(page_id)
                total_count += self.incoming_links_count[page_id]
            else:
                missing_ids.append(page_id)
        
        # For missing IDs, fetch only counts from database (not expensive links)
        if missing_ids:
            # Use database sum method for missing pages
            missing_count = await self.db.fetch_incoming_links_count(missing_ids)
            total_count += missing_count
            # Note: We don't cache individual counts from the sum since we can't break it down
        
        return total_count
        
    async def find_shortest_path(self, start_page: str, target_page: str) -> SolverResponse:
        """
        Find the shortest path(s) between two Wikipedia pages.
        
        Args:
            start_page: Starting page title
            target_page: Target page title
            
        Returns:
            SolverResponse containing all shortest paths and metadata
            
        Raises:
            ValueError: If start or target page not found, or no path exists
        """
        request_start_time = time.time()
        
        # Get page IDs using cached method
        start_id = await self._get_page_id(start_page)
        target_id = await self._get_page_id(target_page)
        
        if start_id is None:
            raise ValueError(f"Start page '{start_page}' not found in database.")
        if target_id is None:
            raise ValueError(f"Target page '{target_page}' not found in database.")

        # Ensure we have a lock for this target
        if target_id not in self._target_locks:
            self._target_locks[target_id] = asyncio.Lock()

        if start_id == target_id:
            path_titles = [[start_page]]
            computation_time_ms = (time.time() - request_start_time) * 1000
            return SolverResponse(
                paths=path_titles, 
                path_length=0,
                computation_time_ms=computation_time_ms,
            )
        
        # Perform BFS using adapted bidirectional search
        actual_computation_start_time = time.time()
        paths_as_ids, bfs_levels = await self._bidirectional_bfs(start_id, target_id, self._target_locks[target_id])
        
        if not paths_as_ids:
            raise ValueError(f"No path found between '{start_page}' and '{target_page}'.")

        # Optimized title conversion: collect all unique page IDs across all paths
        title_conversion_start_time = time.perf_counter()
        all_unique_page_ids = set()
        for path in paths_as_ids:
            all_unique_page_ids.update(path)

        # Get titles for all unique IDs in one optimized cached call  
        page_id_to_title_map = await self._batch_get_page_titles(list(all_unique_page_ids))

        # Reconstruct all paths using the mapping
        all_paths_as_titles = []
        for id_path in paths_as_ids:
            title_path = [page_id_to_title_map[page_id] for page_id in id_path]
            if any(t is None for t in title_path):
                logger.error(f"Path {id_path} contained an ID with no title")
                continue
            all_paths_as_titles.append(title_path)
        
        title_conversion_time = time.perf_counter() - title_conversion_start_time
        total_page_ids_converted = len(all_unique_page_ids)
        logger.debug(
            f"Title conversion: {total_page_ids_converted} unique page IDs converted "
            f"in {title_conversion_time*1000:.1f}ms"
        )

        if not all_paths_as_titles:
             raise ValueError(f"Path IDs found but title conversion failed for '{start_page}' -> '{target_page}'.")

        actual_computation_time_ms = (time.time() - actual_computation_start_time) * 1000
        
        # Log comprehensive solve summary
        logger.info(
            f"SOLVE SUMMARY for {start_page} -> {target_page}: "
            f"Path length: {len(all_paths_as_titles[0])-1}, "
            f"Paths found: {len(all_paths_as_titles)}, "
            f"BFS levels: {bfs_levels}, "
            f"Total time: {actual_computation_time_ms:.1f}ms"
        )

        return SolverResponse(
            paths=all_paths_as_titles,
            path_length=len(all_paths_as_titles[0]) - 1,
            computation_time_ms=actual_computation_time_ms
        )

    async def _get_paths_recursive(
        self, 
        page_ids: List[Optional[int]], 
        visited_dict: Dict[int, List[Optional[int]]], 
        is_forward_path: bool
    ) -> List[List[int]]:
        """
        Recursively reconstructs paths from a list of page IDs to the BFS origin.
        
        Args:
            page_ids: List of parent IDs, None signifies source/target
            visited_dict: Map from child_id to list_of_parent_ids for that search direction
            is_forward_path: True if reconstructing from source, False if from target
            
        Returns:
            List of paths, where each path starts from the BFS origin and ends at one of the page_ids' children
        """
        paths = []
        for page_id in page_ids:
            if page_id is None:  # Base case: reached the origin of this BFS direction
                paths.append([])
            else:
                # Parents of `page_id` in this BFS direction
                parent_ids_of_current_page_id = visited_dict.get(page_id)
                if parent_ids_of_current_page_id is None:
                    logger.error(f"Error in path reconstruction: page_id {page_id} not in visited_dict.")
                    continue 

                current_partial_paths = await self._get_paths_recursive(
                    parent_ids_of_current_page_id, visited_dict, is_forward_path
                )
                for partial_path in current_partial_paths:
                    new_path = list(partial_path)
                    new_path.append(page_id)
                    paths.append(new_path)
        return paths

    async def _bidirectional_bfs(self, start_id: int, target_id: int, target_lock: asyncio.Lock) -> Tuple[List[List[int]], int]:
        """
        Bidirectional BFS implementation with per-target caching and TTL.
        
        Args:
            start_id: Starting page ID
            target_id: Target page ID
            target_lock: Lock for coordinating backward expansions for this target
            
        Returns:
            Tuple of (List of shortest paths as lists of page IDs, BFS levels)
        """
        if start_id == target_id:
            return [[start_id]], 0

        final_paths: List[List[int]] = []

        # Forward search always starts fresh from the new start_id
        unvisited_forward: Dict[int, List[Optional[int]]] = {start_id: [None]}
        visited_forward: Dict[int, List[Optional[int]]] = {}

        # Backward search attempts to use cache for this target
        cached_state = self.backward_bfs_cache.get(target_id)
        if cached_state is not None:
            self._touch_backward_bfs(target_id)
            logger.info(f"Reusing cached backward BFS state for target_id: {target_id}.")
            visited_backward = cached_state['visited'].copy()
            unvisited_backward = cached_state['unvisited'].copy()
        else:
            logger.info(f"No cached backward BFS state for target_id: {target_id}. Starting fresh.")
            unvisited_backward = {target_id: [None]}
            visited_backward = {}

        bfs_level = 0
        while not final_paths and unvisited_forward and unvisited_backward:
            
            # Pre-check if backward expansion makes sense (before acquiring expensive lock)
            should_try_backward = self._should_expand_backward(unvisited_forward, unvisited_backward)

            if should_try_backward:
                # Try backward expansion with lock coordination
                expansion_happened = await self._try_backward_expansion(
                    target_lock, target_id, unvisited_forward, unvisited_backward, 
                    visited_backward, bfs_level
                )
                
                if expansion_happened:
                    # Successfully expanded backward, continue to intersection check
                    pass
                else:
                    # Lock holder decided forward was better, do forward expansion
                    await self._do_forward_expansion(
                        unvisited_forward, visited_forward, bfs_level
                    )
            else:
                # Forward BFS expansion
                await self._do_forward_expansion(
                    unvisited_forward, visited_forward, bfs_level
                )
            
            # Check for path completion (intersection)
            intersection_nodes = []
            if unvisited_forward:
                for page_id in unvisited_forward.keys():
                    if page_id in visited_backward or page_id in unvisited_backward:
                        intersection_nodes.append(page_id)
            if unvisited_backward:
                for page_id in unvisited_backward.keys():
                    if page_id in visited_forward or page_id in unvisited_forward:
                         intersection_nodes.append(page_id)
            
            if intersection_nodes:
                logger.debug(f"Intersection found at nodes: {intersection_nodes}")
                for meeting_node_id in intersection_nodes:
                    # Get parents leading to meeting_node_id from both directions
                    parents_in_fwd = unvisited_forward.get(meeting_node_id, visited_forward.get(meeting_node_id))
                    parents_in_bwd = unvisited_backward.get(meeting_node_id, visited_backward.get(meeting_node_id))

                    # Handle special cases where intersection is at start/target
                    if meeting_node_id == start_id and parents_in_bwd:
                         paths_from_target = await self._get_paths_recursive(parents_in_bwd, visited_backward, is_forward_path=False)
                         for p_target in paths_from_target:
                            final_paths.append([start_id] + list(reversed(p_target)))

                    elif meeting_node_id == target_id and parents_in_fwd:
                        paths_from_source = await self._get_paths_recursive(parents_in_fwd, visited_forward, is_forward_path=True)
                        for p_source in paths_from_source:
                            final_paths.append(list(p_source) + [target_id])
                    
                    # General case: intersection at an intermediate node
                    if parents_in_fwd and parents_in_bwd:
                        paths_from_source_to_meeting = await self._get_paths_recursive(
                            parents_in_fwd, 
                            visited_forward, 
                            is_forward_path=True
                        )
                        
                        paths_from_target_to_meeting = await self._get_paths_recursive(
                            parents_in_bwd,
                            visited_backward,
                            is_forward_path=False
                        )

                        for path_s in paths_from_source_to_meeting:
                            for path_t in paths_from_target_to_meeting:
                                current_full_path = list(path_s) + [meeting_node_id] + list(reversed(path_t))
                                if current_full_path not in final_paths:
                                    final_paths.append(current_full_path)
                
                if final_paths:
                    logger.debug(f"BFS complete at level {bfs_level}. Found {len(final_paths)} paths.")
                    break
            
            bfs_level += 1
     
        return final_paths, bfs_level

    def _should_expand_backward(self, unvisited_forward: Dict, unvisited_backward: Dict) -> bool:
        """Decide if backward expansion should be attempted based on frontier sizes."""
        # Handle edge cases where one frontier is empty
        if not unvisited_forward: 
            return False  # Must expand forward
        if not unvisited_backward: 
            return True   # Must expand backward
            
        # Use frontier size heuristic - see class docstring for rationale
        forward_frontier_size = len(unvisited_forward)
        backward_frontier_size = len(unvisited_backward)
        return backward_frontier_size <= forward_frontier_size

    async def _try_backward_expansion(
        self, 
        target_lock: asyncio.Lock, 
        target_id: int,
        unvisited_forward: Dict, 
        unvisited_backward: Dict,
        visited_backward: Dict,
        bfs_level: int
    ) -> bool:
        """Attempt backward expansion with lock coordination. Returns True if expansion happened."""
        async with target_lock:
            # Re-check cache after acquiring lock - another task might have expanded
            fresh_cached_state = self.backward_bfs_cache.get(target_id)
            if fresh_cached_state is not None:
                # Update our state with any new expansions that happened while we waited
                fresh_visited = fresh_cached_state['visited']
                fresh_unvisited = fresh_cached_state['unvisited']
                
                # Merge any new discoveries into our current state
                for page_id, parents in fresh_visited.items():
                    if page_id not in visited_backward:
                        visited_backward[page_id] = parents.copy()
                
                for page_id, parents in fresh_unvisited.items():
                    if page_id not in visited_backward and page_id not in unvisited_backward:
                        unvisited_backward[page_id] = parents.copy()

            # RE-EVALUATE expansion decision with current state after merging cache
            expand_backward = await self._choose_expansion_direction(unvisited_forward, unvisited_backward, bfs_level)
            
            if not expand_backward:
                logger.debug(f"BFS Level {bfs_level}: Re-evaluated to FORWARD after acquiring lock")
                return False  # Caller should do forward expansion

            # Proceed with backward expansion
            logger.debug(f"BFS Level {bfs_level}: BACKWARD expansion confirmed after lock")
            
            newly_visited_this_level: Dict[int, List[Optional[int]]] = {}
            target_page_ids_to_expand = list(unvisited_backward.keys())

            for page_id, parents in unvisited_backward.items():
                if page_id not in visited_backward:
                    visited_backward[page_id] = parents
                else:
                     for p in parents:
                        if p not in visited_backward[page_id]:
                            visited_backward[page_id].append(p)
            unvisited_backward.clear()

            # Time the database fetch operation for backward expansion
            db_start_time = time.perf_counter()
            tasks = [self._get_incoming_links(target_id_val) for target_id_val in target_page_ids_to_expand]
            results_for_all_targets = await asyncio.gather(*tasks)
            db_fetch_time = time.perf_counter() - db_start_time
            
            # Calculate metrics for backward expansion
            total_links_fetched = sum(len(links) for links in results_for_all_targets)
            logger.debug(
                f"  Backward DB fetch: {len(target_page_ids_to_expand)} pages, "
                f"{total_links_fetched} links, {db_fetch_time*1000:.1f}ms"
            )

            for i, current_target_id in enumerate(target_page_ids_to_expand):
                source_ids_linking_to_target = results_for_all_targets[i]
                for prev_id in source_ids_linking_to_target:
                    if prev_id not in visited_backward:
                        if prev_id not in newly_visited_this_level:
                            newly_visited_this_level[prev_id] = [current_target_id]
                        else:
                            newly_visited_this_level[prev_id].append(current_target_id)
            
            unvisited_backward.update(newly_visited_this_level)
            
            # Update the shared cache with our expanded state
            if visited_backward or unvisited_backward:
                self.backward_bfs_cache[target_id] = {
                    'visited': visited_backward.copy(),
                    'unvisited': unvisited_backward.copy()
                }
                self._touch_backward_bfs(target_id)
                logger.info(
                    f"Cached backward BFS state for target_id: {target_id}. "
                    f"Visited: {len(visited_backward)}, Unvisited: {len(unvisited_backward)}"
                )
            # Log expansion results for backward direction
            logger.debug(f"  Backward expansion result: {len(newly_visited_this_level)} new pages discovered")
            return True

    async def _do_forward_expansion(
        self, 
        unvisited_forward: Dict, 
        visited_forward: Dict,
        bfs_level: int
    ):
        """Perform forward BFS expansion (no coordination needed)."""
        logger.debug(f"BFS Level {bfs_level}: FORWARD expansion")
        
        newly_visited_this_level: Dict[int, List[Optional[int]]] = {}
        source_page_ids_to_expand = list(unvisited_forward.keys())
        
        # Move current unvisited_forward to visited_forward
        for page_id, parents in unvisited_forward.items():
            if page_id not in visited_forward:
                visited_forward[page_id] = parents
            else:
                for p in parents:
                    if p not in visited_forward[page_id]:
                        visited_forward[page_id].append(p)
        unvisited_forward.clear()

        # Fetch outgoing links using cached method
        db_start_time = time.perf_counter()
        db_fetch_tasks = [self._get_outgoing_links(src_id) for src_id in source_page_ids_to_expand]
        results_for_all_sources = await asyncio.gather(*db_fetch_tasks)
        db_fetch_time = time.perf_counter() - db_start_time
        
        # Calculate metrics for this expansion
        total_links_fetched = sum(len(links) for links in results_for_all_sources)
        
        logger.debug(
            f"  Forward DB fetch: {len(source_page_ids_to_expand)} pages, "
            f"{total_links_fetched} links, {db_fetch_time*1000:.1f}ms"
        )
        
        for i, src_id in enumerate(source_page_ids_to_expand):
            target_ids_from_src = results_for_all_sources[i]
            for next_id in target_ids_from_src:
                if next_id not in visited_forward:
                    if next_id not in newly_visited_this_level:
                        newly_visited_this_level[next_id] = [src_id]
                    else:
                        newly_visited_this_level[next_id].append(src_id)
        
        unvisited_forward.update(newly_visited_this_level)
        
        # Log expansion results for forward direction
        logger.debug(f"  Forward expansion result: {len(newly_visited_this_level)} new pages discovered")

    async def _choose_expansion_direction(self, unvisited_forward: Dict, unvisited_backward: Dict, bfs_level: int) -> bool:
        """Choose expansion direction. Returns True for backward, False for forward."""
        # Handle edge cases where one frontier is empty
        if not unvisited_forward: 
            return False  # Must expand forward
        if not unvisited_backward: 
            return True   # Must expand backward
            
        direction_timing_start = time.perf_counter()
        
        # Fast frontier size comparison for expansion direction decision
        # ALTERNATIVE: Could count actual links per frontier, 
        # but counting links for the decision costs on the order of just expanding both directions
        forward_frontier_size = len(unvisited_forward)
        backward_frontier_size = len(unvisited_backward)
        expand_backward = backward_frontier_size <= forward_frontier_size
        
        direction_timing_end = time.perf_counter()
        logger.debug(
            f"  Direction choice (frontier size): {(direction_timing_end - direction_timing_start)*1000:.1f}ms "
            f"(forward: {forward_frontier_size} pages, backward: {backward_frontier_size} pages) -> {'BACKWARD' if expand_backward else 'FORWARD'}"
        )

        return expand_backward

    async def shutdown(self):
        """Gracefully shutdown the solver and cleanup tasks."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass


# Global instance for easy access
wiki_task_solver = WikiTaskSolver() 