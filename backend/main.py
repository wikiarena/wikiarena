import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import config
from backend.api.games import router as games_router
from backend.api.solver import router as solver_router
from backend.websockets.game_hub import websocket_manager

# Configure logging to match wiki_arena style
logging.basicConfig(
    level=logging.INFO,
    format="%(name)s: %(message)s", # TODO(hunter): this is not the wiki-arena style
    handlers=[logging.StreamHandler()]
)

# Create FastAPI app
app = FastAPI(
    title="Wiki Arena API",
    description="API for running Wikipedia navigation games with real-time updates",
    version="2.0.0",
    debug=config.debug
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(games_router)
app.include_router(solver_router)

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Wiki Arena API",
        "version": "2.0.0",
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
        "version": "2.0.0",
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
