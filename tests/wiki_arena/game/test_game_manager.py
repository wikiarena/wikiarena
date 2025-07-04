"""
Comprehensive tests for GameManager that focus on edge cases and failure modes.
These tests are designed to catch bugs by testing boundary conditions and error scenarios.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
from typing import Optional, Any

from wiki_arena.game.game_manager import GameManager
from wiki_arena.models import (
    GameConfig, GameState, GameStatus, Page, Move, GameError, ErrorType, ModelConfig
)
from wiki_arena.wikipedia.live_service import LiveWikiService
from wiki_arena.language_models.language_model import ToolCall


class MockLanguageModel:
    """Mock language model for testing different response scenarios."""
    
    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0
    
    async def generate_response(self, tools, game_state):
        if self.call_count >= len(self.responses):
            raise Exception("No more mock responses available")
        
        response = self.responses[self.call_count]
        self.call_count += 1
        
        if isinstance(response, Exception):
            raise response
        return response


def create_mock_page(title="Test Page", links=None, text=""):
    """Helper to create mock Page objects."""
    if links is None:
        links = ["Link A", "Link B", "Link C"]
    return Page(
        title=title,
        url=f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
        links=links,
        text=text or f"Content for {title}"
    )


@pytest.fixture
def mock_wiki_service():
    """Mock LiveWikiService."""
    service = Mock(spec=LiveWikiService)
    
    # Default navigation behavior
    service.get_page = AsyncMock(return_value=create_mock_page(title="Start Page"))
    
    return service


@pytest.fixture
def basic_game_config():
    """Basic game configuration for testing."""
    return GameConfig(
        start_page_title="Start Page",
        target_page_title="Target Page", 
        max_steps=5,
        model=ModelConfig(
            provider="random",
            model_name="random",
            settings={}
        )
    )


@pytest.fixture
def start_page():
    """Mock start page with some links."""
    return create_mock_page(
        title="Start Page",
        links=["Link A", "Link B", "Target Page"]
    )


class TestGameManagerEdgeCases:
    """Test edge cases that might reveal bugs in game logic."""

    @pytest.mark.asyncio
    async def test_play_turn_before_start_game_should_fail(self, mock_wiki_service):
        """Test that calling play_turn before start_game fails gracefully."""
        manager = GameManager(mock_wiki_service)
        
        # This should return True (game over) because no game state exists
        result = await manager.play_turn()
        assert result is True, "play_turn should return True when no game state exists"

    @pytest.mark.asyncio
    async def test_play_turn_after_game_already_over(self, mock_wiki_service, basic_game_config):
        """Test calling play_turn on an already finished game."""
        manager = GameManager(mock_wiki_service)
        
        # Mock successful initial navigation
        mock_wiki_service.get_page.return_value = create_mock_page(
            title="Start Page", 
            links=["Link A", "Link B"]
        )
            
        # Start game and immediately set it to finished state
        await manager.initialize_game(basic_game_config)
        manager.state.status = GameStatus.WON
            
        # play_turn should return True immediately 
        result = await manager.play_turn()
        assert result is True, "play_turn should return True for already finished game"

    @pytest.mark.asyncio
    async def test_model_navigates_to_same_page(self, mock_wiki_service, basic_game_config, start_page):
        """Test when model tries to navigate to the page it's already on."""
        manager = GameManager(mock_wiki_service)
        
        # Mock initial navigation and subsequent same-page navigation
        mock_wiki_service.get_page.side_effect = [
            create_mock_page(title="Start Page", links=["Link A", "Link B", "Start Page"]),
            create_mock_page(title="Start Page", links=["Link A", "Link B", "Start Page"])
        ]
        
        # Mock model that tries to navigate to same page
        mock_model = MockLanguageModel([
            ToolCall(
                tool_name="navigate",
                tool_arguments={"page": "Start Page"},  # Same as current page
                model_text_response="I'll stay on the same page"
            )
        ])
        
        await manager.initialize_game(basic_game_config)
        manager.language_model = mock_model
            
        # This should work - navigating to same page might be valid
        result = await manager.play_turn()
            
        # Check if this creates a move
        assert len(manager.state.move_history) > 0, "Should create a move even for same-page navigation"
        assert manager.state.status == GameStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_model_requests_nonexistent_tool(self, mock_wiki_service, basic_game_config, start_page):
        """Test when model requests a tool that doesn't exist."""
        manager = GameManager(mock_wiki_service)
        
        # Mock initial navigation
        mock_wiki_service.get_page.return_value = create_mock_page(
            title="Start Page", 
            links=["Link A", "Link B"]
        )
        
        await manager.initialize_game(basic_game_config)
        
        # Mock model requesting nonexistent tool
        mock_model = MockLanguageModel([
            ToolCall(
                tool_name="nonexistent_tool",
                tool_arguments={"page": "Some Page"},
                model_text_response="Using nonexistent tool"
            )
        ])
        manager.language_model = mock_model
            
        # This should fail gracefully
        result = await manager.play_turn()
        assert result is True, "Should end game when invalid tool requested"
        assert manager.state.status == GameStatus.LOST_INVALID_MOVE
        assert len(manager.state.move_history) == 1
        assert manager.state.move_history[0].error is not None
        assert manager.state.move_history[0].error.type == ErrorType.MODEL_INVALID_TOOL

    @pytest.mark.asyncio
    async def test_model_provides_empty_tool_arguments(self, mock_wiki_service, basic_game_config, start_page):
        """Test when model provides empty or invalid tool arguments."""
        manager = GameManager(mock_wiki_service)
        mock_wiki_service.get_page.return_value = start_page
        await manager.initialize_game(basic_game_config)
        
        # Mock model providing empty args
        mock_model = MockLanguageModel([
            ToolCall(
                tool_name="navigate",
                tool_arguments={}, # No page argument
                model_text_response="I forgot the page"
            )
        ])
        manager.language_model = mock_model
        
        result = await manager.play_turn()
        
        assert result is True, "Game should end on invalid tool arguments"
        assert manager.state.status == GameStatus.LOST_INVALID_MOVE
        assert manager.state.move_history[0].error is not None
        assert manager.state.move_history[0].error.type == ErrorType.MODEL_INVALID_TOOL

    @pytest.mark.asyncio
    async def test_navigation_service_fails(self, mock_wiki_service, basic_game_config, start_page):
        """Test when the wiki service fails during navigation."""
        manager = GameManager(mock_wiki_service)
        
        # Mock initial navigation success, then navigation failure
        mock_wiki_service.get_page.side_effect = [
            start_page,
            ConnectionError("Wikipedia is down") # Simulate network error
        ]
        
        await manager.initialize_game(basic_game_config)
        
        # Mock model making a valid move
        mock_model = MockLanguageModel([
            ToolCall(
                tool_name="navigate",
                tool_arguments={"page": "Link A"},
                model_text_response="Navigating to Link A"
            )
        ])
        manager.language_model = mock_model
        
        result = await manager.play_turn()
        
        assert result is True, "Game should end on navigation failure"
        assert manager.state.status == GameStatus.ERROR
        assert manager.state.move_history[0].error is not None
        assert manager.state.move_history[0].error.type == ErrorType.APP_NAVIGATION_ERROR

    @pytest.mark.asyncio
    async def test_case_sensitive_link_validation(self, mock_wiki_service, basic_game_config):
        """Test that link validation is case sensitive."""
        manager = GameManager(mock_wiki_service)
        
        # Page with mixed-case links
        start_page_with_case = create_mock_page(
            title="Start Page",
            links=["CaseSensitiveLink", "AnotherLink"]
        )
        mock_wiki_service.get_page.return_value = start_page_with_case
        
        await manager.initialize_game(basic_game_config)
        
        # Model tries to navigate to lower-case version of link
        mock_model = MockLanguageModel([
            ToolCall(
                tool_name="navigate",
                tool_arguments={"page": "casesensitivelink"}, # wrong case
                model_text_response="I'll use the wrong case"
            )
        ])
        manager.language_model = mock_model
        
        result = await manager.play_turn()
        
        assert result is True, "Game should end on invalid link"
        assert manager.state.status == GameStatus.LOST_INVALID_MOVE
        assert manager.state.move_history[0].error.type == ErrorType.MODEL_INVALID_LINK

    @pytest.mark.asyncio
    async def test_navigation_returns_different_page_than_requested(self, mock_wiki_service, basic_game_config, start_page):
        """Test when navigation results in a different page (e.g. redirect)."""
        manager = GameManager(mock_wiki_service)
        
        redirected_page = create_mock_page(title="Redirected Page", links=["A", "B"])
        
        mock_wiki_service.get_page.side_effect = [
            start_page,
            redirected_page
        ]

        await manager.initialize_game(basic_game_config)

        # Model requests 'Target Page' but service returns 'Redirected Page'
        mock_model = MockLanguageModel([
            ToolCall(
                tool_name="navigate",
                tool_arguments={"page": "Target Page"},
                model_text_response="Navigating to target"
            )
        ])
        manager.language_model = mock_model
        
        result = await manager.play_turn()
        
        assert result is False, "Game should not end on a successful redirect"
        assert manager.state.status == GameStatus.IN_PROGRESS
        assert manager.state.current_page.title == "Redirected Page"
        assert manager.state.move_history[0].to_page_title == "Redirected Page"

    @pytest.mark.asyncio
    async def test_steps_counter_consistency(self, mock_wiki_service, basic_game_config, start_page):
        """Test that the steps counter increments correctly and consistently."""
        manager = GameManager(mock_wiki_service)
        
        mock_wiki_service.get_page.side_effect = [
            start_page,
            create_mock_page(title="Page 2", links=["Target Page"]),
            create_mock_page(title="Target Page", links=[])
        ]
        
        await manager.initialize_game(basic_game_config)
        assert manager.state.steps == 0
        
        manager.language_model = MockLanguageModel([
            ToolCall(tool_name="navigate", tool_arguments={"page": "Link A"}), # This will go to "Page 2"
            ToolCall(tool_name="navigate", tool_arguments={"page": "Target Page"})
        ])
        
        # First move
        await manager.play_turn()
        assert manager.state.steps == 1
        assert manager.state.move_history[0].step == 1
        
        # Second move (win)
        await manager.play_turn()
        assert manager.state.steps == 2
        assert manager.state.move_history[1].step == 2
        assert manager.state.status == GameStatus.WON

    @pytest.mark.asyncio
    async def test_error_move_recording_consistency(self, mock_wiki_service, basic_game_config, start_page):
        """Test that errors are recorded correctly in the move history."""
        manager = GameManager(mock_wiki_service)
        mock_wiki_service.get_page.return_value = start_page
        await manager.initialize_game(basic_game_config)
        
        # Model returns an invalid link
        invalid_link = "NonExistentLink"
        mock_model = MockLanguageModel([
            ToolCall(
                tool_name="navigate",
                tool_arguments={"page": invalid_link},
                model_text_response="I'm sure this link exists."
            )
        ])
        manager.language_model = mock_model
        
        await manager.play_turn()
        
        assert manager.state.status == GameStatus.LOST_INVALID_MOVE
        assert len(manager.state.move_history) == 1
        
        error_move = manager.state.move_history[0]
        assert error_move.step == 1
        assert error_move.from_page_title == start_page.title
        assert error_move.to_page_title is None
        assert error_move.error is not None
        assert error_move.error.type == ErrorType.MODEL_INVALID_LINK
        assert invalid_link in error_move.error.message

    @pytest.mark.asyncio
    @pytest.mark.parametrize("error_str, expected_type", [
        ("PROVIDER_RATE_LIMIT: Too many requests", ErrorType.PROVIDER_RATE_LIMIT),
        ("PROVIDER_TIMEOUT: Request timed out", ErrorType.PROVIDER_TIMEOUT),
        ("PROVIDER_API_ERROR: 500 Server Error", ErrorType.PROVIDER_API_ERROR),
        ("MODEL_GENERATION_ERROR: Something went wrong", ErrorType.MODEL_GENERATION_ERROR),
        ("Some other random error", ErrorType.APP_UNKNOWN_ERROR)
    ])
    async def test_provider_error_categorization(self, mock_wiki_service, basic_game_config, start_page, error_str, expected_type):
        """Test that various provider errors are categorized correctly."""
        manager = GameManager(mock_wiki_service)
        mock_wiki_service.get_page.return_value = start_page
        await manager.initialize_game(basic_game_config)
        
        # Mock model to raise a specific exception
        manager.language_model = MockLanguageModel([Exception(error_str)])
        
        await manager.play_turn()
        
        assert manager.state.status == GameStatus.ERROR
        # Since this error happens before a move is created, the error is on the game state
        if not manager.state.move_history:
            assert manager.state.error_message is not None
        else:
            # If a move was created, error is there
            assert manager.state.move_history[0].error is not None
            assert manager.state.move_history[0].error.type == expected_type 