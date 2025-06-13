"""
Level 1: EventBus Tests (pytest version)
Testing the core event system with NO external dependencies.
"""

import pytest
import asyncio
import logging

from wiki_arena import EventBus, GameEvent

logger = logging.getLogger(__name__)

@pytest.mark.unit
class TestEventBus:
    """Unit tests for EventBus functionality."""
    
    @pytest.mark.asyncio
    async def test_basic_event_flow(self, event_bus: EventBus):
        """Test basic publish/subscribe functionality."""
        received_events = []
        
        async def test_handler(event: GameEvent):
            received_events.append(event)
            logger.info(f"Handler received event: {event.type} for game {event.game_id}")
        
        # Subscribe handler
        event_bus.subscribe("test_event", test_handler)
        
        # Publish event
        test_event = GameEvent(
            type="test_event",
            game_id="test_game_123",
            data={"message": "hello world", "step": 1}
        )
        
        await event_bus.publish(test_event)
        
        # Verify event was received
        assert len(received_events) == 1
        assert received_events[0].type == "test_event"
        assert received_events[0].game_id == "test_game_123"
        assert received_events[0].data["message"] == "hello world"
    
    @pytest.mark.asyncio
    async def test_multiple_handlers(self, event_bus: EventBus):
        """Test multiple handlers for same event type."""
        handler1_calls = []
        handler2_calls = []
        
        async def handler1(event: GameEvent):
            handler1_calls.append(event.game_id)
            logger.info(f"Handler 1 called for game {event.game_id}")
        
        async def handler2(event: GameEvent):
            handler2_calls.append(event.game_id)
            logger.info(f"Handler 2 called for game {event.game_id}")
        
        # Subscribe both handlers
        event_bus.subscribe("multi_test", handler1)
        event_bus.subscribe("multi_test", handler2)
        
        # Publish event
        test_event = GameEvent(
            type="multi_test",
            game_id="multi_game_456",
            data={}
        )
        
        await event_bus.publish(test_event)
        
        # Both handlers should have been called
        assert len(handler1_calls) == 1
        assert len(handler2_calls) == 1
        assert handler1_calls[0] == "multi_game_456"
        assert handler2_calls[0] == "multi_game_456"
    
    @pytest.mark.asyncio
    async def test_error_isolation(self, event_bus: EventBus):
        """Test that handler errors don't affect other handlers."""
        good_handler_calls = []
        
        async def failing_handler(event: GameEvent):
            logger.info("Failing handler called (will raise error)")
            raise ValueError("Intentional test failure")
        
        async def good_handler(event: GameEvent):
            good_handler_calls.append(event.game_id)
            logger.info(f"Good handler successfully processed {event.game_id}")
        
        # Subscribe both handlers
        event_bus.subscribe("error_test", failing_handler)
        event_bus.subscribe("error_test", good_handler)
        
        # Publish event
        test_event = GameEvent(
            type="error_test", 
            game_id="error_game_789",
            data={}
        )
        
        await event_bus.publish(test_event)
        
        # Good handler should still have been called despite failing handler
        assert len(good_handler_calls) == 1
        assert good_handler_calls[0] == "error_game_789"
    
    @pytest.mark.asyncio
    async def test_no_subscribers(self, event_bus: EventBus):
        """Test publishing to event type with no subscribers."""
        # Publish event with no subscribers (should not error)
        test_event = GameEvent(
            type="no_subscribers",
            game_id="lonely_game",
            data={}
        )
        
        # Should not raise any exception
        await event_bus.publish(test_event)
    
    @pytest.mark.asyncio
    async def test_subscriber_count(self, event_bus: EventBus):
        """Test subscriber count utility."""
        async def dummy_handler(event: GameEvent):
            pass
        
        # Initially no subscribers
        assert event_bus.get_subscriber_count("count_test") == 0
        
        # Add one subscriber
        event_bus.subscribe("count_test", dummy_handler)
        assert event_bus.get_subscriber_count("count_test") == 1
        
        # Add another subscriber
        event_bus.subscribe("count_test", dummy_handler)
        assert event_bus.get_subscriber_count("count_test") == 2 