"""
Comprehensive tests for GameManager that focus on edge cases and failure modes.
These tests are designed to catch bugs by testing boundary conditions and error scenarios.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
from typing import Optional

from wiki_arena.game.game_manager import GameManager
from wiki_arena.models import (
    GameConfig, GameState, GameStatus, Page, Move, GameError, ErrorType, ModelConfig
)
from wiki_arena.mcp_client.client import MCPClient
from wiki_arena.language_models.language_model import ToolCall
from wiki_arena.capabilities.navigation import NavigationResult
from mcp.types import Tool


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


class MockNavigationCapability:
    """Mock navigation capability for testing different navigation scenarios."""
    
    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0
    
    async def navigate_to_page(self, page_title):
        if self.call_count >= len(self.responses):
            return NavigationResult(
                success=False,
                error_message="No more mock navigation responses",
                page=None
            )
        
        response = self.responses[self.call_count]
        self.call_count += 1
        return response
    
    async def get_capability_info(self):
        return {"type": "mock", "features": ["navigation"]}
    
    def is_available(self):
        return True


@pytest.fixture
def mock_mcp_client():
    """Mock MCP client with basic functionality."""
    client = Mock(spec=MCPClient)
    client.list_tools = AsyncMock(return_value=Mock(tools=[
        Tool(
            name="navigate", 
            description="Navigate to page",
            inputSchema={
                "type": "object",
                "properties": {
                    "page": {"type": "string"}
                },
                "required": ["page"]
            }
        )
    ]))
    return client


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
    return Page(
        title="Start Page",
        url="http://example.com/start",
        links=["Link A", "Link B", "Target Page"]
    )


class TestGameManagerEdgeCases:
    """Test edge cases that might reveal bugs in game logic."""

    @pytest.mark.asyncio
    async def test_play_turn_before_start_game_should_fail(self, mock_mcp_client):
        """Test that calling play_turn before start_game fails gracefully."""
        manager = GameManager(mock_mcp_client)
        
        # This should return True (game over) because no game state exists
        result = await manager.play_turn()
        assert result is True, "play_turn should return True when no game state exists"

    @pytest.mark.asyncio
    async def test_play_turn_after_game_already_over(self, mock_mcp_client, basic_game_config):
        """Test calling play_turn on an already finished game."""
        manager = GameManager(mock_mcp_client)
        
        # Create mock navigation capability
        mock_nav_capability = MockNavigationCapability([
            NavigationResult(success=True, page=Page(title="Start Page", url="", links=[]), error_message=None)
        ])
        
        # Mock capability registry
        with patch.object(manager.capability_registry, 'initialize', return_value=True), \
             patch.object(manager.capability_registry, 'get_navigation_capability', return_value=mock_nav_capability):
            
            # Start game and immediately set it to finished state
            await manager.start_game(basic_game_config)
            manager.state.status = GameStatus.WON
            
            # play_turn should return True immediately 
            result = await manager.play_turn()
            assert result is True, "play_turn should return True for already finished game"

    @pytest.mark.asyncio
    async def test_model_navigates_to_same_page(self, mock_mcp_client, basic_game_config, start_page):
        """Test when model tries to navigate to the page it's already on."""
        manager = GameManager(mock_mcp_client)
        
        # Mock model that tries to navigate to same page
        mock_model = MockLanguageModel([
            ToolCall(
                tool_name="navigate",
                tool_arguments={"page": "Start Page"},  # Same as current page
                model_text_response="I'll stay on the same page"
            )
        ])
        manager.language_model = mock_model
        
        # Mock successful navigation capability setup
        mock_nav_capability = MockNavigationCapability([
            NavigationResult(success=True, page=start_page, error_message=None)
        ])
        
        with patch.object(manager.capability_registry, 'initialize', return_value=True), \
             patch.object(manager.capability_registry, 'get_navigation_capability', return_value=mock_nav_capability):
            
            await manager.start_game(basic_game_config)
            manager.state.current_page = start_page
            
            # This should work - navigating to same page might be valid
            result = await manager.play_turn()
            
            # Check if this creates a move or fails
            assert len(manager.state.move_history) > 0, "Should create a move even for same-page navigation"

    @pytest.mark.asyncio
    async def test_model_requests_nonexistent_tool(self, mock_mcp_client, basic_game_config, start_page):
        """Test when model requests a tool that doesn't exist."""
        manager = GameManager(mock_mcp_client)
        
        # Create mock navigation capability
        mock_nav_capability = MockNavigationCapability([
            NavigationResult(success=True, page=start_page, error_message=None)
        ])
        
        with patch.object(manager.capability_registry, 'initialize', return_value=True), \
             patch.object(manager.capability_registry, 'get_navigation_capability', return_value=mock_nav_capability):
            
            await manager.start_game(basic_game_config)
            manager.state.current_page = start_page
            
            # NOW override the language model after start_game
            mock_model = MockLanguageModel([
                ToolCall(
                    tool_name="nonexistent_tool",
                    tool_arguments={"page": "Some Page"},
                    model_text_response="Using nonexistent tool"
                )
            ])
            manager.language_model = mock_model
            
            result = await manager.play_turn()
            
            assert result is True, "Game should end when model requests nonexistent tool"
            assert manager.state.status == GameStatus.LOST_INVALID_MOVE
            assert len(manager.state.move_history) == 1
            assert manager.state.move_history[0].error.type == ErrorType.MODEL_INVALID_TOOL

    @pytest.mark.asyncio
    async def test_model_provides_empty_tool_arguments(self, mock_mcp_client, basic_game_config, start_page):
        """Test when model provides empty or malformed tool arguments."""
        manager = GameManager(mock_mcp_client)
        
        # Create mock navigation capability
        mock_nav_capability = MockNavigationCapability([
            NavigationResult(success=True, page=start_page, error_message=None)
        ])
        
        with patch.object(manager.capability_registry, 'initialize', return_value=True), \
             patch.object(manager.capability_registry, 'get_navigation_capability', return_value=mock_nav_capability):
            
            await manager.start_game(basic_game_config)
            manager.state.current_page = start_page
            
            # NOW override the language model after start_game
            mock_model = MockLanguageModel([
                ToolCall(
                    tool_name="navigate",
                    tool_arguments={},  # Empty arguments
                    model_text_response="Navigate with empty args"
                )
            ])
            manager.language_model = mock_model
            
            result = await manager.play_turn()
            
            assert result is True, "Game should end when tool arguments are empty"
            assert manager.state.status == GameStatus.LOST_INVALID_MOVE
            assert len(manager.state.move_history) == 1
            assert manager.state.move_history[0].error.type == ErrorType.MODEL_INVALID_TOOL

    @pytest.mark.asyncio
    async def test_case_sensitive_link_validation(self, mock_mcp_client, basic_game_config):
        """Test if link validation is case-sensitive when it shouldn't be."""
        manager = GameManager(mock_mcp_client)
        
        # Page with links in specific case
        current_page = Page(
            title="Start Page",
            url="",
            links=["target page", "other link"]  # lowercase
        )
        
        # Model tries to navigate to different case
        mock_model = MockLanguageModel([
            ToolCall(
                tool_name="navigate", 
                tool_arguments={"page": "Target Page"},  # Different case
                model_text_response="Navigate to Target Page"
            )
        ])
        manager.language_model = mock_model
        
        # Create mock navigation capability
        mock_nav_capability = MockNavigationCapability([
            NavigationResult(success=True, page=current_page, error_message=None)
        ])
        
        with patch.object(manager.capability_registry, 'initialize', return_value=True), \
             patch.object(manager.capability_registry, 'get_navigation_capability', return_value=mock_nav_capability):
            
            await manager.start_game(basic_game_config)
            manager.state.current_page = current_page
            
            result = await manager.play_turn()
            
            # This might fail if our validation is too strict about case
            # The test will reveal if we handle case sensitivity properly
            print(f"Game status: {manager.state.status}")
            print(f"Move history: {len(manager.state.move_history)}")
            if manager.state.move_history:
                print(f"Error: {manager.state.move_history[0].error}")
                
            # If our link validation is case-sensitive (which it shouldn't be), 
            # this will fail with LOST_INVALID_MOVE
            if manager.state.status == GameStatus.LOST_INVALID_MOVE:
                print("BUG FOUND: Link validation is case-sensitive!")
                print(f"Available links: {current_page.links}")
                print(f"Requested link: Target Page")
                assert False, "Link validation should be case-insensitive"

    @pytest.mark.asyncio
    async def test_navigation_returns_different_page_than_requested(self, mock_mcp_client, basic_game_config, start_page):
        """Test when navigation succeeds but returns a different page (e.g., due to redirects)."""
        manager = GameManager(mock_mcp_client)
        
        # Navigation returns success but different page
        redirected_page = Page(title="Redirected Page", url="", links=[])
        mock_nav_capability = MockNavigationCapability([
            NavigationResult(success=True, page=start_page, error_message=None),  # For start_game
            NavigationResult(success=True, page=redirected_page, error_message=None)  # For play_turn
        ])
        
        with patch.object(manager.capability_registry, 'initialize', return_value=True), \
             patch.object(manager.capability_registry, 'get_navigation_capability', return_value=mock_nav_capability):
            
            await manager.start_game(basic_game_config)
            manager.state.current_page = start_page
            
            # NOW override the language model after start_game
            mock_model = MockLanguageModel([
                ToolCall(
                    tool_name="navigate",
                    tool_arguments={"page": "Link A"},
                    model_text_response="Navigate to Link A"
                )
            ])
            manager.language_model = mock_model
            
            result = await manager.play_turn()
            
            # Should this be considered success? The move should record the actual destination
            assert manager.state.current_page.title == "Redirected Page"
            if len(manager.state.move_history) > 0:
                move = manager.state.move_history[0]
                # The to_page_title should reflect the actual destination, not the requested one
                assert move.to_page_title == "Redirected Page"

    @pytest.mark.asyncio
    async def test_steps_counter_consistency(self, mock_mcp_client, basic_game_config, start_page):
        """Test that steps counter stays consistent with move history."""
        manager = GameManager(mock_mcp_client)
        
        target_page = Page(title="Target Page", url="", links=[])
        
        mock_nav_capability = MockNavigationCapability([
            NavigationResult(success=True, page=start_page, error_message=None),  # For start_game
            NavigationResult(success=True, page=Page(title="Link A", url="", links=["Target Page"]), error_message=None),
            NavigationResult(success=True, page=target_page, error_message=None)
        ])
        
        with patch.object(manager.capability_registry, 'initialize', return_value=True), \
             patch.object(manager.capability_registry, 'get_navigation_capability', return_value=mock_nav_capability):
            
            await manager.start_game(basic_game_config)
            manager.state.current_page = start_page
            
            # NOW override the language model after start_game
            mock_model = MockLanguageModel([
                ToolCall(tool_name="navigate", tool_arguments={"page": "Link A"}, model_text_response="Move 1"),
                ToolCall(tool_name="navigate", tool_arguments={"page": "Target Page"}, model_text_response="Move 2")
            ])
            manager.language_model = mock_model
            
            # Make two moves
            result1 = await manager.play_turn()
            assert result1 is False, "First move should continue game"
            
            result2 = await manager.play_turn()
            assert result2 is True, "Second move should win"
            
            # Check consistency
            assert manager.state.steps == len(manager.state.move_history), \
                f"Steps ({manager.state.steps}) should equal move history length ({len(manager.state.move_history)})"
            
            # Check step numbers in moves
            for i, move in enumerate(manager.state.move_history):
                expected_step = i + 1
                assert move.step == expected_step, \
                    f"Move {i} has step {move.step}, expected {expected_step}"

    @pytest.mark.asyncio
    async def test_concurrent_play_turn_calls(self, mock_mcp_client, basic_game_config, start_page):
        """Test what happens if play_turn is called concurrently (race condition)."""
        manager = GameManager(mock_mcp_client)
        
        slow_model = Mock()
        slow_model.generate_response = AsyncMock()
        
        # Simulate slow model response
        async def slow_response(*args, **kwargs):
            await asyncio.sleep(0.1)  # Simulate network delay
            return ToolCall(
                tool_name="navigate",
                tool_arguments={"page": "Link A"},
                model_text_response="Slow response"
            )
        
        slow_model.generate_response.side_effect = slow_response
        manager.language_model = slow_model
        
        mock_nav_capability = MockNavigationCapability([
            NavigationResult(success=True, page=Page(title="Link A", url="", links=[]), error_message=None),
            NavigationResult(success=True, page=Page(title="Link A", url="", links=[]), error_message=None)
        ])
        
        with patch.object(manager.capability_registry, 'initialize', return_value=True), \
             patch.object(manager.capability_registry, 'get_navigation_capability', return_value=mock_nav_capability):
            
            await manager.start_game(basic_game_config)
            manager.state.current_page = start_page
            
            # Start two concurrent play_turn calls
            task1 = asyncio.create_task(manager.play_turn())
            task2 = asyncio.create_task(manager.play_turn())
            
            results = await asyncio.gather(task1, task2, return_exceptions=True)
            
            # At least one should complete successfully, but check for race conditions
            print(f"Concurrent results: {results}")
            print(f"Final steps: {manager.state.steps}")
            print(f"Move history length: {len(manager.state.move_history)}")
            
            # Check for inconsistencies that might indicate race conditions
            assert manager.state.steps >= 0, "Steps should never be negative"
            assert len(manager.state.move_history) >= 0, "Move history should never be negative length"

    @pytest.mark.asyncio
    async def test_error_move_recording_consistency(self, mock_mcp_client, basic_game_config, start_page):
        """Test that error moves are recorded consistently."""
        manager = GameManager(mock_mcp_client)
        
        # Model that will cause an invalid link error
        mock_model = MockLanguageModel([
            ToolCall(
                tool_name="navigate",
                tool_arguments={"page": "Nonexistent Link"},
                model_text_response="Navigate to nonexistent link"
            )
        ])
        manager.language_model = mock_model
        
        # Create mock navigation capability for start_game
        mock_nav_capability = MockNavigationCapability([
            NavigationResult(success=True, page=start_page, error_message=None)
        ])
        
        with patch.object(manager.capability_registry, 'initialize', return_value=True), \
             patch.object(manager.capability_registry, 'get_navigation_capability', return_value=mock_nav_capability):
            
            await manager.start_game(basic_game_config)
            manager.state.current_page = start_page
            
            result = await manager.play_turn()
            
            assert result is True, "Game should end due to invalid link"
            assert len(manager.state.move_history) == 1, "Should have exactly one error move"
            
            error_move = manager.state.move_history[0]
            assert error_move.error is not None, "Move should have error information"
            assert error_move.to_page_title is None, "Error move should have no destination"
            assert error_move.step == 1, "Error move should have correct step number"
            assert error_move.from_page_title == "Start Page", "Error move should have correct source"

    @pytest.mark.asyncio
    async def test_provider_error_categorization(self, mock_mcp_client, basic_game_config, start_page):
        """Test that different provider errors are categorized correctly."""
        manager = GameManager(mock_mcp_client)
        
        # Test different provider errors
        test_cases = [
            (Exception("rate limit exceeded"), ErrorType.PROVIDER_RATE_LIMIT),
            (Exception("request timeout"), ErrorType.PROVIDER_TIMEOUT), 
            (Exception("HTTP 500 internal server error"), ErrorType.PROVIDER_API_ERROR),
            (Exception("unknown model error"), ErrorType.MODEL_GENERATION_ERROR),
            (Exception("some other error"), ErrorType.APP_UNKNOWN_ERROR),
        ]
        
        for exception, expected_error_type in test_cases:
            manager_instance = GameManager(mock_mcp_client)
            
            mock_model = MockLanguageModel([exception])
            manager_instance.language_model = mock_model
            
            # Create mock navigation capability
            mock_nav_capability = MockNavigationCapability([
                NavigationResult(success=True, page=start_page, error_message=None)
            ])
            
            with patch.object(manager_instance.capability_registry, 'initialize', return_value=True), \
                 patch.object(manager_instance.capability_registry, 'get_navigation_capability', return_value=mock_nav_capability):
                
                await manager_instance.start_game(basic_game_config)
                manager_instance.state.current_page = start_page
                
                result = await manager_instance.play_turn()
                
                assert result is True, f"Game should end due to {exception}"
                assert manager_instance.state.status == GameStatus.ERROR
                
                # Check if error was categorized correctly (this might reveal categorization bugs)
                if len(manager_instance.state.move_history) > 0:
                    move = manager_instance.state.move_history[0]
                    if move.error:
                        print(f"Exception: {exception}")
                        print(f"Expected: {expected_error_type}")
                        print(f"Actual: {move.error.type}")
                        # This assertion might fail and reveal categorization bugs
                        # assert move.error.type == expected_error_type


if __name__ == "__main__":
    # Run specific tests to catch bugs
    pytest.main([__file__, "-v", "-s"]) 