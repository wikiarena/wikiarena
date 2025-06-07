from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

# API Request Models
class StartGameRequest(BaseModel):
    """Request to start a new game."""
    start_page: str = Field(..., description="Starting Wikipedia page title")
    target_page: str = Field(..., description="Target Wikipedia page title")
    max_steps: int = Field(30, description="Maximum number of steps allowed")
    model_provider: str = Field("random", description="Model provider (anthropic, openai, random)")
    model_name: str = Field("random", description="Specific model name")

# API Response Models
class GameConfigResponse(BaseModel):
    """Game configuration in API format."""
    start_page_title: str
    target_page_title: str
    max_steps: int
    model: Dict[str, Any]

class MoveResponse(BaseModel):
    """Single move in API format."""
    step: int
    from_page_title: str
    to_page_title: Optional[str] = None
    model_response: Optional[str] = None
    tool_call_attempt: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    timestamp: Optional[str] = None

class GameStateResponse(BaseModel):
    """Game state in API format - matches frontend GameState interface."""
    game_id: str
    status: str  # 'not_started' | 'in_progress' | 'won' | 'lost_max_steps' | 'lost_invalid_move' | 'error'
    steps: int
    start_page: str
    target_page: str
    current_page: Optional[str] = None
    moves: List[MoveResponse]
    start_timestamp: str
    end_timestamp: Optional[str] = None

class StartGameResponse(BaseModel):
    """Response when starting a new game."""
    game_id: str
    message: str
    game_state: GameStateResponse

class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: Optional[str] = None
    game_id: Optional[str] = None
