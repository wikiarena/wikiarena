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

    async def handle_task_solved(self, event: GameEvent):
        """Handle task_solved events by broadcasting optimal path update for each game's WebSocket clients."""
        logger.debug(f"Broadcasting task_solved for game {event.game_id}")
        
        optimal_paths = event.data.get("shortest_paths", [])
        optimal_path_length = event.data.get("shortest_path_length", -1)
        from_page_title = event.data.get("from_page_title")
        to_page_title = event.data.get("to_page_title")

        # broadcast same event to all games 
        for game_id in event.data.get("game_ids", []):
            message = {
                "type": "OPTIMAL_PATHS_UPDATED",
                "game_id": game_id,
                "optimal_paths": optimal_paths,
                "optimal_path_length": optimal_path_length,
                "from_page_title": from_page_title,
                "to_page_title": to_page_title,
            }
            
            await websocket_manager.broadcast_to_game(game_id, message)
            logger.debug(f"Broadcasted task solver to clients for game {game_id}")
    
    async def handle_shortest_paths_found(self, event: GameEvent):
        """Handle task solver completion by broadcasting updated optimal paths."""
        logger.debug(f"Broadcasting task solver results for game {event.game_id}")
        
        message = {
            "type": "OPTIMAL_PATHS_UPDATED",
            "game_id": event.game_id,
            "optimal_paths": event.data.get("shortest_paths", []),
            "optimal_path_length": event.data.get("shortest_path_length", -1),
            "from_page_title": event.data.get("from_page_title"),
            "to_page_title": event.data.get("to_page_title"),
        }
        
        await websocket_manager.broadcast_to_game(event.game_id, message)
        logger.debug(f"Broadcasted task solver to clients for game {event.game_id}")

    async def handle_move_completed(self, event: GameEvent):
        """Handle move_completed events by broadcasting to WebSocket clients."""
        logger.debug(f"Broadcasting move_completed for game {event.game_id}")
        
        # Extract data from event
        move_data = event.data.get("move")
        game_state_data = event.data.get("game_state")
        
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
            "current_page": game_state_data.current_page,
            "steps": game_state_data.steps,
            "status": game_state_data.status.value
        }
        
        # Broadcast to all clients watching this game
        await websocket_manager.broadcast_to_game(event.game_id, message)
        
        logger.info(f"Broadcasted move to {websocket_manager.get_connection_count(event.game_id)} clients for game {event.game_id}")

    # async def handle_game_started(self, event: GameEvent):
    #     """Handle game_started events by broadcasting to WebSocket clients."""
    #     logger.debug(f"Broadcasting game_started for game {event.game_id}")
        
    #     game_state_data = event.data.get("game_state")
        
    #     message = {
    #         "type": "GAME_STARTED",
    #         "game_id": event.game_id,
    #         "start_page": game_state_data.config.start_page_title,
    #         "target_page": game_state_data.config.target_page_title,
    #         "status": game_state_data.status.value,
    #         "steps": game_state_data.steps
    #     }
        
    #     await websocket_manager.broadcast_to_game(event.game_id, message)
    #     logger.info(f"Broadcasted game_started to clients for game {event.game_id}")
    
    async def handle_game_ended(self, event: GameEvent):
        """Handle game_ended events by broadcasting final status to WebSocket clients."""
        logger.debug(f"Broadcasting game_ended for game {event.game_id}")
        
        game_state_data = event.data.get("game_state")
        
        message = {
            "type": "GAME_ENDED",
            "state": game_state_data.model_dump()
        }
        
        await websocket_manager.broadcast_to_game(event.game_id, message)
        logger.info(f"Broadcasted game_ended to clients for game {event.game_id}")

    async def handle_task_ended(self, event: GameEvent):
        """Handle task_ended events by broadcasting task completion to all WebSocket clients."""
        logger.debug(f"Broadcasting task_ended for task {event.game_id}")
        
        task_id = event.data.get("task_id")
        start_page = event.data.get("start_page")
        target_page = event.data.get("target_page")
        
        message = {
            "type": "TASK_ENDED",
            "task_id": task_id,
            "start_page": start_page,
            "target_page": target_page,
        }
        
        # Broadcast to all games in the system since we don't have game IDs anymore
        # Note: This could be optimized to only broadcast to games that were part of this task
        active_games = websocket_manager.get_all_games()
        for game_id in active_games:
            await websocket_manager.broadcast_to_game(game_id, message)
        
        logger.info(f"Broadcasted task_ended to {len(active_games)} game channels for task {task_id}")
