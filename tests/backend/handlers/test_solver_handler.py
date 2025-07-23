"""
Level 2: SolverHandler Tests (pytest version)
Testing the task solver handler with real EventBus and wiki_arena solver.
"""

import pytest
import asyncio
import logging
from typing import List

from wiki_arena import EventBus, GameEvent
from wiki_arena.types import GameState, GameConfig, ModelConfig, Page, Move, GameStatus
from backend.handlers import SolverHandler

logger = logging.getLogger(__name__)

@pytest.mark.integration
@pytest.mark.requires_db
class TestSolverHandler:
    """Integration tests for SolverHandler with real solver."""
    
    @pytest.mark.asyncio
    async def test_path_analysis_on_move(
        self, 
        event_bus: EventBus, 
        solver_handler: SolverHandler,
        move_completed_event: GameEvent
    ):
        """Test task solver triggered by move_completed event."""
        analysis_results = []
        
        async def track_analysis(event: GameEvent):
            analysis_results.append(event.data)
            logger.info(f"task solver completed: {event.data.get('shortest_path_length')} steps")
        
        # Subscribe to events
        event_bus.subscribe("shortest_paths_found", track_analysis)
        event_bus.subscribe("move_completed", solver_handler.handle_move_completed)
        
        # Publish move completed event
        await event_bus.publish(move_completed_event)
        
        # Wait for async task solver to complete
        await asyncio.sleep(1.0)
        
        # Should have received task solver result
        assert len(analysis_results) > 0, "No task solver results received"
        
        result = analysis_results[0]
        assert "shortest_path_length" in result
        assert "from_page_title" in result
        assert "to_page_title" in result
        assert result["from_page_title"] == "Programming language"  # Current page after move
        assert result["to_page_title"] == "JavaScript"              # Target page
        assert isinstance(result["shortest_path_length"], int)
        assert result["shortest_path_length"] >= 0
    
    @pytest.mark.asyncio
    async def test_task_selected_analysis(
        self,
        event_bus: EventBus,
        solver_handler: SolverHandler
    ):
        """Test task solver triggered by task_selected event."""
        analysis_results = []
        
        async def track_analysis(event: GameEvent):
            analysis_results.append(event.data)
            logger.info(f"Task solved: {event.data.get('shortest_path_length')} steps")
        
        event_bus.subscribe("task_solved", track_analysis)
        event_bus.subscribe("task_selected", solver_handler.handle_task_selected)
        
        # Create a mock task for testing
        from wiki_arena.types import Task
        test_task = Task(
            start_page_title="Python (programming language)",
            target_page_title="JavaScript"
        )
        
        task_event = GameEvent(
            type="task_selected",
            game_id="test_task_123",  # This is actually task_id for task events
            data={
                "task": test_task,
                "task_id": "test_task_123",
                "game_ids": ["game1", "game2"]
            }
        )
        
        await event_bus.publish(task_event)
        
        # Wait for analysis
        await asyncio.sleep(1.0)
        
        # Should have task solution
        assert len(analysis_results) > 0, "No task solution results received"
        
        result = analysis_results[0]
        assert result["task_id"] == "test_task_123"
        assert result["from_page_title"] == "Python (programming language)"
        assert result["to_page_title"] == "JavaScript"
        assert "shortest_path_length" in result
    
    @pytest.mark.asyncio
    async def test_path_analysis_error_handling(
        self,
        event_bus: EventBus,
        solver_handler: SolverHandler
    ):
        """Test error handling in task solver."""
        error_events = []
        success_events = []
        
        async def track_errors(event: GameEvent):
            error_events.append(event.data)
            logger.info(f"task solver failed: {event.data.get('error')}")
        
        async def track_success(event: GameEvent):
            success_events.append(event.data)
        
        event_bus.subscribe("path_analysis_failed", track_errors)
        event_bus.subscribe("shortest_paths_found", track_success)
        event_bus.subscribe("move_completed", solver_handler.handle_move_completed)
        
        # Create move event with invalid/non-existent pages
        test_config = GameConfig(
            start_page_title="NonExistentStartPage123456",
            target_page_title="NonExistentTargetPage123456",
            max_steps=10
        )
        
        invalid_page = Page(
            title="NonExistentCurrentPage123456",
            url="https://en.wikipedia.org/wiki/NonExistentCurrentPage123456",
            text="This page doesn't exist",
            links=[]
        )
        
        test_game_state = GameState(
            game_id="test_error_game",
            config=test_config,
            current_page=invalid_page,
            status=GameStatus.IN_PROGRESS,
            steps=1
        )
        
        test_move = Move(
            step=1,
            from_page_title="NonExistentStartPage123456",
            to_page_title="NonExistentCurrentPage123456"
        )
        
        move_event = GameEvent(
            type="move_completed",
            game_id="test_error_game",
            data={
                "game_state": test_game_state,
                "move": test_move
            }
        )
        
        await event_bus.publish(move_event)
        
        # Wait for analysis (which should fail)
        await asyncio.sleep(1.0)
        
        # Should have received error event (or possibly success with empty result)
        total_events = len(error_events) + len(success_events)
        assert total_events > 0, "No events received for error case"
        
        if error_events:
            error = error_events[0]
            assert "error" in error
            logger.info(f"Error properly handled: {error['error']}")
        else:
            logger.info("Solver handled non-existent pages gracefully")
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_concurrent_path_analysis(
        self,
        event_bus: EventBus,
        solver_handler: SolverHandler
    ):
        """Test multiple concurrent path analyses."""
        analysis_results = []
        
        async def track_analysis(event: GameEvent):
            analysis_results.append(event.data)
            logger.info(f"Analysis completed for game {event.game_id}")
        
        event_bus.subscribe("shortest_paths_found", track_analysis)
        event_bus.subscribe("move_completed", solver_handler.handle_move_completed)
        
        # Create multiple move events for different games
        test_games = [
            ("game1", "Python (programming language)", "JavaScript"),
            ("game2", "Computer science", "Programming language"),
            ("game3", "Software engineering", "Computer programming")
        ]
        
        # Publish all events at once
        for game_id, from_page, to_page in test_games:
            config = GameConfig(
                start_page_title=from_page,
                target_page_title=to_page,
                max_steps=10
            )
            
            current_page = Page(
                title=from_page,
                url=f"https://en.wikipedia.org/wiki/{from_page.replace(' ', '_')}",
                text="Test content",
                links=[to_page]
            )
            
            game_state = GameState(
                game_id=game_id,
                config=config,
                current_page=current_page,
                status=GameStatus.IN_PROGRESS,
                steps=1
            )
            
            move = Move(step=1, from_page_title=from_page, to_page_title=from_page)
            
            move_event = GameEvent(
                type="move_completed",
                game_id=game_id,
                data={"game_state": game_state, "move": move}
            )
            
            await event_bus.publish(move_event)
        
        # Wait for all analyses to complete
        await asyncio.sleep(2.0)
        
        # Should have results for all games
        game_ids = [result["game_id"] for result in analysis_results]
        expected_ids = ["game1", "game2", "game3"]
        
        for expected_id in expected_ids:
            assert expected_id in game_ids, f"Missing result for {expected_id}"
        
        assert len(analysis_results) >= 3, f"Expected at least 3 results, got {len(analysis_results)}" 