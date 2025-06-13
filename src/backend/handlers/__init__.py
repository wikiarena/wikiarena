"""
Backend event handlers.

Handlers are stateless functions that react to events emitted by the core library.
Each handler has a single responsibility (WebSocket broadcasting, task solver, etc.).
"""

from .websocket_handler import WebSocketHandler
from .optimal_path_handler import OptimalPathHandler

__all__ = ['WebSocketHandler', 'OptimalPathHandler'] 