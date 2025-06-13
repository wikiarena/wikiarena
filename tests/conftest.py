"""
Pytest configuration and shared fixtures for backend testing.
"""

import pytest
import asyncio
import logging
from typing import AsyncGenerator

from wiki_arena import EventBus, GameEvent
from wiki_arena.solver import WikiTaskSolver,wiki_task_solver
from wiki_arena.models import GameState, GameConfig, ModelConfig, Page, Move, GameStatus
from backend.handlers.optimal_path_handler import OptimalPathHandler

# Configure logging for tests
logging.basicConfig(level=logging.INFO)

@pytest.fixture
def event_bus() -> EventBus:
    """Create a fresh EventBus for each test."""
    return EventBus()

@pytest.fixture
def optimal_path_handler(event_bus: EventBus, solver: WikiTaskSolver = wiki_task_solver) -> OptimalPathHandler:
    """Create OptimalPathHandler with initialized solver."""
    return OptimalPathHandler(event_bus, solver)

@pytest.fixture
def sample_game_config() -> GameConfig:
    """Standard game configuration for testing."""
    return GameConfig(
        start_page_title="Python (programming language)",
        target_page_title="JavaScript",
        max_steps=10,
        model=ModelConfig(provider="random", model_name="random")
    )

@pytest.fixture
def sample_page() -> Page:
    """Sample Wikipedia page for testing."""
    return Page(
        title="Programming language",
        url="https://en.wikipedia.org/wiki/Programming_language", 
        text="A programming language is a formal language...",
        links=["JavaScript", "Computer science", "Software"]
    )

@pytest.fixture
def sample_game_state(sample_game_config: GameConfig, sample_page: Page) -> GameState:
    """Sample game state for testing."""
    return GameState(
        game_id="test_game",
        config=sample_game_config,
        current_page=sample_page,
        status=GameStatus.IN_PROGRESS,
        steps=1
    )

@pytest.fixture
def sample_move() -> Move:
    """Sample move for testing."""
    return Move(
        step=1,
        from_page_title="Python (programming language)",
        to_page_title="Programming language"
    )

@pytest.fixture
def move_completed_event(sample_game_state: GameState, sample_move: Move) -> GameEvent:
    """Sample move_completed event for testing."""
    return GameEvent(
        type="move_completed",
        game_id="test_game",
        data={
            "game_state": sample_game_state,
            "move": sample_move
        }
    )

@pytest.fixture
def game_started_event(sample_game_state: GameState) -> GameEvent:
    """Sample game_started event for testing."""
    # Modify to be initial state
    initial_state = sample_game_state.model_copy()
    initial_state.steps = 0
    initial_state.current_page = Page(
        title="Python (programming language)",
        url="https://en.wikipedia.org/wiki/Python_(programming_language)",
        text="Python is a programming language...",
        links=["JavaScript", "Programming", "Computer science"]
    )
    
    return GameEvent(
        type="game_started",
        game_id="test_game",
        data={"game_state": initial_state}
    ) 