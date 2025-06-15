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
    
    async def select_task(self) -> Optional[Task]:
        """Create a task from user-specified pages."""
        logger.info(f"Creating custom task: {self.strategy.start_page} → {self.strategy.target_page}")
        
        # TODO: Add validation that pages exist and are reachable
        # For now, create the task directly
        task = Task(
            start_page_title=self.strategy.start_page,
            target_page_title=self.strategy.target_page
        )
        
        return task
    
    def get_strategy_info(self) -> Dict[str, str]:
        return {
            "strategy": "custom",
            "start_page": self.strategy.start_page,
            "target_page": self.strategy.target_page,
            "description": "User-specified start and target pages"
        }

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