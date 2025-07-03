"""
Backend event handlers.

Handlers are stateless functions that react to events emitted by the core library.
Each handler has a single responsibility (WebSocket broadcasting, task solver, etc.).
"""

from .websocket_handler import WebSocketHandler
from .solver_handler import SolverHandler
from .storage_handler import StorageHandler

__all__ = ['WebSocketHandler', 'SolverHandler', 'StorageHandler'] 