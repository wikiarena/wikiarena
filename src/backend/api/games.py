from fastapi import APIRouter, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Query, Depends
from typing import Dict, Any, Annotated
import logging

from wiki_arena.types import GameState
from backend.coordinators.game_coordinator import GameCoordinator
from backend.websockets.game_hub import websocket_manager
from backend.dependencies import get_game_coordinator

router = APIRouter(prefix="/api/games", tags=["games"])
logger = logging.getLogger(__name__)

GameCoordinatorDep = Annotated[GameCoordinator, Depends(get_game_coordinator)]

@router.get("/{game_id}", response_model=GameState)
async def get_game_state(game_id: str, coordinator: GameCoordinatorDep) -> GameState:
    """Get the current state of a game."""
    state = await coordinator.get_game_state(game_id)
    if not state:
        raise HTTPException(
            status_code=404,
            detail=f"Game {game_id} not found"
        )
    return state

@router.get("/{game_id}/status")
async def get_game_status(game_id: str, coordinator: GameCoordinatorDep) -> Dict[str, Any]:
    """Get just the status of a game (lightweight endpoint for polling)."""
    state = await coordinator.get_game_state(game_id)
    if not state:
        raise HTTPException(
            status_code=404,
            detail=f"Game {game_id} not found"
        )
    return {
        "game_id": state.game_id,
        "status": state.status.value,
        "steps": state.steps,
        "current_page": state.current_page.title if state.current_page else None
    }

@router.websocket("/{game_id}/ws")
async def game_websocket(websocket: WebSocket, game_id: str):
    """WebSocket endpoint for real-time game updates."""
    await websocket_manager.connect(websocket, game_id)
    logger.info(f"WebSocket connected for game {game_id}")
    
    try:
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
async def list_active_games(coordinator: GameCoordinatorDep) -> Dict[str, Any]:
    """List all active games and their execution mode."""
    try:
        active_games = coordinator.get_active_games()
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
