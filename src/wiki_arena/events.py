import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Callable, Awaitable, Any, Optional
from collections import defaultdict
from pydantic import BaseModel, Field

class GameEvent(BaseModel):
    """Event emitted during game execution."""
    type: str = Field(..., min_length=1, description="Event type identifier (e.g., 'move_completed', 'game_ended')")
    game_id: str = Field(..., min_length=1, description="Unique identifier for the game")
    data: Dict[str, Any] = Field(..., description="Event payload containing relevant event data")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the event was created")
    
    class Config:
        # Allow arbitrary types in data field (for Move, GameState objects)
        arbitrary_types_allowed = True
        # Use enum values for serialization
        use_enum_values = True

class EventBus:
    """
    Simple event bus for coordinating between game execution and backend services.
    
    Supports async event handlers with error isolation - if one handler fails,
    others continue to run.
    """
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[GameEvent], Awaitable[None]]]] = defaultdict(list)
        self.logger = logging.getLogger(__name__)
    
    def subscribe(self, event_type: str, handler: Callable[[GameEvent], Awaitable[None]]):
        """Subscribe a handler to an event type."""
        self._subscribers[event_type].append(handler)
        self.logger.debug(f"Subscribed handler to {event_type}")
    
    async def publish(self, event: GameEvent):
        """Publish an event to all subscribers."""
        handlers = self._subscribers[event.type]
        if not handlers:
            self.logger.debug(f"No subscribers for event type: {event.type}")
            return
            
        self.logger.debug(f"Publishing {event.type} to {len(handlers)} handlers")
        
        # Run all handlers concurrently with error isolation
        results = await asyncio.gather(
            *[self._safe_handle(handler, event) for handler in handlers],
            return_exceptions=True
        )
        
        # Log any errors but don't fail the publish operation
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"Event handler {i} failed for {event.type}: {result}")
    
    async def _safe_handle(self, handler: Callable, event: GameEvent):
        """Run a handler with error isolation."""
        try:
            await handler(event)
        except Exception as e:
            self.logger.error(f"Handler {handler.__name__} failed: {e}", exc_info=True)
            raise  # Re-raise so gather() can catch it as exception
    
    def get_subscriber_count(self, event_type: str) -> int:
        """Get number of subscribers for an event type (useful for testing)."""
        return len(self._subscribers[event_type]) 