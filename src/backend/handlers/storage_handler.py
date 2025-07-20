import logging
from typing import Optional

from wiki_arena import GameEvent
from wiki_arena.models import GameResult, GameState
from wiki_arena.openrouter import OpenRouterModelConfig
from wiki_arena.storage import GameStorageService, StorageConfig

logger = logging.getLogger(__name__)

class StorageHandler:
    """
    Handles game result storage in response to game events.
    
    This handler is stateless and reactive - it receives game_ended events
    and persists the game results to storage.
    """
    
    def __init__(self, storage_config: Optional[StorageConfig] = None):
        self.storage_service = GameStorageService(storage_config or StorageConfig())
        self.enabled = True  # Can be configured to disable storage
        logger.info(f"StorageHandler initialized with storage path: {self.storage_service.config.storage_path}")
    
    async def handle_game_ended(self, event: GameEvent):
        """Handle game_ended events by storing the game result."""
        if not self.enabled:
            logger.debug(f"Storage disabled, skipping game {event.game_id}")
            return
            
        logger.debug(f"Processing game_ended event for storage: {event.game_id}")
        
        # Extract game state and model config from event
        game_state: GameState = event.data.get("game_state")
        model_config: OpenRouterModelConfig = event.data.get("model_config")
        if not game_state:
            logger.error(f"No game_state found in game_ended event for game {event.game_id}")
            return
        if not model_config:
            logger.error(f"No model_config found in game_ended event for game {event.game_id}")
            return
        
        try:
            # Convert GameState to GameResult
            game_result = GameResult.from_game_state(game_state, model_config.id)
            
            # Store the game result
            success = self.storage_service.store_game(game_result)
            
            if success:
                logger.info(f"Successfully stored game {event.game_id} ({game_result.status.value})")
            else:
                logger.warning(f"Failed to store game {event.game_id}")
                
        except Exception as e:
            logger.error(f"Error storing game result for {event.game_id}: {e}", exc_info=True)
    
    def enable_storage(self):
        """Enable storage operations."""
        self.enabled = True
        logger.info("Game storage enabled")
    
    def disable_storage(self):
        """Disable storage operations (useful for testing)."""
        self.enabled = False
        logger.info("Game storage disabled") 