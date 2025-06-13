"""
WikiTaskSolver - Service for finding shortest paths between Wikipedia pages.

This service uses bidirectional BFS with intelligent caching to efficiently find
optimal paths between Wikipedia pages using the static wiki graph database.
"""

import asyncio
import time
import logging
from typing import List, Dict, Set, Optional, Tuple
from collections import deque

from .static_db import StaticSolverDB
from .models import SolverResponse

logger = logging.getLogger(__name__)


class WikiTaskSolver:
    """Service for finding shortest paths between Wikipedia pages using bidirectional BFS."""
    
    def __init__(self, db: Optional[StaticSolverDB] = None):
        """
        Initialize the task solver.
        
        Args:
            db: StaticSolverDB instance. If None, uses the global static_solver_db.
        """
        if db is None:
            from .static_db import static_solver_db
            self.db = static_solver_db
        else:
            self.db = db
            
        # Cache for target-specific optimization
        self.active_target_id: Optional[int] = None
        # Cache for backward search state {visited: ..., unvisited: ...} for the active_target_id
        self.cached_backward_bfs_state: Optional[Dict[str, Dict[int, List[Optional[int]]]]] = None
        # Cache for forward expansion outgoing links: {source_node_id: [link_ids]} for the active_target_id
        self.cached_forward_expansion_links: Dict[int, List[int]] = {}
        
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
        
        # Get page IDs
        start_id = await self.db.get_page_id(start_page)
        target_id = await self.db.get_page_id(target_page)
        
        if start_id is None:
            raise ValueError(f"Start page '{start_page}' not found in database.")
        if target_id is None:
            raise ValueError(f"Target page '{target_page}' not found in database.")
        
        # --- Cache Management based on target_id ---
        if self.active_target_id != target_id:
            logger.info(f"Target ID changed from {self.active_target_id} to {target_id}. Resetting caches.")
            self.active_target_id = target_id
            self.cached_backward_bfs_state = None
            self.cached_forward_expansion_links.clear()
        else:
            logger.info(f"Continuing with active target ID: {self.active_target_id}. Caches may be reused.")

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
        paths_as_ids = await self._bidirectional_bfs(start_id, target_id)
        
        if not paths_as_ids:
            raise ValueError(f"No path found between '{start_page}' and '{target_page}'.")

        # Convert paths of IDs to paths of titles
        all_paths_as_titles: List[List[str]] = []
        for id_path in paths_as_ids:
            title_path = await self.db.batch_get_page_titles(id_path)
            # Ensure no None titles in path
            if any(t is None for t in title_path):
                logger.error(f"Path {id_path} contained an ID with no title: {title_path}")
                continue 
            all_paths_as_titles.append(title_path)

        if not all_paths_as_titles:
             raise ValueError(f"Path IDs found but title conversion failed for '{start_page}' -> '{target_page}'.")

        actual_computation_time_ms = (time.time() - actual_computation_start_time) * 1000
        
        logger.info(f"Path found for {start_page} -> {target_page}. Path length: {len(all_paths_as_titles[0])-1}. Paths found: {len(all_paths_as_titles)}. Took {actual_computation_time_ms:.2f} ms.")

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

    async def _bidirectional_bfs(self, start_id: int, target_id: int) -> List[List[int]]:
        """
        Bidirectional BFS implementation with caching support.
        
        Args:
            start_id: Starting page ID
            target_id: Target page ID
            
        Returns:
            List of shortest paths as lists of page IDs
        """
        if start_id == target_id:
            return [[start_id]]

        final_paths: List[List[int]] = []

        # Forward search always starts fresh from the new start_id
        unvisited_forward: Dict[int, List[Optional[int]]] = {start_id: [None]}
        visited_forward: Dict[int, List[Optional[int]]] = {}

        # Backward search attempts to use cache if active_target_id matches target_id
        if self.cached_backward_bfs_state is not None and self.active_target_id == target_id:
            logger.info(f"Reusing cached backward BFS state for target_id: {target_id}.")
            visited_backward = self.cached_backward_bfs_state['visited'].copy()
            unvisited_backward = self.cached_backward_bfs_state['unvisited'].copy()
        else:
            logger.info(f"No valid cache for backward BFS state for target_id: {target_id}. Starting fresh.")
            unvisited_backward = {target_id: [None]}
            visited_backward = {}

        while not final_paths and unvisited_forward and unvisited_backward:
            
            # Choose direction based on link counts
            forward_links_count = await self.db.fetch_outgoing_links_count(list(unvisited_forward.keys()))
            backward_links_count = await self.db.fetch_incoming_links_count(list(unvisited_backward.keys()))

            # Determine search direction
            expand_forward = forward_links_count <= backward_links_count
            if not unvisited_forward: 
                expand_forward = False
            if not unvisited_backward: 
                expand_forward = True

            if expand_forward:
                # Forward BFS expansion
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

                # Fetch outgoing links with caching
                results_for_all_sources = [[] for _ in source_page_ids_to_expand]
                indices_and_src_ids_for_db_fetch = []

                for original_idx, src_id_to_check in enumerate(source_page_ids_to_expand):
                    cached_links = self.cached_forward_expansion_links.get(src_id_to_check)
                    
                    if cached_links is not None:
                        results_for_all_sources[original_idx] = cached_links
                        logger.debug(f"Forward link cache HIT for {src_id_to_check}")
                    else:
                        indices_and_src_ids_for_db_fetch.append((original_idx, src_id_to_check))
                        logger.debug(f"Forward link cache MISS for {src_id_to_check}")
                
                if indices_and_src_ids_for_db_fetch:
                    src_ids_to_fetch_from_db = [item[1] for item in indices_and_src_ids_for_db_fetch]
                    db_fetch_tasks = [self.db.get_outgoing_links(s_id) for s_id in src_ids_to_fetch_from_db]
                    fetched_links_results_list = await asyncio.gather(*db_fetch_tasks)

                    for i, (original_idx, s_id_fetched) in enumerate(indices_and_src_ids_for_db_fetch):
                        actual_links = fetched_links_results_list[i]
                        self.cached_forward_expansion_links[s_id_fetched] = actual_links
                        results_for_all_sources[original_idx] = actual_links
                
                for i, src_id in enumerate(source_page_ids_to_expand):
                    target_ids_from_src = results_for_all_sources[i]
                    for next_id in target_ids_from_src:
                        if next_id not in visited_forward:
                            if next_id not in newly_visited_this_level:
                                newly_visited_this_level[next_id] = [src_id]
                            else:
                                newly_visited_this_level[next_id].append(src_id)
                
                unvisited_forward = newly_visited_this_level

            else:
                # Backward BFS expansion
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

                tasks = [self.db.get_incoming_links(target_id_val) for target_id_val in target_page_ids_to_expand]
                results_for_all_targets = await asyncio.gather(*tasks)

                for i, current_target_id in enumerate(target_page_ids_to_expand):
                    source_ids_linking_to_target = results_for_all_targets[i]
                    for prev_id in source_ids_linking_to_target:
                        if prev_id not in visited_backward:
                            if prev_id not in newly_visited_this_level:
                                newly_visited_this_level[prev_id] = [current_target_id]
                            else:
                                newly_visited_this_level[prev_id].append(current_target_id)
                
                unvisited_backward = newly_visited_this_level

            # Check for path completion (intersection)
            intersection_nodes = []
            if expand_forward:
                for page_id in unvisited_forward.keys():
                    if page_id in visited_backward or page_id in unvisited_backward:
                        intersection_nodes.append(page_id)
            else:
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
                    logger.debug(f"BFS complete. Found {len(final_paths)} paths.")
                    break

        # Cache backward search state if it was computed fresh for this target
        if self.active_target_id == target_id and self.cached_backward_bfs_state is None and (visited_backward or unvisited_backward):
            self.cached_backward_bfs_state = {
                'visited': visited_backward.copy(), 
                'unvisited': unvisited_backward.copy()
            }
            logger.info(f"Cached backward BFS state for active target_id: {self.active_target_id}. Visited: {len(visited_backward)}, Unvisited: {len(unvisited_backward)}")
            
        return final_paths


# Global instance for easy access
wiki_task_solver = WikiTaskSolver() 