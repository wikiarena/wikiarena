from fastapi import Request
from wiki_arena import EventBus
from wiki_arena.solver import WikiTaskSolver
from backend.coordinators.game_coordinator import GameCoordinator

async def get_event_bus(request: Request) -> EventBus:
    """Dependency provider to get the shared EventBus instance."""
    return request.app.state.event_bus

async def get_game_coordinator(request: Request) -> GameCoordinator:
    """Dependency provider to get the shared GameCoordinator instance."""
    return request.app.state.game_coordinator

async def get_solver(request: Request) -> WikiTaskSolver:
    """Dependency provider to get the shared WikiTaskSolver instance."""
    return request.app.state.solver 