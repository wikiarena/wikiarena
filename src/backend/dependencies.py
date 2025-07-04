from fastapi import Request
from wiki_arena import EventBus
from backend.coordinators.task_coordinator import TaskCoordinator
from backend.coordinators.game_coordinator import GameCoordinator
from wiki_arena.solver import WikiTaskSolver
from wiki_arena.wikipedia import LiveWikiService

async def get_event_bus(request: Request) -> EventBus:
    """Dependency provider to get the shared EventBus instance."""
    return request.app.state.event_bus

def get_task_coordinator(request: Request) -> TaskCoordinator:
    """Dependency to get the TaskCoordinator from app state."""
    return request.app.state.task_coordinator 

async def get_game_coordinator(request: Request) -> GameCoordinator:
    """Dependency provider to get the shared GameCoordinator instance."""
    return request.app.state.game_coordinator

async def get_solver(request: Request) -> WikiTaskSolver:
    """Dependency provider to get the shared WikiTaskSolver instance."""
    return request.app.state.solver

async def get_wiki_service(request: Request) -> LiveWikiService:
    """Dependency provider to get the shared LiveWikiService instance."""
    return request.app.state.wiki_service