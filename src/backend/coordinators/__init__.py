"""
Backend coordinators.

Coordinators manage business object lifecycles and orchestrate between
the core wiki_arena library and the web layer.
"""

from .game_coordinator import GameCoordinator

__all__ = ['GameCoordinator'] 