"""
Level 3: WebSocketHandler Integration Tests (pytest version)
Testing WebSocket event handler with REAL GameWebSocketManager and WebSocketHandler.
NO MOCKS - Uses real backend components with minimal test WebSocket implementation.
"""

import pytest
import asyncio
import json
import logging
import sys
import os

# Add src directory to path for imports  
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../src'))

from wiki_arena import EventBus, GameEvent
from wiki_arena.types import GameState, GameConfig, ModelConfig, Page, Move, GameStatus
from backend.handlers.websocket_handler import WebSocketHandler
from backend.websockets.game_hub import GameWebSocketManager

logger = logging.getLogger(__name__)

class MockWebSocket:
    """Minimal WebSocket implementation that mimics FastAPI WebSocket interface."""
    
    def __init__(self, game_id: str):
        self.game_id = game_id
        self.messages = []
        self.connected = False
        
    async def accept(self):
        """Accept the WebSocket connection."""
        self.connected = True
        logger.debug(f"Test WebSocket accepted for game {self.game_id}")
        
    async def send_text(self, message: str):
        """Store sent messages for verification."""
        if self.connected:
            self.messages.append(message)
            logger.debug(f"Test WebSocket sent: {message[:100]}...")
        else:
            raise Exception("WebSocket not connected")
            
    async def receive_text(self):
        """Mock receive - not used in these tests."""
        await asyncio.sleep(10)
        return "test"
    
    def get_messages(self):
        """Get all messages sent to this WebSocket."""
        return self.messages
    
    def get_last_message_data(self):
        """Get the last message as parsed JSON."""
        if self.messages:
            return json.loads(self.messages[-1])
        return None
    
    def clear_messages(self):
        """Clear all received messages."""
        self.messages.clear()

