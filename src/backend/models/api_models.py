from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum

# API Request Models
class StartGameRequest(BaseModel):
    """Request to start a new game."""
    start_page: str = Field(..., description="Starting Wikipedia page title")
    target_page: str = Field(..., description="Target Wikipedia page title")
    max_steps: int = Field(30, description="Maximum number of steps allowed")
    model_provider: str = Field("random", description="Model provider (anthropic, openai, random)")
    model_name: str = Field("random", description="Specific model name")

# API Response Models
class StartGameResponse(BaseModel):
    """Response when starting a new game."""
    game_id: str
    message: str
    # Note: We'll embed the full GameState from core library directly

class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: Optional[str] = None
    game_id: Optional[str] = None
