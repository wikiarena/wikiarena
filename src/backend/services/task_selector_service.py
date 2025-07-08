"""
Task Selector Service for Backend API

This service provides a unified interface for task selection strategies,
integrating the existing wiki_arena task selection infrastructure.
"""

import logging
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod

from wiki_arena.models import Task
from wiki_arena.wikipedia.task_selector import get_random_task_async
from wiki_arena.wikipedia.live_service import LiveWikiService
from wiki_arena.wikipedia.task_selector import WikipediaTaskSelector
from backend.models.api_models import (
    TaskStrategy,
    TaskStrategyType,
    RandomTaskStrategy,
    CustomTaskStrategy,
)

logger = logging.getLogger(__name__)

class TaskSelector(ABC):
    """Abstract base class for task selection strategies."""
    
    @abstractmethod
    async def select_task(self) -> Optional[Task]:
        """Select a task based on the strategy."""
        pass
    
    @abstractmethod
    def get_strategy_info(self) -> Dict[str, str]:
        """Get information about this strategy for API responses."""
        pass

class RandomTaskSelector(TaskSelector):
    """Selector for random Wikipedia tasks."""
    
    def __init__(self, strategy: RandomTaskStrategy):
        self.strategy = strategy
    
    async def select_task(self) -> Optional[Task]:
        """Select a random task using the existing infrastructure."""
        logger.info(f"Selecting random task (language: {self.strategy.language})")
        
        # Convert excluded_prefixes to set if provided
        excluded_prefixes = None
        if self.strategy.excluded_prefixes:
            excluded_prefixes = set(self.strategy.excluded_prefixes)
        
        task = await get_random_task_async(
            language=self.strategy.language,
            max_retries=self.strategy.max_retries,
            excluded_prefixes=excluded_prefixes
        )
        
        if task:
            logger.info(f"Selected random task: {task.start_page_title} → {task.target_page_title}")
        else:
            logger.error("Failed to select random task")
        
        return task
    
    def get_strategy_info(self) -> Dict[str, str]:
        return {
            "strategy": "random",
            "language": self.strategy.language,
            "description": f"Randomly selected from {self.strategy.language} Wikipedia"
        }

