import logging
from typing import Dict, Any

from wiki_arena import GameEvent
from backend.websockets.game_hub import websocket_manager

logger = logging.getLogger(__name__)

class WebSocketHandler:
    """
    Handles WebSocket broadcasting in response to game events.
    
    This handler is stateless and purely reactive - it receives events
    and broadcasts them to connected WebSocket clients.
    """
    
    async def handle_move_completed(self, event: GameEvent):
        """Handle move_completed events by broadcasting to WebSocket clients."""
        logger.debug(f"Broadcasting move_completed for game {event.game_id}")
        
        # Extract data from event
        move_data = event.data.get("move")
        game_state_data = event.data.get("game_state")
        is_game_over = event.data.get("is_game_over", False)
        
        # Create WebSocket message
        message = {
            "type": "GAME_MOVE_COMPLETED",
            "game_id": event.game_id,
            "move": {
                "step": move_data.step,
                "from_page_title": move_data.from_page_title,
                "to_page_title": move_data.to_page_title,
                "timestamp": None,  # Move model doesn't have timestamp (MoveMetrics does tho)
                "model_response": move_data.model_response
            },
            "game_over": is_game_over,
            "current_page": game_state_data.current_page,
            "steps": game_state_data.steps,
            "status": game_state_data.status.value
        }
        
        # Broadcast to all clients watching this game
        await websocket_manager.broadcast_to_game(event.game_id, message)
        
        logger.info(f"Broadcasted move to {websocket_manager.get_connection_count(event.game_id)} clients for game {event.game_id}")
    
    async def handle_game_started(self, event: GameEvent):
        """Handle game_started events by broadcasting to WebSocket clients."""
        logger.debug(f"Broadcasting game_started for game {event.game_id}")
        
        game_state_data = event.data.get("game_state")
        
        message = {
            "type": "GAME_STARTED",
            "game_id": event.game_id,
            "start_page": game_state_data.config.start_page_title,
            "target_page": game_state_data.config.target_page_title,
            "status": game_state_data.status.value,
            "steps": game_state_data.steps
        }
        
        await websocket_manager.broadcast_to_game(event.game_id, message)
        logger.info(f"Broadcasted game_started to clients for game {event.game_id}")
    
    async def handle_game_ended(self, event: GameEvent):
        """Handle game_ended events by broadcasting final status to WebSocket clients."""
        logger.debug(f"Broadcasting game_ended for game {event.game_id}")
        
        game_state_data = event.data.get("game_state")
        
        message = {
            "type": "GAME_ENDED",
            "game_id": event.game_id,
            "final_status": game_state_data.status.value,
            "total_steps": game_state_data.steps,
            "error_message": getattr(game_state_data, 'error_message', None)
        }
        
        await websocket_manager.broadcast_to_game(event.game_id, message)
        logger.info(f"Broadcasted game_ended to clients for game {event.game_id}")
    
    async def handle_optimal_paths_found(self, event: GameEvent):
        """Handle task solver completion by broadcasting updated optimal paths."""
        logger.debug(f"Broadcasting task solver results for game {event.game_id}")
        
        optimal_paths = event.data.get("optimal_paths", [])
        optimal_path_length = event.data.get("optimal_path_length", -1)
        move_quality = event.data.get("move_quality")
        
        message = {
            "type": "OPTIMAL_PATHS_UPDATED",
            "game_id": event.game_id,
            "optimal_paths": optimal_paths,
            "optimal_path_length": optimal_path_length,
            "move_quality": move_quality # TODO(hunter): the frontend should calculate this
        }
        
        await websocket_manager.broadcast_to_game(event.game_id, message)
        logger.debug(f"Broadcasted task solver to clients for game {event.game_id}") 