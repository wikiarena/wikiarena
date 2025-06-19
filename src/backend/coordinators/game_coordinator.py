import asyncio
import logging
from typing import Dict, Optional, Set
from datetime import datetime

from wiki_arena import EventBus, GameEvent
from wiki_arena.game.game_manager import GameManager
from wiki_arena.models import GameConfig, GameState, GameStatus
from wiki_arena.language_models import create_model
from wiki_arena.mcp_client.client import MCPClient

from backend.models.api_models import StartGameRequest, StartGameResponse
from backend.services.task_selector_service import task_selector_service

logger = logging.getLogger(__name__)

class GameCoordinator:
    """
    Coordinates game lifecycle and orchestrates between core library and web layer.
    
    Responsibilities:
    - Manage active game instances
    - Create games using core library
    - Coordinate background game execution
    - Handle request/response conversion where needed
    - Wait for initial paths before starting gameplay
    
    Does NOT handle:
    - WebSocket broadcasting (handled by WebSocketHandler)
    - task solver (handled by OptimalPathHandler) 
    - Storage (handled by StorageHandler - future)
    """
    
    def __init__(self, event_bus: EventBus, mcp_client: MCPClient):
        self.event_bus = event_bus
        self.mcp_client = mcp_client
        self.active_games: Dict[str, GameManager] = {}
        self.background_tasks: Dict[str, asyncio.Task] = {}
        # Track games waiting for initial paths to be ready
        self.games_waiting_for_initial_paths: Set[str] = set()
        
    async def start_game(self, request: StartGameRequest, background: bool = False) -> StartGameResponse:
        """Start a new game and optionally run it in the background."""
        logger.info(f"Starting game with strategy: {request.task_strategy.type}")
        
        # Select task using the specified strategy
        task = await task_selector_service.select_task(request.task_strategy)
        logger.debug(f"Task selection result: {task} (type: {type(task)})")
        
        if not task:
            raise ValueError("Failed to select a valid task")
        
        logger.info(f"Selected task: {task.start_page_title} -> {task.target_page_title}")
        
        # Create model configuration
        model = create_model(request.model_provider)
        if request.model_name != "random":
            model.model_config.model_name = request.model_name
        
        # Create game configuration
        game_config = GameConfig(
            start_page_title=task.start_page_title,
            target_page_title=task.target_page_title,
            max_steps=request.max_steps,
            model=model.model_config
        )
        
        # Create GameManager with event bus
        game_manager = GameManager(self.mcp_client, event_bus=self.event_bus)
        initial_state = await game_manager.start_game(game_config)
        
        if initial_state.status == GameStatus.ERROR:
            logger.error(f"Failed to start game: {initial_state.error_message}")
            raise ValueError(f"Game initialization failed: {initial_state.error_message}")
        
        # Store active game
        self.active_games[initial_state.game_id] = game_manager
        
        # Mark game as waiting for initial paths if background execution requested
        if background:
            self.games_waiting_for_initial_paths.add(initial_state.game_id)
            background_task = asyncio.create_task(self._run_game_background(initial_state.game_id))
            self.background_tasks[initial_state.game_id] = background_task
            logger.info(f"Game {initial_state.game_id} marked as waiting for initial paths")
            
        # Emit game_started event (this will trigger initial path calculation)
        await self.event_bus.publish(GameEvent(
            type="game_started",
            game_id=initial_state.game_id,
            data={"game_state": initial_state}
        ))
        
        # Get task strategy info for response
        task_info = task_selector_service.get_strategy_info(request.task_strategy)
        task_info.update({
            "start_page": task.start_page_title,
            "target_page": task.target_page_title
        })
        
        logger.info(f"Game {initial_state.game_id} started successfully")
        return StartGameResponse(
            game_id=initial_state.game_id,
            message="Game started successfully",
            task_info=task_info
        )
    
    async def handle_initial_paths_ready(self, event: GameEvent):
        """Handle initial_paths_ready event and allow background game execution to proceed."""
        game_id = event.game_id
        if game_id in self.games_waiting_for_initial_paths:
            self.games_waiting_for_initial_paths.remove(game_id)
            logger.info(f"Initial paths ready for game {game_id}, gameplay can now proceed")
        else:
            logger.debug(f"Received initial_paths_ready for game {game_id} but game was not waiting")
    
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
            game_id: "background" if game_id in self.background_tasks else "interactive"
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
        self.games_waiting_for_initial_paths.clear()
        
        logger.info("GameCoordinator shutdown complete")
    
    async def _run_game_background(self, game_id: str):
        """Run a game in the background until completion, waiting for initial paths first."""
        try:
            logger.info(f"Starting background execution for game {game_id}")
            
            # Wait for initial paths to be ready before starting gameplay
            logger.info(f"Waiting for initial paths to be ready for game {game_id}")
            while game_id in self.games_waiting_for_initial_paths:
                if game_id not in self.active_games:
                    # Game was terminated while waiting
                    logger.info(f"Game {game_id} was terminated while waiting for initial paths")
                    return
                await asyncio.sleep(0.1)  # Small polling interval
            
            logger.info(f"Initial paths ready, starting gameplay for game {game_id}")
            
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
            # Ensure cleanup happens
            if game_id in self.active_games:
                await self._cleanup_game(game_id)
    
    async def _cleanup_game(self, game_id: str):
        """Clean up game resources."""
        # Cancel background task if exists
        if game_id in self.background_tasks:
            self.background_tasks[game_id].cancel()
            del self.background_tasks[game_id]
        
        # Remove from active games
        if game_id in self.active_games:
            del self.active_games[game_id]
        
        # Remove from waiting set if still there
        if game_id in self.games_waiting_for_initial_paths:
            self.games_waiting_for_initial_paths.remove(game_id)
        
        logger.info(f"Cleaned up game {game_id}")
