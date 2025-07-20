from typing import List, Dict, Any, Optional, Union, Literal
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
    start_page: Optional[str] = Field(None, description="Starting Wikipedia page title (optional - will be randomly selected if not provided)")
    target_page: Optional[str] = Field(None, description="Target Wikipedia page title (optional - will be randomly selected if not provided)")
    language: str = Field("en", description="Wikipedia language edition")
    max_retries: int = Field(3, description="Maximum retries for finding valid pages")
    
    @field_validator("target_page")
    @classmethod
    def pages_must_be_different(cls, v: Optional[str], info):
        if v and hasattr(info, 'data') and info.data.get('start_page') and v == info.data['start_page']:
            raise ValueError("Start and target pages must be different")
        return v
    
    @field_validator("start_page", "target_page")
    @classmethod
    def pages_must_be_non_empty_if_provided(cls, v: Optional[str]):
        if v is not None and not v.strip():
            raise ValueError("Page titles must be non-empty if provided")
        return v.strip() if v else None

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

# Game Configuration Models
class CreateTaskRequest(BaseModel):
    """Request to create a new task with multiple competing games."""
    task_strategy: TaskStrategy = Field(..., description="How to select the start/target pages")
    model_ids: List[str] = Field(..., description="An ordered list of model IDs to compete in the task")
    max_steps: int = Field(30, description="Maximum number of steps allowed per game")

class ModelInfoResponse(BaseModel):
    """A slimmed-down model definition for the frontend."""
    id: str = Field(..., description="The unique identifier for the model, e.g., 'anthropic/claude-3-opus-20240229'")
    name: str = Field(..., description="The human-readable name of the model, e.g., 'Claude 3 Opus'")
    provider: str = Field(..., description="The name of the provider, e.g., 'Anthropic'")
    icon_slug: str = Field(..., description="The LobeHub icon slug for the model provider, e.g., 'claude'.")
    created: int = Field(..., description="The unix timestamp when the model was added to OpenRouter.")
    input_cost_per_1m_tokens: float = Field(..., description="Cost per 1M input tokens in USD.")
    output_cost_per_1m_tokens: float = Field(..., description="Cost per 1M output tokens in USD.")

# TODO(hunter): rename to PlayerResponse?
class Player(BaseModel):
    """Information about a single game created within a task."""
    game_id: str
    model: ModelInfoResponse

class CreateTaskResponse(BaseModel):
    """Response for a successful task creation."""
    task_id: str
    start_page: str
    target_page: str
    players: List[Player]

class ErrorResponse(BaseModel):
    """Standard error response format."""
    detail: str
