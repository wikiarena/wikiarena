"""
Wikipedia module for Wiki Arena.

This module contains functionality for interacting with Wikipedia,
including page selection and content sourcing for games.
"""

from .page_selector import (
    PagePair,
    LinkValidationConfig,
    WikipediaPageSelector,
    get_random_page_pair,
    get_random_page_pair_async
)

__all__ = [
    'PagePair',
    'LinkValidationConfig', 
    'WikipediaPageSelector',
    'get_random_page_pair',
    'get_random_page_pair_async'
] 