class CustomTaskSelector(TaskSelector):
    """Selector for user-specified tasks."""
    
    def __init__(self, strategy: CustomTaskStrategy):
        self.strategy = strategy
        self.wiki = LiveWikiService(language=strategy.language)
    
    async def _validate_page_exists(self, page_title: str) -> bool:
        """Validate that a page exists on Wikipedia."""
        try:
            await self.wiki.get_page(page_title, include_all_namespaces=True)
            return True
        except ValueError:
            # Page doesn't exist
            return False
        except Exception as e:
            logger.error(f"Error validating page '{page_title}': {e}")
            return False
    
    async def _find_random_start_page(self, exclude_page: Optional[str] = None) -> Optional[str]:
        """Find a random page that can serve as a valid start page (has outgoing links)."""
        selector = WikipediaTaskSelector(
            live_wiki_service=self.wiki,
            max_retries=self.strategy.max_retries
        )
        
        for attempt in range(self.strategy.max_retries):
            try:
                # Get random pages and find a valid start page
                random_pages = await self.wiki.get_random_pages(count=20)
                valid_pages = [
                    page for page in random_pages 
                    if selector._is_valid_page_title(page) and page != exclude_page
                ]
                
                start_page = await selector._find_valid_start_page(valid_pages)
                if start_page:
                    return start_page
                    
            except Exception as e:
                logger.warning(f"Error in attempt {attempt + 1} to find random start page: {e}")
        
        return None
    
    async def _find_random_target_page(self, exclude_page: Optional[str] = None) -> Optional[str]:
        """Find a random page that can serve as a valid target page (has incoming links)."""
        selector = WikipediaTaskSelector(
            live_wiki_service=self.wiki,
            max_retries=self.strategy.max_retries
        )
        
        for attempt in range(self.strategy.max_retries):
            try:
                # Get random pages and find a valid target page
                random_pages = await self.wiki.get_random_pages(count=20)
                valid_pages = [
                    page for page in random_pages 
                    if selector._is_valid_page_title(page) and page != exclude_page
                ]
                
                target_page = await selector._find_valid_target_page(valid_pages, exclude_page=exclude_page or "")
                if target_page:
                    return target_page
                    
            except Exception as e:
                logger.warning(f"Error in attempt {attempt + 1} to find random target page: {e}")
        
        return None
    
    async def select_task(self) -> Optional[Task]:
        """Create a task from user-specified pages, with validation and random fallback."""
        logger.info(f"Creating custom task: {self.strategy.start_page} → {self.strategy.target_page}")
        
        # Handle start page - validate if provided, otherwise find random
        if self.strategy.start_page:
            if not await self._validate_page_exists(self.strategy.start_page):
                logger.error(f"Start page '{self.strategy.start_page}' does not exist")
                return None
            
            if not await self.wiki.has_outgoing_links(self.strategy.start_page):
                logger.error(f"Start page '{self.strategy.start_page}' has no outgoing links - cannot be used for game")
                return None
            
            start_page = self.strategy.start_page
        else:
            start_page = await self._find_random_start_page()
            if not start_page:
                logger.error("Failed to find suitable random start page")
                return None
        
        # Handle target page - validate if provided, otherwise find random
        if self.strategy.target_page:
            if not await self._validate_page_exists(self.strategy.target_page):
                logger.error(f"Target page '{self.strategy.target_page}' does not exist")
                return None
            
            if not await self.wiki.has_incoming_links(self.strategy.target_page):
                logger.error(f"Target page '{self.strategy.target_page}' has no incoming links - cannot be used for game")
                return None
            
            target_page = self.strategy.target_page
        else:
            target_page = await self._find_random_target_page(exclude_page=start_page)
            if not target_page:
                logger.error("Failed to find suitable random target page")
                return None
        
        # Ensure pages are different (shouldn't happen due to exclusion logic, but safety check)
        if start_page == target_page:
            logger.error(f"Start and target pages are the same: '{start_page}'")
            return None
        
        task = Task(start_page_title=start_page, target_page_title=target_page)
        
        # Log the result type for clarity
        start_type = "custom" if self.strategy.start_page else "random"
        target_type = "custom" if self.strategy.target_page else "random"
        logger.info(f"Created task: {start_page} ({start_type}) → {target_page} ({target_type})")
        
        return task
    
    def get_strategy_info(self) -> Dict[str, str]:
        info = {
            "strategy": "custom",
            "language": self.strategy.language,
            "description": "User-specified task with validation and random fallback"
        }
        
        if self.strategy.start_page:
            info["start_page"] = self.strategy.start_page
        else:
            info["start_page"] = "random"
            
        if self.strategy.target_page:
            info["target_page"] = self.strategy.target_page
        else:
            info["target_page"] = "random"
            
        return info

class TaskSelectorService:
    """Main service for task selection."""
    
    def __init__(self):
        self.selectors = {
            TaskStrategyType.RANDOM: RandomTaskSelector,
            TaskStrategyType.CUSTOM: CustomTaskSelector,
        }
    
    async def select_task(self, strategy: TaskStrategy) -> Optional[Task]:
        """Select a task using the specified strategy."""
        logger.info(f"Selecting task with strategy: {strategy.type}")
        
        selector_class = self.selectors.get(strategy.type)
        if not selector_class:
            logger.error(f"Unknown task strategy: {strategy.type}")
            return None
        
        selector = selector_class(strategy)
        return await selector.select_task()
    
    def get_strategy_info(self, strategy: TaskStrategy) -> Dict[str, str]:
        """Get information about the strategy for API responses."""
        selector_class = self.selectors.get(strategy.type)
        if not selector_class:
            return {"strategy": "unknown", "description": "Unknown strategy"}
        
        selector = selector_class(strategy)
        return selector.get_strategy_info()

# Global service instance
task_selector_service = TaskSelectorService() 