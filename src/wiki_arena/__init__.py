"""
Wiki Arena - Core Library

A standalone Python package containing all the logic required to run and analyze 
a Wikipedia navigation game.
"""

from .events import EventBus, GameEvent

__all__ = ['EventBus', 'GameEvent']
