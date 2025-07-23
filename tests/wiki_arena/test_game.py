"""
Comprehensive tests for GameManager that focus on edge cases and failure modes.
These tests are designed to catch bugs by testing boundary conditions and error scenarios.
"""

import pytest
import asyncio
from unittest.mock import patch
from typing import List

from wiki_arena.game import Game
from wiki_arena.types import (
    GameConfig, GameState, GameStatus, Page, Move, GameError, ErrorType, ModelConfig
)
from wiki_arena.wikipedia import LiveWikiService
from wiki_arena.language_models import LanguageModel
from wiki_arena.language_models.random_model import RandomModel
from wiki_arena.tools import get_tools
from wiki_arena import EventBus
from wiki_arena.types import AssistantMessage, AssistantToolCall


@pytest.fixture
def language_model() -> LanguageModel:
    """Provides a real RandomModel instance."""
    return RandomModel(ModelConfig(provider="random", model_name="random"))

@pytest.fixture
def wiki_service() -> LiveWikiService:
    """Provides a real LiveWikiService instance for integration testing."""
    return LiveWikiService()

@pytest.fixture
def tools() -> List[dict]:
    """Provides the actual toolset for the game."""
    return get_tools()

@pytest.fixture
def event_bus() -> EventBus:
    """Provides a real EventBus instance."""
    return EventBus()

@pytest.fixture
def basic_game_config():
    """Basic game configuration for testing."""
    return GameConfig(
        start_page_title="Python (programming language)",
        target_page_title="JavaScript",
        max_steps=5
    )

@pytest.fixture
async def start_page(wiki_service: LiveWikiService, basic_game_config: GameConfig) -> Page:
    """Provides a real start page fetched from Wikipedia."""
    return await wiki_service.get_page(basic_game_config.start_page_title)


class TestGameIntegration:
    """
    Integration tests for the Game class using real components
    (LiveWikiService, RandomModel, EventBus) to ensure they work together correctly.
    """

    @pytest.mark.asyncio
    async def test_model_navigates_to_same_page(self, basic_game_config, wiki_service, language_model, tools, event_bus):
        """Test when model is forced to navigate to the page it's already on."""
        recursion_page_title = "Recursion (computer science)"
        # We fetch the real page to make sure it exists and to get its URL.
        real_recursion_page = await wiki_service.get_page(recursion_page_title)
        # Now, create a controlled start page that *only* contains a link to itself,
        # ensuring the RandomModel has no other choice.
        controlled_start_page = Page(
            title=real_recursion_page.title, 
            url=real_recursion_page.url, 
            links=[recursion_page_title], 
            text="..."
        )

        game = Game(
            config=basic_game_config,
            wiki_service=wiki_service,
            language_model=language_model,
            start_page=controlled_start_page,
            tools=tools,
            event_bus=event_bus,
        )
            
        result = await game.run()
        
        assert not result, "Game should not be over after one turn"
        assert len(game.state.moves) == 1, "Should create a move even for same-page navigation"
        assert game.state.current_page.title == recursion_page_title
        assert game.state.status == GameStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_model_with_no_links(self, basic_game_config, wiki_service, language_model, tools, event_bus):
        """Test game behavior when the current page has no links."""
        no_links_page = Page(title="Dead End Page", url="test_url", links=[], text="This page has no links.")
        
        game = Game(
            config=basic_game_config,
            wiki_service=wiki_service,
            language_model=language_model,
            start_page=no_links_page,
            tools=tools,
            event_bus=event_bus,
        )
        
        result = await game.run()
        
        assert result is True, "Game should end when model cannot make a tool call"
        assert game.state.status == GameStatus.LOST_INVALID_MOVE
        assert game.state.moves[0].error is not None
        assert game.state.moves[0].error.type == ErrorType.MODEL_NO_TOOL_CALL

    @pytest.mark.asyncio
    async def test_navigation_service_fails_on_bad_page(self, basic_game_config, wiki_service, language_model, tools, event_bus):
        """Test when the wiki service fails to find a page."""
        # Page with a link that will fail to resolve
        bad_link_page = Page(title="Test Page", url="test_url", links=["NON_EXISTENT_PAGE_12345"], text="...")

        game = Game(
            config=basic_game_config,
            wiki_service=wiki_service,
            language_model=language_model,
            start_page=bad_link_page,
            tools=tools,
            event_bus=event_bus,
        )
        
        result = await game.run()
        
        assert result is True, "Game should end on navigation failure"
        assert game.state.status == GameStatus.ERROR
        assert game.state.moves[0].error is not None
        assert game.state.moves[0].error.type == ErrorType.APP_NAVIGATION_ERROR

    @pytest.mark.asyncio
    async def test_navigation_handles_redirect(self, basic_game_config, wiki_service, language_model, tools, event_bus):
        """Test the game continues correctly after a page redirect."""
        # "USA" is a reliable redirect to "United States"
        redirect_page_name = "USA" 
        final_page_name = "United States"
        
        # We start from a fabricated page that links to the redirect page.
        start_page_with_redirect_link = Page(title="Start Page", url="test_url", links=[redirect_page_name], text="...")

        game = Game(
            config=basic_game_config,
            wiki_service=wiki_service,
            language_model=language_model,
            start_page=start_page_with_redirect_link,
            tools=tools,
            event_bus=event_bus,
        )
        
        result = await game.run()

        assert not result, "Game should not be over after a redirect"
        assert game.state.current_page.title == final_page_name
        assert game.state.steps == 1

    @pytest.mark.asyncio
    async def test_full_game_run_to_win(self, wiki_service, language_model, tools, event_bus):
        """Test a short game from start to finish, aiming for a win."""
        # A short, predictable path
        start_page_title = "Six degrees of separation"
        target_page_title = "Kevin Bacon"

        config = GameConfig(
            start_page_title=start_page_title,
            target_page_title=target_page_title, 
            max_steps=5
        )
        
        start_page = await wiki_service.get_page(start_page_title)
        
        # Mock successful navigation
        game.wiki_service.get_page.return_value = start_page

        # Patch random choice to force a win
        with patch('random.choice', return_value=target_page_title):
            game = Game(
                config=config,
                wiki_service=wiki_service,
                language_model=language_model,
                start_page=start_page,
                tools=tools,
                event_bus=event_bus,
            )
        
            result = await game.run()
        
            assert result is True, "Game should be over"
            assert game.state.status == GameStatus.WON
            assert game.state.steps == 1
            assert game.state.current_page.title == target_page_title 


