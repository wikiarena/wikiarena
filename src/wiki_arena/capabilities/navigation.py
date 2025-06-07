"""
Navigation Capability Interface

Defines what the game needs for navigation functionality without coupling
to specific MCP tools or implementation details.
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from dataclasses import dataclass

from wiki_arena.data_models.game_models import Page


@dataclass
class NavigationResult:
    """Result of a navigation operation."""
    success: bool
    page: Optional[Page] = None
    error_message: Optional[str] = None
    
    @property
    def is_success(self) -> bool:
        return self.success and self.page is not None


class INavigationCapability(ABC):
    """
    Navigation capability interface.
    
    This defines what the game logic needs for navigation without specifying
    how it's implemented (text-based tools, computer use, etc.).
    """
    
    @abstractmethod
    async def navigate_to_page(self, page_title: str) -> NavigationResult:
        """
        Navigate to a Wikipedia page and return page information.
        
        Args:
            page_title: The title of the page to navigate to
            
        Returns:
            NavigationResult containing the page data or error information
        """
        pass
    
    @abstractmethod
    async def get_capability_info(self) -> dict:
        """
        Get information about this navigation capability.
        
        Returns:
            Dictionary with capability metadata (implementation type, features, etc.)
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if this navigation capability is currently available.
        
        Returns:
            True if the capability can be used, False otherwise
        """
        pass 