import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime

from wiki_arena.config import load_config
from wiki_arena.mcp_client.client import MCPClient, create_server_params_from_config
from wiki_arena.game.game_manager import GameManager
from wiki_arena.data_models.game_models import GameConfig, ModelConfig, GameState, GameStatus, GameResult
from wiki_arena.language_models import create_model
from wiki_arena.storage import GameStorageService, StorageConfig

from backend.models.api_models import (
    StartGameRequest, 
    GameStateResponse, 
    MoveResponse, 
    GameConfigResponse,
    StartGameResponse
)
from backend.config import config
from backend.websockets.game_hub import websocket_manager

class GameService:
    """Service that wraps GameManager for API usage with WebSocket support."""
    
    def __init__(self):
        self.active_games: Dict[str, GameManager] = {}
        self.background_tasks: Dict[str, asyncio.Task] = {}
        self.app_config = None
        self.storage_service = None
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self):
        """Initialize the service with wiki_arena configuration."""
        try:
            self.app_config = load_config()
            
            # Initialize storage service for backend games
            storage_config = StorageConfig() # use default config
            self.storage_service = GameStorageService(storage_config)
            
            self.logger.info("GameService initialized with wiki_arena config and storage")
        except Exception as e:
            self.logger.error(f"Failed to load wiki_arena config: {e}")
            raise
    
    async def start_game(self, request: StartGameRequest, background: bool = False) -> StartGameResponse:
        """Start a new game and optionally run it in the background."""
        try:
            # Create MCP client
            mcp_client = await self._create_mcp_client()
            
            # Create model config
            model = create_model(request.model_provider)
            if request.model_name != "random":
                # Override model name if specified
                model.model_config.model_name = request.model_name
            
            # Create game config
            game_config = GameConfig(
                start_page_title=request.start_page,
                target_page_title=request.target_page,
                max_steps=request.max_steps,
                model=model.model_config
            )
            
            # Create and start game
            game_manager = GameManager(mcp_client)
            initial_state = await game_manager.start_game(game_config)
            
            # Store the game manager
            self.active_games[initial_state.game_id] = game_manager
            
            # Convert to API format
            api_state = self._convert_game_state_to_api(initial_state)
            
            self.logger.info(f"Started game {initial_state.game_id}: {request.start_page} -> {request.target_page}")
            
            # Broadcast initial state via WebSocket
            await self._broadcast_game_update(initial_state.game_id, "game_started", api_state)
            
            # Start background execution if requested
            if background:
                task = asyncio.create_task(self._run_game_background(initial_state.game_id))
                self.background_tasks[initial_state.game_id] = task
                self.logger.info(f"Started background execution for game {initial_state.game_id}")
            
            return StartGameResponse(
                game_id=initial_state.game_id,
                message="Game started successfully" + (" (running in background)" if background else ""),
                game_state=api_state
            )
            
        except Exception as e:
            self.logger.error(f"Failed to start game: {e}", exc_info=True)
            raise
    
    async def get_game_state(self, game_id: str) -> Optional[GameStateResponse]:
        """Get current state of a game."""
        game_manager = self.active_games.get(game_id)
        if not game_manager or not game_manager.state:
            return None
        
        return self._convert_game_state_to_api(game_manager.state)
    
    async def play_turn(self, game_id: str) -> Optional[GameStateResponse]:
        """Play a single turn of the game."""
        game_manager = self.active_games.get(game_id)
        if not game_manager:
            return None
        
        try:
            # Check if game is running in background
            if game_id in self.background_tasks:
                # Game is running in background, just return current state
                return self._convert_game_state_to_api(game_manager.state)
            
            game_over = await game_manager.play_turn()
            api_state = self._convert_game_state_to_api(game_manager.state)
            
            # Broadcast turn update via WebSocket
            if game_manager.state.move_history:
                last_move = game_manager.state.move_history[-1]
                await self._broadcast_game_update(game_id, "turn_played", api_state, {
                    "move": self._convert_move_to_api(last_move),
                    "game_over": game_over
                })
            
            # If game is over, clean up
            if game_over:
                await self._broadcast_game_update(game_id, "game_finished", api_state, {
                    "final_status": api_state.status,
                    "total_steps": api_state.steps
                })
                await self._cleanup_game(game_id)
            
            return api_state
            
        except Exception as e:
            self.logger.error(f"Error playing turn for game {game_id}: {e}", exc_info=True)
            # Broadcast error via WebSocket
            await self._broadcast_game_update(game_id, "error", None, {
                "error": str(e),
                "error_type": "turn_execution_error"
            })
            # Clean up on error
            await self._cleanup_game(game_id)
            raise
    
    async def _run_game_background(self, game_id: str):
        """Run a game to completion in the background."""
        game_manager = self.active_games.get(game_id)
        if not game_manager:
            return
        
        try:
            self.logger.info(f"Starting background execution for game {game_id}")
            
            while True:
                game_over = await game_manager.play_turn()
                api_state = self._convert_game_state_to_api(game_manager.state)
                
                # Broadcast turn update
                if game_manager.state.move_history:
                    last_move = game_manager.state.move_history[-1]
                    await self._broadcast_game_update(game_id, "turn_played", api_state, {
                        "move": self._convert_move_to_api(last_move),
                        "game_over": game_over,
                        "background": True
                    })
                
                if game_over:
                    await self._broadcast_game_update(game_id, "game_finished", api_state, {
                        "final_status": api_state.status,
                        "total_steps": api_state.steps,
                        "background": True
                    })
                    break
                
                # Small delay between turns for better UX
                await asyncio.sleep(1.0)
            
            self.logger.info(f"Background game {game_id} completed with status: {game_manager.state.status.value}")
            
        except Exception as e:
            self.logger.error(f"Error in background game {game_id}: {e}", exc_info=True)
            await self._broadcast_game_update(game_id, "error", None, {
                "error": str(e),
                "error_type": "background_execution_error"
            })
        finally:
            # Clean up
            await self._cleanup_game(game_id)
    
    async def _broadcast_game_update(self, game_id: str, event_type: str, game_state: Optional[GameStateResponse], extra_data: Optional[Dict] = None):
        """Broadcast a game update via WebSocket."""
        message = {
            "type": event_type,
            "game_state": game_state.dict() if game_state else None
        }
        
        if extra_data:
            # Convert any Pydantic models to dicts for JSON serialization
            serializable_extra = {}
            for key, value in extra_data.items():
                if hasattr(value, 'dict'):  # Pydantic model
                    serializable_extra[key] = value.dict()
                else:
                    serializable_extra[key] = value
            message.update(serializable_extra)
        
        # Debug logging
        self.logger.info(f"Broadcasting {event_type} to game {game_id} - WebSocket connections: {websocket_manager.get_connection_count(game_id)}")
        
        await websocket_manager.broadcast_to_game(game_id, message)
    
    async def _create_mcp_client(self) -> MCPClient:
        """Create and connect an MCP client."""
        if not self.app_config:
            await self.initialize()
        
        # Get server config (reuse existing logic)
        server_config = self.app_config['mcp_servers'][config.mcp_server_name]
        server_params = create_server_params_from_config(server_config.get("transport", {}))
        
        # Create and connect client
        mcp_client = MCPClient()
        await mcp_client.connect(server_params)
        
        return mcp_client
    
    async def _cleanup_game(self, game_id: str):
        """Clean up resources for a finished game."""
        # Cancel background task if running
        if game_id in self.background_tasks:
            task = self.background_tasks[game_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            del self.background_tasks[game_id]
        
        # Get game manager for storage before cleanup
        game_manager = self.active_games.get(game_id)
        
        # Store completed game before cleanup
        if self.storage_service and game_manager and game_manager.state:
            try:
                # Only store if game is actually completed (not in progress)
                if game_manager.state.status != GameStatus.IN_PROGRESS:
                    game_result = GameResult.from_game_state(game_manager.state)
                    # Run storage in executor to avoid blocking the event loop
                    await asyncio.get_event_loop().run_in_executor(
                        None, self.storage_service.store_game, game_result
                    )
                    self.logger.info(f"Stored game {game_id} to persistent storage")
            except Exception as e:
                self.logger.error(f"Failed to store game {game_id}: {e}")
        
        # Clean up MCP client
        if game_manager and game_manager.mcp_client:
            try:
                # Create a new task for MCP disconnection to avoid cancel scope issues
                disconnect_task = asyncio.create_task(game_manager.mcp_client.disconnect())
                await asyncio.wait_for(disconnect_task, timeout=5.0)
            except asyncio.TimeoutError:
                self.logger.warning(f"Timeout disconnecting MCP client for game {game_id}")
            except Exception as e:
                self.logger.warning(f"Error disconnecting MCP client for game {game_id}: {e}")
        
        # Remove from active games
        self.active_games.pop(game_id, None)
        self.logger.info(f"Cleaned up game {game_id}")
    
    def _convert_move_to_api(self, move) -> MoveResponse:
        """Convert a single move to API format."""
        return MoveResponse(
            step=move.step,
            from_page_title=move.from_page_title,
            to_page_title=move.to_page_title,
            model_response=move.model_response,
            tool_call_attempt=move.tool_call_attempt,
            error=move.error.dict() if move.error else None,
            timestamp=move.timestamp.isoformat() if hasattr(move, 'timestamp') and move.timestamp else None
        )
    
    def _convert_game_state_to_api(self, game_state: GameState) -> GameStateResponse:
        """Convert internal GameState to API format."""
        # Convert moves
        api_moves = []
        for move in game_state.move_history:
            api_move = self._convert_move_to_api(move)
            api_moves.append(api_move)
        
        # Map status to frontend format
        status_mapping = {
            GameStatus.NOT_STARTED: "not_started",
            GameStatus.IN_PROGRESS: "in_progress", 
            GameStatus.WON: "won",
            GameStatus.LOST_MAX_STEPS: "lost_max_steps",
            GameStatus.LOST_INVALID_MOVE: "lost_invalid_move",
            GameStatus.ERROR: "error"
        }
        
        return GameStateResponse(
            game_id=game_state.game_id,
            status=status_mapping[game_state.status],
            steps=game_state.steps,
            start_page=game_state.config.start_page_title,
            target_page=game_state.config.target_page_title,
            current_page=game_state.current_page.title if game_state.current_page else None,
            moves=api_moves,
            start_timestamp=game_state.start_timestamp.isoformat(),
            end_timestamp=datetime.now().isoformat() if game_state.status in [
                GameStatus.WON, GameStatus.LOST_MAX_STEPS, 
                GameStatus.LOST_INVALID_MOVE, GameStatus.ERROR
            ] else None
        )
    
    def get_active_games(self) -> Dict[str, str]:
        """Get list of active games with their status."""
        return {
            game_id: "background" if game_id in self.background_tasks else "manual"
            for game_id in self.active_games.keys()
        }

# Global service instance
game_service = GameService()
