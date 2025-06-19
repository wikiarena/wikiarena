import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import config
from backend.api.games import router as games_router
from backend.websockets.game_hub import websocket_manager
from backend.coordinators.game_coordinator import GameCoordinator
from wiki_arena import EventBus

# Configure unified logging to match wiki_arena style
from wiki_arena.logging_config import setup_logging
setup_logging(level="INFO")

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events."""
    logger.info("Starting Wiki Arena API...")
    
    # Create event bus
    event_bus = EventBus()
    
    # Initialize core services
    from wiki_arena.config import load_config
    from wiki_arena.mcp_client.client import MCPClient, create_server_params_from_config
    
    app_config = load_config()
    server_config = app_config['mcp_servers'][config.mcp_server_name]
    server_params = create_server_params_from_config(server_config.get("transport", {}))
    
    mcp_client = MCPClient()
    await mcp_client.connect(server_params)
    logger.info("MCP client connected")
    
    # Create and initialize solver
    from wiki_arena.solver import WikiTaskSolver
    from wiki_arena.solver.static_db import static_solver_db
    
    solver = WikiTaskSolver(db=static_solver_db)
    logger.info("WikiTaskSolver created")
    
    # Create coordinator
    game_coordinator = GameCoordinator(event_bus, mcp_client)
    
    # Create event handlers with dependencies
    from backend.handlers.websocket_handler import WebSocketHandler
    from backend.handlers.optimal_path_handler import OptimalPathHandler
    from backend.utils.state_collector import StateCollector
    
    websocket_handler = WebSocketHandler()
    optimal_path_handler = OptimalPathHandler(event_bus, solver)
    
    # Create state collector and wire it to websocket manager
    state_collector = StateCollector(game_coordinator, optimal_path_handler)
    websocket_manager.state_collector = state_collector
    
    # Register event handlers
    event_bus.subscribe("move_completed", websocket_handler.handle_move_completed)
    event_bus.subscribe("move_completed", optimal_path_handler.handle_move_completed)
    event_bus.subscribe("game_started", websocket_handler.handle_game_started)
    event_bus.subscribe("game_started", optimal_path_handler.handle_game_started)
    event_bus.subscribe("game_ended", websocket_handler.handle_game_ended)
    event_bus.subscribe("optimal_paths_found", websocket_handler.handle_optimal_paths_found)
    event_bus.subscribe("initial_paths_ready", game_coordinator.handle_initial_paths_ready)
    event_bus.subscribe("initial_paths_ready", websocket_handler.handle_optimal_paths_found) # NOTE: finding initial paths is a special case of optimal paths found
    # TODO(hunter): add storage and maybe metrics handler

    logger.info("Event handlers registered")
    
    # Store in app state
    app.state.event_bus = event_bus
    app.state.game_coordinator = game_coordinator
    app.state.mcp_client = mcp_client
    app.state.solver = solver
    
    logger.info("Wiki Arena API startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Wiki Arena API...")
    await game_coordinator.shutdown()
    await mcp_client.disconnect()
    logger.info("Wiki Arena API shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="Wiki Arena API",
    description="API for running Wikipedia navigation games with real-time updates",
    version="0.0.1",
    debug=config.debug,
    lifespan=lifespan
)

# Routers and Middleware
app.include_router(games_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Wiki Arena API",
        "version": "0.0.1",
        "features": [
            "REST API for game management",
            "WebSocket support for real-time updates",
            "Background game execution",
            "Live game streaming"
        ],
        "docs": "/docs",
        "health": "/health",
        "websocket_example": "ws://localhost:8000/api/games/{game_id}/ws"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "wiki-arena-api",
        "version": "0.0.1",
        "features": {
            "websockets": True,
            "background_execution": True,
            "real_time_updates": True
        }
    }

@app.get("/stats")
async def get_stats():
    """Get API statistics and active connections."""
    try:
        active_games = websocket_manager.get_all_games()
        total_connections = sum(
            websocket_manager.get_connection_count(game_id) 
            for game_id in active_games
        )
        
        return {
            "active_games": len(active_games),
            "total_websocket_connections": total_connections,
            "games_with_connections": {
                game_id: websocket_manager.get_connection_count(game_id)
                for game_id in active_games
            }
        }
    except Exception as e:
        return {
            "error": f"Failed to get stats: {str(e)}"
        }

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors."""
    logging.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": "An unexpected error occurred"
        }
    )

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
        log_level="info"
    )
