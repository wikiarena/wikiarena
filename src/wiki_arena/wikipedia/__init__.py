"""
Wikipedia module for Wiki Arena.

This module contains functionality for interacting with Wikipedia,
including page selection and content sourcing for games.
"""

from .live_service import LiveWikiService
from .task_selector import (
    get_random_task,
    get_random_task_async,
    WikipediaTaskSelector
)

__all__ = [
    'LiveWikiService',
    'get_random_task',
    'get_random_task_async',
    'WikipediaTaskSelector'
] 