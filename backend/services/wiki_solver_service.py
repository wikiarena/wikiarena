import asyncio
import time
import logging
from typing import List, Dict, Set, Optional, Tuple
from collections import deque
from datetime import datetime

from backend.services.wiki_db_service import wiki_db
from backend.models.solver_models import SolverResponse

logger = logging.getLogger(__name__)

class WikiPathSolver:
    """Service for finding shortest paths between Wikipedia pages using sdow BFS logic."""
    
    def __init__(self):
        # Caching removed for now, will be re-evaluated post-testing.
        pass
        
    async def initialize(self):
        """Initialize the solver (database initialization is handled by wiki_db)."""
        logger.info("Wiki path solver initialized and using pre-existing sdow database.")
    
    async def find_shortest_path(self, start_page: str, target_page: str) -> SolverResponse:
        """Find the shortest path(s) between two Wikipedia pages."""
        request_start_time = time.time()
        
        # Get page IDs
        start_id = await wiki_db.get_page_id(start_page)
        target_id = await wiki_db.get_page_id(target_page)
        
        if start_id is None:
            raise ValueError(f"Start page '{start_page}' not found in database.")
        if target_id is None:
            raise ValueError(f"Target page '{target_page}' not found in database.")
        
        if start_page == target_page: # Or start_id == target_id
            path_titles = [[start_page]]
            computation_time_ms = (time.time() - request_start_time) * 1000
            return SolverResponse(
                paths=path_titles, path_length=0,
                computation_time_ms=computation_time_ms, from_cache=False
            )
        
        # Perform BFS using adapted sdow logic
        actual_computation_start_time = time.time()
        paths_as_ids = await self._adapted_sdow_bfs(start_id, target_id)
        
        if not paths_as_ids:
            # No path found by BFS, raise an error as per original sdow behavior implicitly
            # and explicit behavior of previous solver.
            raise ValueError(f"No path found between '{start_page}' and '{target_page}'.")

        # Convert paths of IDs to paths of titles
        all_paths_as_titles: List[List[str]] = []
        for id_path in paths_as_ids:
            # batch_get_page_titles returns titles in order, handles None if an ID is bad (should not happen here)
            # It also ensures readable titles.
            title_path = await wiki_db.batch_get_page_titles(id_path)
            # Ensure no None titles in path, which would indicate an issue
            if any(t is None for t in title_path):
                logger.error(f"Path {id_path} contained an ID with no title: {title_path}")
                # Skip this problematic path or raise error
                continue 
            all_paths_as_titles.append(title_path)

        if not all_paths_as_titles:
             raise ValueError(f"Path IDs found but title conversion failed for '{start_page}' -> '{target_page}'.")

        actual_computation_time_ms = (time.time() - actual_computation_start_time) * 1000
        
        logger.info(f"Path found for {start_page} -> {target_page}. Path length: {len(all_paths_as_titles[0])-1}. Paths found: {len(all_paths_as_titles)}. Took {actual_computation_time_ms:.2f} ms.")

        return SolverResponse(
            paths=all_paths_as_titles,
            path_length=len(all_paths_as_titles[0]) - 1,
            computation_time_ms=actual_computation_time_ms,
            from_cache=False
        )

    async def _get_paths_recursive(
        self, 
        page_ids: List[Optional[int]], # List of parent IDs, None signifies source/target
        visited_dict: Dict[int, List[Optional[int]]], # e.g. visited_forward or visited_backward
        is_forward_path: bool # True if reconstructing from source, False if from target (needs reversal)
    ) -> List[List[int]]:
        """
        Recursively reconstructs paths from a list of page IDs to the BFS origin.
        Adapted from sdow's get_paths.
        `page_ids` are the parents of the node leading to the intersection.
        `visited_dict` is the map from child_id to list_of_parent_ids for that search direction.
        Returns a list of paths, where each path starts from the BFS origin and ends at one of the `page_ids`' children.
        """
        paths = []
        for page_id in page_ids:
            if page_id is None: # Base case: reached the origin of this BFS direction
                paths.append([])
            else:
                # Parents of `page_id` in this BFS direction
                parent_ids_of_current_page_id = visited_dict.get(page_id)
                if parent_ids_of_current_page_id is None:
                    # Should not happen if page_id came from visited_dict keys
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

    async def _adapted_sdow_bfs(self, start_id: int, target_id: int) -> List[List[int]]:
        """
        Adapted asynchronous version of the bi-directional BFS from database/sdow/breadth_first_search.py.
        Returns a list of shortest paths, each path being a list of page IDs.
        """
        if start_id == target_id: # Should be handled by caller, but as a safeguard
            return [[start_id]]

        final_paths: List[List[int]] = []

        # page_id -> list of parent_ids (None signifies origin)
        unvisited_forward: Dict[int, List[Optional[int]]] = {start_id: [None]}
        unvisited_backward: Dict[int, List[Optional[int]]] = {target_id: [None]}

        visited_forward: Dict[int, List[Optional[int]]] = {}
        visited_backward: Dict[int, List[Optional[int]]] = {}
        
        # The sdow BFS doesn't use explicit depth counters for termination in the same way the old one did.
        # It terminates when an intersection is found and processed, or queues are empty.
        # Max depth for safety can be added if needed.

        while not final_paths and unvisited_forward and unvisited_backward:
            
            # Choose direction (sdow compares estimated link counts)
            # For async, we might expand one level from each if not intersecting, or stick to sdow's choice.
            # Let's stick to sdow's count-based decision for now.
            # Note: get_page_ids in db service takes list of titles, here we have list of IDs.
            forward_links_count = await wiki_db.fetch_outgoing_links_count(list(unvisited_forward.keys()))
            backward_links_count = await wiki_db.fetch_incoming_links_count(list(unvisited_backward.keys()))

            # --- Determine search direction ---
            expand_forward = forward_links_count <= backward_links_count
            if not unvisited_forward: expand_forward = False # Must expand backward if forward is empty
            if not unvisited_backward: expand_forward = True # Must expand forward if backward is empty


            if expand_forward:
                # --- FORWARD BFS ---
                newly_visited_this_level: Dict[int, List[Optional[int]]] = {}
                
                # Process all nodes currently at the fringe of the forward search
                # Keys of unvisited_forward are the current fringe
                source_page_ids_to_expand = list(unvisited_forward.keys())
                
                # Move current unvisited_forward to visited_forward
                for page_id, parents in unvisited_forward.items():
                    if page_id not in visited_forward:
                        visited_forward[page_id] = parents
                    else: # page already visited, append parents if different (sdow appends)
                        for p in parents:
                            if p not in visited_forward[page_id]:
                                visited_forward[page_id].append(p)
                
                unvisited_forward.clear()

                # Get all outgoing links for the source_page_ids_to_expand
                # This needs to be efficient. Consider a batch get_outgoing_links if possible,
                # or iterate. Current wiki_db.get_outgoing_links is per ID.
                tasks = [wiki_db.get_outgoing_links(src_id) for src_id in source_page_ids_to_expand]
                results_for_all_sources = await asyncio.gather(*tasks)
                
                for i, src_id in enumerate(source_page_ids_to_expand):
                    target_ids_from_src = results_for_all_sources[i]
                    for next_id in target_ids_from_src:
                        if next_id not in visited_forward: # Not visited by forward search yet
                            if next_id not in newly_visited_this_level:
                                newly_visited_this_level[next_id] = [src_id]
                            else:
                                newly_visited_this_level[next_id].append(src_id)
                
                unvisited_forward = newly_visited_this_level

            else: # expand_backward
                # --- BACKWARD BFS ---
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

                tasks = [wiki_db.get_incoming_links(target_id_val) for target_id_val in target_page_ids_to_expand]
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

            # --- CHECK FOR PATH COMPLETION ---
            # Intersection is any page_id present in unvisited_forward keys and unvisited_backward keys
            # OR a page_id in unvisited_forward keys that is already in visited_backward keys
            # OR a page_id in unvisited_backward keys that is already in visited_forward keys
            
            # sdow checks intersection of unvisited_forward with (unvisited_backward + visited_backward)
            # and unvisited_backward with (unvisited_forward + visited_forward)
            # The original sdow code checks for intersection *after* one direction has expanded.
            # Let's check for intersection using the newly populated unvisited set against the *other direction's* total visited set.

            intersection_nodes = []
            if expand_forward: # Forward just expanded, check unvisited_forward against all backward visited
                # unvisited_forward now contains the *new* fringe from forward expansion
                for page_id in unvisited_forward.keys():
                    if page_id in visited_backward or page_id in unvisited_backward: # unvisited_backward is the fringe of backward
                        intersection_nodes.append(page_id)
            else: # Backward just expanded, check unvisited_backward against all forward visited
                # unvisited_backward now contains the *new* fringe from backward expansion
                for page_id in unvisited_backward.keys():
                    if page_id in visited_forward or page_id in unvisited_forward:
                         intersection_nodes.append(page_id)
            
            if intersection_nodes:
                logger.debug(f"Intersection found at nodes: {intersection_nodes}")
                for meeting_node_id in intersection_nodes:
                    # Parents leading to meeting_node_id from forward search
                    parents_in_fwd = unvisited_forward.get(meeting_node_id, visited_forward.get(meeting_node_id))

                    # Parents leading to meeting_node_id from backward search
                    # If meeting_node_id is in unvisited_backward, its parents are in unvisited_backward[meeting_node_id]
                    # If meeting_node_id is in visited_backward, its parents are in visited_backward[meeting_node_id]
                    parents_in_bwd = unvisited_backward.get(meeting_node_id, visited_backward.get(meeting_node_id))

                    if parents_in_fwd is None or parents_in_bwd is None:
                        # This implies meeting_node_id itself is start_id or target_id and the other search met it directly.
                        # Or an error in logic. The original sdow's get_paths handles [None] for origins.
                        # If meeting_node_id is start_id, parents_in_fwd would be [None].
                        # If meeting_node_id is target_id, parents_in_bwd would be [None].
                        if meeting_node_id == start_id and parents_in_bwd: # Path from target to start
                             paths_from_target = await self._get_paths_recursive(parents_in_bwd, visited_backward, is_forward_path=False)
                             for p_target in paths_from_target:
                                final_paths.append([start_id] + list(reversed(p_target)))

                        elif meeting_node_id == target_id and parents_in_fwd: # Path from start to target
                            paths_from_source = await self._get_paths_recursive(parents_in_fwd, visited_forward, is_forward_path=True)
                            for p_source in paths_from_source:
                                final_paths.append(list(p_source) + [target_id])
                        else: # Potentially more complex intersection
                             # This block needs to handle when intersection happens AT start/target itself
                            pass # Covered by the general case below if parents_in_fwd/bwd are correctly retrieved
                    
                    # General case: intersection at a node that is not start/target directly
                    # Reconstruct paths from source to meeting_node_id
                    # `visited_forward` contains the parent pointers for the forward search.
                    # `unvisited_forward` contains parents for the current fringe.
                    # The parents for meeting_node_id in the forward search are in `unvisited_forward[meeting_node_id]`
                    # or `visited_forward[meeting_node_id]` if it was visited in an earlier forward step.
                    
                    # If meeting_node_id was just added to unvisited_forward, its parents are unvisited_forward[meeting_node_id]
                    # otherwise, they are in visited_forward[meeting_node_id]
                    paths_from_source_to_meeting = await self._get_paths_recursive(
                        unvisited_forward.get(meeting_node_id, visited_forward.get(meeting_node_id, [])), # Get parents leading to meeting_node
                        visited_forward, 
                        is_forward_path=True
                    )
                    
                    # Reconstruct paths from target to meeting_node_id (these will be reversed)
                    paths_from_target_to_meeting = await self._get_paths_recursive(
                        unvisited_backward.get(meeting_node_id, visited_backward.get(meeting_node_id, [])), # Get parents leading to meeting_node
                        visited_backward,
                        is_forward_path=False # Will be reversed by helper if needed, or here
                    )

                    for path_s in paths_from_source_to_meeting:
                        for path_t in paths_from_target_to_meeting:
                            # path_s ends just before meeting_node_id
                            # path_t ends just before meeting_node_id (coming from target)
                            # Complete path: path_s + [meeting_node_id] + reversed(path_t)
                            current_full_path = list(path_s) + [meeting_node_id] + list(reversed(path_t))
                            if current_full_path not in final_paths: # sdow had a TODO for duplicates
                                final_paths.append(current_full_path)
                
                if final_paths: # If any path is found, BFS for shortest paths is complete.
                    logger.debug(f"BFS complete. Found {len(final_paths)} paths.")
                    break # Exit while loop

        return final_paths

# Global instance
wiki_solver = WikiPathSolver() 