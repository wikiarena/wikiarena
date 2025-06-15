from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field, field_validator
from enum import Enum

# Task Strategy Models
class TaskStrategyType(str, Enum):
    """Types of task selection strategies."""
    RANDOM = "random"
    CUSTOM = "custom"
    RANKED = "ranked"       # Future: based on player skill
    THEMED = "themed"       # Future: within specific categories
    CAMPAIGN = "campaign"   # Future: sequential difficulty
    TOURNAMENT = "tournament"  # Future: same task for all players

class RandomTaskStrategy(BaseModel):
    """Strategy for randomly selected tasks."""
    type: TaskStrategyType = TaskStrategyType.RANDOM
    language: str = Field("en", description="Wikipedia language edition")
    max_retries: int = Field(3, description="Maximum retries for finding valid task")
    excluded_prefixes: Optional[List[str]] = Field(None, description="Page prefixes to exclude")

class CustomTaskStrategy(BaseModel):
    """Strategy for user-specified tasks."""
    type: TaskStrategyType = TaskStrategyType.CUSTOM
    start_page: str = Field(..., description="Starting Wikipedia page title")
    target_page: str = Field(..., description="Target Wikipedia page title")
    
    @field_validator("target_page")
    @classmethod
    def pages_must_be_different(cls, v: str, info):
        if hasattr(info, 'data') and 'start_page' in info.data and v == info.data['start_page']:
            raise ValueError("Start and target pages must be different")
        return v

# class RankedTaskStrategy(BaseModel):
#     """Strategy for skill-based task selection (future implementation)."""
#     type: TaskStrategyType = TaskStrategyType.RANKED
#     player_skill_level: int = Field(1, ge=1, le=10, description="Player skill level 1-10")
#     difficulty_preference: str = Field("balanced", description="easy, balanced, or hard")

# class ThemedTaskStrategy(BaseModel):
#     """Strategy for category-based task selection (future implementation)."""
#     type: TaskStrategyType = TaskStrategyType.THEMED
#     theme: str = Field(..., description="Wikipedia category or theme")
#     difficulty: str = Field("any", description="Difficulty preference")

# Union type for all task strategies  
TaskStrategy = Union[
    RandomTaskStrategy,
    CustomTaskStrategy,
]

# API Request Models
class StartGameRequest(BaseModel):
    """Request to start a new game with flexible task selection."""
    task_strategy: TaskStrategy = Field(..., description="How to select the start/target pages")
    max_steps: int = Field(30, description="Maximum number of steps allowed")
    model_provider: str = Field("random", description="Model provider (anthropic, openai, random)")
    model_name: str = Field("random", description="Specific model name")

# API Response Models
class StartGameResponse(BaseModel):
    """Response when starting a new game."""
    game_id: str
    message: str
    task_info: Dict[str, str] = Field(..., description="Information about the selected task")
    # Note: We'll embed the full GameState from core library directly

class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: Optional[str] = None
    game_id: Optional[str] = None