@pytest.mark.integration 
class TestWebSocketHandler:
    """Integration tests for WebSocketHandler with real components."""
    
    @pytest.fixture
    async def websocket_manager(self):
        """Create a real GameWebSocketManager for testing."""
        manager = GameWebSocketManager()
        yield manager
        # Cleanup: disconnect any remaining connections
        for game_id in list(manager.game_connections.keys()):
            connections = list(manager.game_connections[game_id])
            for ws in connections:
                await manager.disconnect(ws)
    
    @pytest.fixture
    def websocket_handler(self, websocket_manager):
        """Create a real WebSocketHandler with patched manager."""
        handler = WebSocketHandler()
        
        # Patch the global websocket_manager
        import backend.handlers.websocket_handler as handler_module
        original_manager = handler_module.websocket_manager
        handler_module.websocket_manager = websocket_manager
        
        yield handler
        
        # Restore original manager
        handler_module.websocket_manager = original_manager
    
    @pytest.fixture
    async def connected_websocket(self, websocket_manager):
        """Create and connect a test WebSocket."""
        game_id = "test_game"
        test_ws = MockWebSocket(game_id)
        await websocket_manager.connect(test_ws, game_id)
        
        # Clear connection message
        test_ws.clear_messages()
        
        yield test_ws, game_id
        
        # Cleanup
        await websocket_manager.disconnect(test_ws)
    
    @pytest.mark.asyncio
    async def test_websocket_manager_connection_lifecycle(self, websocket_manager):
        """Test real GameWebSocketManager connection and disconnection."""
        game_id = "lifecycle_test"
        
        # Initially no connections
        assert websocket_manager.get_connection_count(game_id) == 0
        
        # Create and connect test WebSocket
        test_ws = MockWebSocket(game_id)
        await websocket_manager.connect(test_ws, game_id)
        
        # Should have one connection
        assert websocket_manager.get_connection_count(game_id) == 1
        assert game_id in websocket_manager.get_all_games()
        
        # Should receive connection_established message
        messages = test_ws.get_messages()
        assert len(messages) == 1
        data = json.loads(messages[0])
        assert data["type"] == "CONNECTION_ESTABLISHED"
        # Note: game_id is not included in CONNECTION_ESTABLISHED message (it's in the URL)
        
        # Disconnect
        await websocket_manager.disconnect(test_ws)
        
        # Should be cleaned up
        assert websocket_manager.get_connection_count(game_id) == 0
    
    @pytest.mark.asyncio
    async def test_multiple_connections_same_game(self, websocket_manager):
        """Test multiple WebSocket connections to the same game."""
        game_id = "multi_conn_test"
        
        # Create multiple connections
        ws1 = MockWebSocket(game_id)  
        ws2 = MockWebSocket(game_id)
        
        await websocket_manager.connect(ws1, game_id)
        await websocket_manager.connect(ws2, game_id)
        
        # Should have 2 connections
        assert websocket_manager.get_connection_count(game_id) == 2
        
        # Both should receive connection messages
        assert len(ws1.get_messages()) == 1
        assert len(ws2.get_messages()) == 1
        
        # Clean up
        await websocket_manager.disconnect(ws1)
        await websocket_manager.disconnect(ws2)
        
        assert websocket_manager.get_connection_count(game_id) == 0
    
    @pytest.mark.asyncio
    async def test_websocket_handler_move_completed_broadcast(
        self, 
        websocket_handler, 
        connected_websocket,
        sample_game_state,
        sample_move
    ):
        """Test WebSocketHandler broadcasting move_completed events."""
        test_ws, game_id = connected_websocket
        
        # Create move_completed event
        move_event = GameEvent(
            type="move_completed",
            game_id=game_id,
            data={
                "game_state": sample_game_state,
                "move": sample_move,
            }
        )
        
        # Process through real handler
        await websocket_handler.handle_move_completed(move_event)
        
        # Should receive GAME_MOVE_COMPLETED message
        messages = test_ws.get_messages()
        assert len(messages) == 1
        
        data = json.loads(messages[0])
        assert data["type"] == "GAME_MOVE_COMPLETED"
        assert data["game_id"] == game_id
        assert data["current_page"]["title"] == "Programming language"
        assert data["steps"] == 1
        assert data["status"] == "in_progress"
        
        # Verify move data structure
        move_data = data["move"]
        assert move_data["step"] == 1
        assert move_data["from_page_title"] == "Python (programming language)"
        assert move_data["to_page_title"] == "Programming language"
    
    @pytest.mark.asyncio
    async def test_websocket_handler_shortest_paths_broadcast(
        self,
        websocket_handler,
        connected_websocket
    ):
        """Test WebSocketHandler broadcasting shortest_paths_found events."""
        test_ws, game_id = connected_websocket
        
        # Create shortest_paths_found event
        paths_event = GameEvent(
            type="shortest_paths_found",
            game_id=game_id,
            data={
                "shortest_paths": [["Python (programming language)", "Programming language", "JavaScript"]],
                "shortest_path_length": 3,
            }
        )
        
        # Process through real handler
        await websocket_handler.handle_shortest_paths_found(paths_event)
        
        # Should receive SHORTEST_PATHS_UPDATED message
        messages = test_ws.get_messages()
        assert len(messages) == 1
        
        data = json.loads(messages[0])
        assert data["type"] == "OPTIMAL_PATHS_UPDATED"
        assert data["game_id"] == game_id
        assert data["optimal_paths"] == [["Python (programming language)", "Programming language", "JavaScript"]]
        assert data["optimal_path_length"] == 3
    
    @pytest.mark.asyncio
    async def test_websocket_handler_game_ended_broadcast(
        self,
        websocket_handler,
        connected_websocket,
        sample_game_config
    ):
        """Test WebSocketHandler broadcasting game_ended events.""" 
        test_ws, game_id = connected_websocket
        
        # Create ended game state
        ended_page = Page(
            title="JavaScript",
            url="https://en.wikipedia.org/wiki/JavaScript", 
            text="JavaScript is a programming language...",
            links=[]
        )
        
        ended_state = GameState(
            game_id=game_id,
            config=sample_game_config,
            current_page=ended_page,
            status=GameStatus.WON,
            steps=3
        )
        
        # Create game_ended event
        end_event = GameEvent(
            type="game_ended",
            game_id=game_id,
            data={"game_state": ended_state}
        )
        
        # Process through real handler
        await websocket_handler.handle_game_ended(end_event)
        
        # Should receive GAME_ENDED message
        messages = test_ws.get_messages()
        assert len(messages) == 1
        
        data = json.loads(messages[0])
        assert data["type"] == "GAME_ENDED"
        assert data["game_id"] == game_id
        assert data["final_status"] == "won"
        assert data["total_steps"] == 3
    
    @pytest.mark.asyncio
    async def test_broadcast_isolation_between_games(
        self,
        websocket_handler,
        websocket_manager
    ):
        """Test that broadcasts are isolated between different games."""
        game_1 = "isolation_game_1"
        game_2 = "isolation_game_2"
        
        # Connect WebSockets to different games
        ws1 = MockWebSocket(game_1)
        ws2 = MockWebSocket(game_2)
        
        await websocket_manager.connect(ws1, game_1)
        await websocket_manager.connect(ws2, game_2)
        
        # Clear connection messages
        ws1.clear_messages()
        ws2.clear_messages()
        
        # Create event for game_1 only
        paths_event = GameEvent(
            type="shortest_paths_found",
            game_id=game_1,  # Only game_1
            data={
                "shortest_paths": [["A", "B", "C"]],
                "shortest_path_length": 3
            }
        )
        
        # Process event
        await websocket_handler.handle_shortest_paths_found(paths_event)
        
        # Only ws1 should receive message
        assert len(ws1.get_messages()) == 1
        assert len(ws2.get_messages()) == 0
        
        # Verify ws1 got the right message
        data = ws1.get_last_message_data()
        assert data["type"] == "OPTIMAL_PATHS_UPDATED"
        assert data["game_id"] == game_1
        
        # Clean up
        await websocket_manager.disconnect(ws1)
        await websocket_manager.disconnect(ws2)
    
    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_connections_same_game(
        self,
        websocket_handler,
        websocket_manager
    ):
        """Test broadcasting to multiple connections on the same game."""
        game_id = "multi_broadcast_test"
        
        # Connect multiple WebSockets to same game
        ws1 = MockWebSocket(game_id)
        ws2 = MockWebSocket(game_id)
        
        await websocket_manager.connect(ws1, game_id)
        await websocket_manager.connect(ws2, game_id)
        
        # Clear connection messages
        ws1.clear_messages()
        ws2.clear_messages()
        
        # Create event
        paths_event = GameEvent(
            type="shortest_paths_found",
            game_id=game_id,
            data={
                "shortest_paths": [["Multi", "Broadcast", "Test"]],
                "shortest_path_length": 3
            }
        )
        
        # Process event
        await websocket_handler.handle_shortest_paths_found(paths_event)
        
        # Both WebSockets should receive message
        assert len(ws1.get_messages()) == 1
        assert len(ws2.get_messages()) == 1
        
        # Both should have same message content
        data1 = ws1.get_last_message_data()
        data2 = ws2.get_last_message_data()
        
        assert data1["type"] == data2["type"] == "OPTIMAL_PATHS_UPDATED"
        assert data1["game_id"] == data2["game_id"] == game_id
        assert data1["optimal_paths"] == data2["optimal_paths"]
        
        # Clean up
        await websocket_manager.disconnect(ws1)
        await websocket_manager.disconnect(ws2)
    
    @pytest.mark.asyncio
    async def test_websocket_message_serialization(
        self,
        websocket_handler,
        connected_websocket,
        sample_game_state,
        sample_move
    ):
        """Test that WebSocket messages are properly JSON serialized."""
        test_ws, game_id = connected_websocket
        
        # Create move event with complex nested data
        move_event = GameEvent(
            type="move_completed",
            game_id=game_id,
            data={
                "game_state": sample_game_state,
                "move": sample_move,
            }
        )
        
        # Process event
        await websocket_handler.handle_move_completed(move_event)
        
        # Should receive properly serialized JSON
        messages = test_ws.get_messages()
        assert len(messages) == 1
        
        # Should be valid JSON
        data = json.loads(messages[0])
        
        # Should contain move timestamp (even if None)
        assert "timestamp" in data["move"]
        assert data["game_id"] == game_id
        
        # Should preserve all original data structure
        assert data["type"] == "GAME_MOVE_COMPLETED"
        assert isinstance(data["move"], dict)
        assert isinstance(data["steps"], int)