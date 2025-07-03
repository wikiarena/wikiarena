import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime

from wiki_arena import EventBus, GameEvent
from wiki_arena.game.game_manager import GameManager
from wiki_arena.models import GameConfig, GameState, GameStatus, Task
from wiki_arena.language_models import create_model
from wiki_arena.mcp_client.client import MCPClient

from backend.models.api_models import ModelSelection

logger = logging.getLogger(__name__)

class GameCoordinator:
    """
    Coordinates individual game lifecycle and execution.
    
    Responsibilities:
    - Initialize individual games
    - Manage game execution and background tasks
    - Handle game-level events
    - Clean up game resources
    
    Does NOT handle:
    - Task coordination (handled by TaskCoordinator)
    - WebSocket broadcasting (handled by WebSocketHandler)
    - Path solving (handled by SolverHandler) 
    - Storage (handled by StorageHandler)
    """
    
    def __init__(self, event_bus: EventBus, mcp_client: MCPClient):
        self.event_bus = event_bus
        self.mcp_client = mcp_client
        self.active_games: Dict[str, GameManager] = {} # { game_id: GameManager }
        # background was because we thought we would support an interactive mode (viewer can step through)
        # TODO(hunter): refactor this as everything is background now
        self.background_tasks: Dict[str, asyncio.Task] = {} # { game_id: asyncio.Task }
        
    async def setup_game(self, task: Task, model_selection: ModelSelection, max_steps: int = 30) -> str:
        """Initialize a new game without starting execution. Returns game_id."""
        logger.info(f"Setting up game: {model_selection.model_name} for task {task.start_page_title} -> {task.target_page_title}")
        
        # Create model configuration
        model = create_model(model_selection.model_name)

        # Create game configuration
        game_config = GameConfig(
            start_page_title=task.start_page_title,
            target_page_title=task.target_page_title,
            max_steps=max_steps,
            model=model.model_config
        )
        
        # Create GameManager with event bus
        # TODO(hunter): we could pass the language model and config to the constructor?
        game_manager = GameManager(self.mcp_client, event_bus=self.event_bus) 
        initial_state = await game_manager.initialize_game(game_config)
        
        if initial_state.status == GameStatus.ERROR:
            logger.error(f"Failed to initialize game: {initial_state.error_message}")
            raise ValueError(f"Game initialization failed: {initial_state.error_message}")
        
        # Store active game
        self.active_games[initial_state.game_id] = game_manager
        
        # Emit game_started event
        await self.event_bus.publish(GameEvent(
            type="game_started",
            game_id=initial_state.game_id,
            data={"game_state": initial_state}
        ))
        
        logger.info(f"Game {initial_state.game_id} initialized successfully")
        return initial_state.game_id
    
    async def start_game_execution(self, game_id: str, background: bool = True) -> bool:
        """Start execution for an initialized game."""
        if game_id not in self.active_games:
            logger.error(f"Cannot start execution for unknown game: {game_id}")
            return False
        
        if background:
            # Start background execution
            background_task = asyncio.create_task(self._run_game_background(game_id))
            self.background_tasks[game_id] = background_task
            logger.info(f"Started background execution for game {game_id}")
        
        return True
    
    async def start_games(self, game_ids: list[str], background: bool = True) -> int:
        """Start execution for multiple games. Returns number of successfully started games."""
        started_count = 0
        for game_id in game_ids:
            if await self.start_game_execution(game_id, background):
                started_count += 1
        
        logger.info(f"Started execution for {started_count}/{len(game_ids)} games")
        return started_count
    
    async def get_game_state(self, game_id: str) -> Optional[GameState]:
        """Get current state of a game."""
        game_manager = self.active_games.get(game_id)
        if not game_manager or not game_manager.state:
            return None
        
        return game_manager.state
    
    async def play_turn(self, game_id: str) -> Optional[GameState]:
        """Play a single turn of the game."""
        game_manager = self.active_games.get(game_id)
        if not game_manager:
            return None
        
        # Execute turn (this will emit events via EventBus)
        game_over = await game_manager.play_turn()
        
        # Clean up if game is over
        if game_over:
            await self._cleanup_game(game_id)
        
        return game_manager.state
    
    async def terminate_game(self, game_id: str):
        """Forcibly terminate a game and clean up resources."""
        if game_id not in self.active_games:
            raise ValueError(f"Game {game_id} not found")
        
        logger.info(f"Terminating game {game_id}")
        await self._cleanup_game(game_id)
    
    def get_active_games(self) -> Dict[str, str]:
        """List all active games and their execution mode."""
        return {
            game_id: "background" if game_id in self.background_tasks else "inactive"
            for game_id in self.active_games.keys()
        }
    
    async def shutdown(self):
        """Gracefully shutdown all games and background tasks."""
        logger.info("Shutting down GameCoordinator...")
        
        # Cancel all background tasks
        for task in self.background_tasks.values():
            task.cancel()
        
        # Wait for tasks to complete
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks.values(), return_exceptions=True)
        
        # Clear everything
        self.active_games.clear()
        self.background_tasks.clear()
        
        logger.info("GameCoordinator shutdown complete")
    
    async def _run_game_background(self, game_id: str):
        """Run a game in the background until completion."""
        try:
            logger.info(f"Starting background execution for game {game_id}")
            
            while game_id in self.active_games:
                game_state = await self.play_turn(game_id)
                if not game_state or game_state.status.value not in ['in_progress', 'not_started']:
                    logger.info(f"Background game {game_id} completed with status: {game_state.status.value if game_state else 'not_found'}")
                    break
                
                # Small delay between moves
                await asyncio.sleep(1.0)
                
        except asyncio.CancelledError:
            logger.info(f"Background game {game_id} cancelled")
        except Exception as e:
            logger.error(f"Error in background game {game_id}: {e}", exc_info=True)
        finally:
            # Clean up background task reference
            self.background_tasks.pop(game_id, None)
    
    async def _cleanup_game(self, game_id: str):
        """Clean up a completed or terminated game."""
        # Cancel background task if running
        if game_id in self.background_tasks:
            self.background_tasks[game_id].cancel()
            try:
                await self.background_tasks[game_id]
            except asyncio.CancelledError:
                pass
            del self.background_tasks[game_id]
        
        # Remove from active games
        if game_id in self.active_games:
            del self.active_games[game_id]
        
        logger.debug(f"Cleaned up game {game_id}")
