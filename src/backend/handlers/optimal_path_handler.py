import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from wiki_arena import GameEvent, EventBus
from wiki_arena.solver import WikiTaskSolver

logger = logging.getLogger(__name__)

class OptimalPathHandler:
    """
    Handles task solver in response to game events.
    
    This handler triggers task solver in parallel (non-blocking) when moves
    are completed and publishes the results as new events.
    """
    
    def __init__(self, event_bus: EventBus, solver: WikiTaskSolver): 
        self.event_bus = event_bus
        self.solver = solver
        # Cache for latest solver results per game # TODO(hunter): this should be per task
        # why is this only caching the initial solve? (it's for the connection_initialized event)
        # shouldn't we be caching all start pages for the same task (target page)? 
        # Dict[target, Dict[start, solver_result]]
        self.cache: Dict[str, Dict[str, Any]] = {}
    
    # TODO(hunter): do we still need this once we fix game init?
    def get_cached_results(self, game_id: str) -> Optional[Dict[str, Any]]:
        """Get cached solver results for a game."""
        return self.cache.get(game_id)

    async def handle_move_completed(self, event: GameEvent):
        """Handle move_completed events by triggering parallel task solver."""
        logger.debug(f"Triggering task solver for game {event.game_id}")
        
        # Extract necessary data
        game_state = event.data.get("game_state")
        move = event.data.get("move")
        
        if not game_state or not move:
            logger.warning(f"Missing game_state or move data in event for game {event.game_id}")
            return
        
        # Start task solver in background (non-blocking)
        asyncio.create_task(self._find_optimal_paths(
            event.game_id,
            game_state.current_page.title,
            game_state.config.target_page_title,
        ))
    
    
    async def handle_task_selected(self, event: GameEvent):
        """Handle task_selected events by solving the task once for all games."""
        # TODO(hunter): we may need to change GameEvent
        logger.debug(f"Solving task for task_id: {event.game_id}")  # game_id is actually task_id for task events
        
        task = event.data.get("task")
        task_id = event.data.get("task_id")
        game_ids = event.data.get("game_ids", [])
        
        if not task or not task_id:
            logger.warning(f"Missing task data in task_selected event")
            return
        
        # Solve the task once
        try:
            logger.info(f"Solving task {task_id}: {task.start_page_title} -> {task.target_page_title}")
            
            solver_result = await self.solver.find_shortest_path(
                task.start_page_title, 
                task.target_page_title
            )
            
            # Cache results for all games in this task
            cache_data = {
                "optimal_paths": solver_result.paths,
                "optimal_path_length": solver_result.path_length,
                "from_page_title": task.start_page_title,
                "to_page_title": task.target_page_title,
                "computation_time_ms": solver_result.computation_time_ms,
                "is_initial": True,
                "timestamp": datetime.now().isoformat()
            }
            
            # Cache for all games in this task
            for game_id in game_ids:
                self.cache[game_id] = cache_data.copy()
            
            # Emit task_solved event
            await self.event_bus.publish(GameEvent(
                type="task_solved",
                game_id=task_id,  # Use task_id as game_id for task-level events
                data={
                    "task_id": task_id,
                    "game_ids": game_ids,
                    "optimal_paths": solver_result.paths,
                    "optimal_path_length": solver_result.path_length,
                    "from_page_title": task.start_page_title,
                    "to_page_title": task.target_page_title,
                    "computation_time_ms": solver_result.computation_time_ms
                }
            ))
            
            logger.info(
                f"Task {task_id} solved: "
                f"{task.start_page_title} -> {task.target_page_title} "
                f"(length: {solver_result.path_length}, "
                f"time: {solver_result.computation_time_ms:.1f}ms, "
                f"games: {len(game_ids)})"
            )
            
        except Exception as e:
            logger.error(f"Failed to solve task {task_id}: {e}", exc_info=True)
            
            # Emit failure event
            await self.event_bus.publish(GameEvent(
                type="task_solve_failed",
                game_id=task_id,
                data={
                    "error": str(e),
                    "task_id": task_id,
                    "start_page": task.start_page_title,
                    "target_page": task.target_page_title
                }
            ))
    
    async def _find_optimal_paths(
        self, 
        game_id: str, 
        from_page: str, 
        to_page: str, 
        is_initial: bool = False
    ):
        """
        Perform task solver asynchronously and emit results.
        
        This method runs in the background and doesn't block game execution.
        For initial path calculations, emits 'initial_paths_ready' event.
        For subsequent moves, emits 'optimal_paths_found' event.
        """
        try:
            logger.debug(f"Analyzing path: {from_page} -> {to_page} for game {game_id} (initial: {is_initial})")
            
            solver_result = await self.solver.find_shortest_path(from_page, to_page)
            
            # Cache the results
            self.cache[game_id] = {
                "optimal_paths": solver_result.paths,
                "optimal_path_length": solver_result.path_length,
                "from_page_title": from_page,
                "to_page_title": to_page,
                "computation_time_ms": solver_result.computation_time_ms,
                "is_initial": is_initial,
                "timestamp": datetime.now().isoformat()
            }
            # TODO(hunter): why do we do this twice? 
            # Prepare event data
            event_data = {
                "game_id": game_id,
                "from_page_title": from_page,
                "to_page_title": to_page,
                "optimal_paths": solver_result.paths,
                "optimal_path_length": solver_result.path_length,
                "computation_time_ms": solver_result.computation_time_ms,
                "is_initial": is_initial
            }
            
            # Emit different events based on whether this is initial or subsequent analysis
            if is_initial:
                await self.event_bus.publish(GameEvent(
                    type="initial_paths_ready",
                    game_id=game_id,
                    data=event_data
                ))
                logger.info(
                    f"Initial paths ready for game {game_id}: "
                    f"{from_page} -> {to_page} "
                    f"(length: {solver_result.path_length}, "
                    f"time: {solver_result.computation_time_ms:.1f}ms)"
                )
            else:
                await self.event_bus.publish(GameEvent(
                    type="optimal_paths_found",
                    game_id=game_id,
                    data=event_data
                ))
                logger.info(
                    f"Optimal paths updated for game {game_id}: "
                    f"{from_page} -> {to_page} "
                    f"(length: {solver_result.path_length}, "
                    f"time: {solver_result.computation_time_ms:.1f}ms)"
                )
            
        except Exception as e:
            logger.error(f"task solver failed for game {game_id}: {e}", exc_info=True)
            
            # Emit failure event
            await self.event_bus.publish(GameEvent(
                type="path_analysis_failed", # TODO(hunter): nobody subscribes to this event
                game_id=game_id,
                data={
                    "error": str(e),
                    "from_page_title": from_page,
                    "to_page_title": to_page,
                    "is_initial": is_initial
                }
            )) 