from fastapi import APIRouter, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Query
from typing import Dict, Any
import logging

from backend.models.api_models import (
    StartGameRequest,
    StartGameResponse, 
    GameStateResponse,
    ErrorResponse
)
from backend.services.game_service import game_service
from backend.websockets.game_hub import websocket_manager

router = APIRouter(prefix="/api/games", tags=["games"])
logger = logging.getLogger(__name__)

@router.post("", response_model=StartGameResponse)
async def start_game(request: StartGameRequest, background: bool = Query(False, description="Run game in background")) -> StartGameResponse:
    """Start a new game with the specified configuration."""
    try:
        # Initialize service if needed
        if not game_service.app_config:
            await game_service.initialize()
        
        response = await game_service.start_game(request, background=background)
        return response
        
    except Exception as e:
        logger.error(f"Failed to start game: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start game: {str(e)}"
        )

@router.get("/{game_id}", response_model=GameStateResponse)
async def get_game_state(game_id: str) -> GameStateResponse:
    """Get the current state of a game."""
    try:
        game_state = await game_service.get_game_state(game_id)
        
        if not game_state:
            raise HTTPException(
                status_code=404,
                detail=f"Game {game_id} not found"
            )
        
        return game_state
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get game state for {game_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get game state: {str(e)}"
        )

@router.post("/{game_id}/turn", response_model=GameStateResponse)
async def play_turn(game_id: str) -> GameStateResponse:
    """Play a single turn of the game."""
    try:
        game_state = await game_service.play_turn(game_id)
        
        if not game_state:
            raise HTTPException(
                status_code=404,
                detail=f"Game {game_id} not found"
            )
        
        return game_state
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to play turn for {game_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to play turn: {str(e)}"
        )

@router.get("/{game_id}/status")
async def get_game_status(game_id: str) -> Dict[str, Any]:
    """Get just the status of a game (lightweight endpoint for polling)."""
    try:
        game_state = await game_service.get_game_state(game_id)
        
        if not game_state:
            raise HTTPException(
                status_code=404,
                detail=f"Game {game_id} not found"
            )
        
        return {
            "game_id": game_state.game_id,
            "status": game_state.status,
            "steps": game_state.steps,
            "current_page": game_state.current_page
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get game status for {game_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get game status: {str(e)}"
        )

@router.websocket("/{game_id}/ws")
async def game_websocket(websocket: WebSocket, game_id: str):
    """WebSocket endpoint for real-time game updates."""
    try:
        await websocket_manager.connect(websocket, game_id)
        logger.info(f"WebSocket connected for game {game_id}")
        
        # Keep connection alive and handle client messages
        while True:
            try:
                # Wait for client messages (ping/pong, etc.)
                message = await websocket.receive_text()
                logger.debug(f"Received WebSocket message for game {game_id}: {message}")
                
                # Echo back for ping/pong
                if message == "ping":
                    await websocket.send_text("pong")
                
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for game {game_id}")
                break
            except Exception as e:
                logger.error(f"Error in WebSocket for game {game_id}: {e}")
                break
                
    except Exception as e:
        logger.error(f"WebSocket connection error for game {game_id}: {e}")
    finally:
        await websocket_manager.disconnect(websocket)

@router.get("")
async def list_active_games() -> Dict[str, Any]:
    """List all active games and their execution mode."""
    try:
        active_games = game_service.get_active_games()
        websocket_connections = {
            game_id: websocket_manager.get_connection_count(game_id)
            for game_id in active_games.keys()
        }
        
        return {
            "active_games": active_games,
            "websocket_connections": websocket_connections,
            "total_games": len(active_games)
        }
        
    except Exception as e:
        logger.error(f"Failed to list active games: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list active games: {str(e)}"
        )
