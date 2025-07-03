from typing import Dict, Any, Optional
from datetime import datetime
import logging

from backend.coordinators.game_coordinator import GameCoordinator
from backend.handlers.optimal_path_handler import OptimalPathHandler

logger = logging.getLogger(__name__)

class StateCollector:
    """
    Collects complete state from multiple sources for WebSocket connections.
    
    This utility gathers all available information about a game:
    - Core game state from GameCoordinator
    - Cached solver results from OptimalPathHandler
    """
    
    def __init__(self, game_coordinator: GameCoordinator, optimal_path_handler: OptimalPathHandler):
        self.game_coordinator = game_coordinator
        self.optimal_path_handler = optimal_path_handler
    
    async def get_complete_state(self, game_id: str) -> Dict[str, Any]:
        """
        Get complete state for a game including all available data.
        
        Returns:
            Dict containing:
            - game: Core game state (if available)
            - solver: Cached solver results (if available) 
        """
        logger.debug(f"Collecting complete state for game {game_id}")
        
        # Get core game state
        game_state = await self.game_coordinator.get_game_state(game_id)
        
        # Get all cached solver results for this game
        solver_results = self.optimal_path_handler.get_cached_results(game_id)
        
        complete_state = {
            "game": game_state.model_dump() if game_state else None,
            "solver_results": solver_results,
        }
        
        logger.debug(f"Complete state collected for game {game_id}: "
                    f"game={'present' if complete_state['game'] else 'missing'}, "
                    f"solver_results={len(complete_state['solver_results'])} results")
        
        return complete_state 