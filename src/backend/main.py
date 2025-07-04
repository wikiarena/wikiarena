import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import config
from backend.api.games import router as games_router
from backend.api.tasks import router as tasks_router
from backend.websockets.game_hub import websocket_manager
from backend.coordinators.game_coordinator import GameCoordinator
from backend.coordinators.task_coordinator import TaskCoordinator
from wiki_arena import EventBus
from wiki_arena.wikipedia import LiveWikiService

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
    wiki_service = LiveWikiService()
    logger.info("LiveWikiService created.")
    
    # Create and initialize solver
    from wiki_arena.solver import WikiTaskSolver
    from wiki_arena.solver import static_solver_db
    
    solver = WikiTaskSolver(db=static_solver_db)
    logger.info("WikiTaskSolver created")
    
    # Create coordinators
    game_coordinator = GameCoordinator(event_bus, wiki_service)
    task_coordinator = TaskCoordinator(event_bus, game_coordinator)
    
    # Create event handlers with dependencies
    from backend.handlers.websocket_handler import WebSocketHandler
    from backend.handlers.solver_handler import SolverHandler
    from backend.handlers.storage_handler import StorageHandler
    from backend.utils.state_collector import StateCollector
    
    websocket_handler = WebSocketHandler()
    solver_handler = SolverHandler(event_bus, solver)
    storage_handler = StorageHandler()
    
    # Create state collector and wire it to websocket manager
    state_collector = StateCollector(game_coordinator, solver_handler)
    websocket_manager.state_collector = state_collector
    
    # Register event handlers
    event_bus.subscribe("task_selected", solver_handler.handle_task_selected) # start solving task
    event_bus.subscribe("task_solved", task_coordinator.handle_task_solved) # start games (old handle_initial_paths_ready)
    event_bus.subscribe("task_solved", websocket_handler.handle_task_solved) # send shortest paths to frontend for all games under that task

    event_bus.subscribe("move_completed", websocket_handler.handle_move_completed) # broadcast move to all clients
    event_bus.subscribe("move_completed", solver_handler.handle_move_completed) # solve new subtask
    event_bus.subscribe("shortest_paths_found", websocket_handler.handle_shortest_paths_found) # broadcast optimal paths to all clients
    event_bus.subscribe("game_ended", websocket_handler.handle_game_ended) # broadcast game ended to all clients
    event_bus.subscribe("game_ended", storage_handler.handle_game_ended) # store game in database# NOTE: task_solved is similar to initial_paths_ready
    event_bus.subscribe("game_ended", task_coordinator.handle_game_ended) # mark game as ended, broadcast task_ended if all games have ended 
    
    event_bus.subscribe("task_ended", websocket_handler.handle_task_ended) # broadcast task ended to all clients
    # TODO(hunter): make solver cache per target page (more than one task at a time)
    # event_bus.subscribe("task_ended", solver_handler.handle_task_ended) # clear solver cache for this target page
    
    logger.info("Event handlers registered")
    
    # Store in app state
    app.state.event_bus = event_bus
    app.state.game_coordinator = game_coordinator
    app.state.task_coordinator = task_coordinator
    app.state.wiki_service = wiki_service
    app.state.solver = solver
    
    logger.info("Wiki Arena API startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Wiki Arena API...")
    await game_coordinator.shutdown()
    await task_coordinator.shutdown()
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
app.include_router(tasks_router)
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
            "Task-centric multi-game coordination",
            "WebSocket support for real-time updates",
            "Background game execution",
            "Live game streaming"
        ],
        "docs": "/docs",
        "health": "/health",
        "websocket_example": "ws://localhost:8000/api/games/{game_id}/ws",
        "task_api": "/api/tasks"
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
            "real_time_updates": True,
            "task_coordination": True
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
        
        # Get task stats
        task_coordinator = app.state.task_coordinator
        active_tasks = task_coordinator.get_active_tasks()
        
        return {
            "active_games": len(active_games),
            "active_tasks": len(active_tasks),
            "total_websocket_connections": total_connections,
            "games_with_connections": {
                game_id: websocket_manager.get_connection_count(game_id)
                for game_id in active_games
            },
            "task_details": active_tasks
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
