import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime

from wiki_arena import EventBus, GameEvent
from wiki_arena.game import Game
from wiki_arena.types import GameConfig, GameState, GameStatus, Task, Page
from wiki_arena.openrouter import create_openrouter_model
from wiki_arena.tools import get_tools
from wiki_arena.wikipedia import LiveWikiService
from backend.exceptions import InvalidModelException

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
    
    def __init__(self, event_bus: EventBus, wiki_service: LiveWikiService):
        self.event_bus = event_bus
        self.wiki_service = wiki_service
        self.active_games: Dict[str, Game] = {} # { game_id: Game }
        # background was because we thought we would support an interactive mode (viewer can step through)
        # TODO(hunter): refactor this as everything is background now
        self.background_tasks: Dict[str, asyncio.Task] = {} # { game_id: asyncio.Task }
        
    async def setup_game(self, task: Task, model_id: str, start_page: Page, max_steps: int = 30) -> str:
        """Initialize a new game without starting execution. Returns game_id."""
        logger.info(f"Setting up game: {model_id} for task {task.start_page_title} -> {task.target_page_title}")
        
        # Create model configuration
        try:
            language_model = create_openrouter_model(model_id)
        except ValueError as e:
            raise InvalidModelException(str(e))

        # Create game configuration
        game_config = GameConfig(
            start_page_title=task.start_page_title,
            target_page_title=task.target_page_title,
            max_steps=max_steps
        )
        
        tools = get_tools()

        try:
            game = Game(
                config=game_config,
                wiki_service=self.wiki_service,
                language_model=language_model,
                start_page=start_page,
                tools=tools,
                event_bus=self.event_bus,
            )
            initial_state = game.state
        except Exception as e:
            logger.error(f"Failed to initialize game: {e}", exc_info=True)
            raise ValueError(f"Game initialization failed: {e}")

        # Store active game
        self.active_games[game.id] = game
        
        # Emit game_initialized event
        # TODO(hunter): nothing uses this event
        # await self.event_bus.publish(GameEvent(
        #     type="game_initialized",
        #     game_id=game.id,
        #     data={"game_state": initial_state}
        # ))
        
        logger.info(f"Game {game.id} initialized successfully")
        return game.id
    
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
        game = self.active_games.get(game_id)
        if not game or not game.state:
            return None
        
        return game.state
    
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
        game = self.active_games.get(game_id)
        if not game:
            logger.warning(f"Attempted to run non-existent game: {game_id}")
            return

        try:
            logger.info(f"Starting background execution for game {game_id}")
            await game.run()
            logger.info(f"Background game {game_id} completed with status: {game.state.status.value if game.state else 'not_found'}")
                
        except asyncio.CancelledError:
            logger.info(f"Background game {game_id} cancelled")
        except Exception as e:
            logger.error(f"Error in background game {game_id}: {e}", exc_info=True)
        finally:
            # Game finished or errored, clean up
            self.background_tasks.pop(game_id, None)
            self.active_games.pop(game_id, None)
            logger.debug(f"Cleaned up game {game_id}")
    
    async def _cleanup_game(self, game_id: str):
        """Clean up a completed or terminated game."""
        # Cancel background task if running
        if game_id in self.background_tasks:
            self.background_tasks[game_id].cancel()
            # No need to await here, cancellation is fire-and-forget from this context

        # Remove from active games
        if game_id in self.active_games:
            del self.active_games[game_id]
        
        logger.debug(f"Cleaned up game {game_id}")