@pytest.mark.asyncio
async def test_model_with_invalid_tool_call(game: Game):
    """Test game behavior when the model makes an invalid tool call."""
    # Mock the model to make an invalid move (select a non-existent link)
    invalid_tool_call = AssistantToolCall(
        id="test_call_1",
        name="navigate_to_page", 
        arguments={"page_title": "Invalid Link"}
    )
    game.language_model.generate_response.return_value = AssistantMessage(
        content="Trying to navigate to invalid link",
        tool_calls=[invalid_tool_call]
    )

    # Act
    await game.run()

    # Assert
    assert game.state.status == GameStatus.LOST_INVALID_MOVE


@pytest.mark.asyncio
async def test_game_max_steps(game: Game):
    """Test game behavior when max steps is reached."""
    game.config.max_steps = 1
    valid_tool_call = AssistantToolCall(
        id="test_call_2",
        name="navigate_to_page", 
        arguments={"page_title": "Another Page"}
    )
    game.language_model.generate_response.return_value = AssistantMessage(
        content="Navigating to another page",
        tool_calls=[valid_tool_call]
    )
    game.wiki_service.get_page.return_value = Page(title="Another Page", text="...", links=[])

    # Act
    await game.run()

    # Assert
    assert game.state.status == GameStatus.LOST_MAX_STEPS


@pytest.mark.asyncio
async def test_model_with_no_tool_call(game: Game):
    """Test game behavior when the model makes no tool call."""
    # Mock the language model to return no tool call
    game.language_model.generate_response.return_value = AssistantMessage(
        content="I'm not sure what to do",
        tool_calls=None
    )

    # Act
    await game.run()

    # Assert
    assert game.state.status == GameStatus.LOST_INVALID_MOVE


@pytest.mark.asyncio
async def test_model_with_invalid_tool_name(game: Game):
    """Test game behavior when the model makes an invalid tool name."""
    # Mock the language model to return an invalid tool name
    invalid_tool_call = AssistantToolCall(
        id="test_call_4",
        name="invalid_tool", 
        arguments={"page_title": "Target"}
    )
    game.language_model.generate_response.return_value = AssistantMessage(
        content="Trying to use invalid tool",
        tool_calls=[invalid_tool_call]
    )

    # Act
    await game.run()

    # Assert
    assert game.state.status == GameStatus.LOST_INVALID_MOVE
    assert "unavailable tool" in game.state.error_message 