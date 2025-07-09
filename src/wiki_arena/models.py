from typing import List, Dict, Any, Optional, Type, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, field_validator, ValidationInfo

from wiki_arena.utils.wiki_helpers import get_sanitized_page_title

# --- Enums ---

class GameStatus(Enum):
    """Represents the current status of a game."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    WON = "won"
    LOST_MAX_STEPS = "lost_max_steps"
    LOST_INVALID_MOVE = "lost_invalid_move"
    ERROR = "error"

class ErrorType(Enum):
    """Categorizes different types of errors that can occur during gameplay."""
    # Model issues
    MODEL_NO_TOOL_CALL = "model_no_tool_call"
    MODEL_INVALID_TOOL = "model_invalid_tool"
    MODEL_INVALID_LINK = "model_invalid_link"
    MODEL_GENERATION_ERROR = "model_generation_error"
    
    # Provider infrastructure issues
    PROVIDER_API_ERROR = "provider_api_error"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_RATE_LIMIT = "provider_rate_limit"
    
    # Application bugs/issues
    APP_CAPABILITY_ERROR = "app_capability_error"
    APP_NAVIGATION_ERROR = "app_navigation_error"
    APP_UNKNOWN_ERROR = "app_unknown_error"

# --- Context Models ---

class ModelCallMetrics(BaseModel):
    """Metrics for a single model call."""
    input_tokens: Optional[int] = Field(0, description="Input tokens for this API call (uncached)")
    output_tokens: Optional[int] = Field(0, description="Output tokens for this API call")
    total_tokens: Optional[int] = Field(0, description="Total tokens for this API call (input + output)")
    cache_creation_input_tokens: Optional[int] = Field(0, description="Input tokens used to create a cache entry")
    cache_read_input_tokens: Optional[int] = Field(0, description="Input tokens read from a cache entry")
    estimated_cost_usd: Optional[float] = Field(0.0, description="Estimated cost for this API call in USD")
    response_time_ms: float = Field(0.0, description="API response time in milliseconds")
    request_timestamp: datetime = Field(default_factory=datetime.now, description="When this API call was made")

class MessageRole(str, Enum):
    """Represents the role of the author of a message."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

class AssistantToolCall(BaseModel):
    """A tool call requested by the assistant."""
    id: str = Field(..., description="A unique ID for this tool call, to be used in the tool response.")
    name: str = Field(..., description="The name of the tool to call.")
    arguments: Dict[str, Any] = Field(..., description="The arguments for the tool.")

class ToolResultMessage(BaseModel):
    """A message containing the result of a tool call."""
    role: MessageRole = Field(MessageRole.TOOL, frozen=True)
    tool_call_id: str = Field(..., description="The ID of the tool call this is a response to.")
    content: str = Field(..., description="The string result of the tool execution.")
    is_error: bool = Field(False, description="Whether the tool call resulted in an error.")

class AssistantMessage(BaseModel):
    """A message from the assistant, which can contain text and/or tool calls."""
    role: MessageRole = Field(MessageRole.ASSISTANT, frozen=True)
    content: Optional[str] = Field(None, description="The text content of the message.")
    tool_calls: Optional[List[AssistantToolCall]] = Field(None, description="A list of tool calls requested by the assistant.")
    metrics: Optional[ModelCallMetrics] = Field(None, description="Metrics for the API call that generated this message.")

class UserMessage(BaseModel):
    """A message from the user."""
    role: MessageRole = Field(MessageRole.USER, frozen=True)
    content: str

class SystemMessage(BaseModel):
    """A system message to set the context for the assistant."""
    role: MessageRole = Field(MessageRole.SYSTEM, frozen=True)
    content: str

# A concrete message in the context.
ContextMessage = Union[SystemMessage, UserMessage, AssistantMessage, ToolResultMessage]

# --- Data Models ---

class Task(BaseModel):
    """A task outlines the initial state and objective of a game."""
    start_page_title: str = Field(..., description="The title of the starting Wikipedia page.")
    target_page_title: str = Field(..., description="The title of the target Wikipedia page.")

    @field_validator("target_page_title")
    @classmethod
    def titles_must_be_different(cls, v: str, info: ValidationInfo):
        if "start_page_title" in info.data and v == info.data["start_page_title"]:
            raise ValueError("Start and target page titles must be different.")
        return v

    @property # NOTE: this may be confused with TaskCordinator's task_id, this one is used for Leaderboard
    def task_id(self) -> str:
        """Generate a unique task ID by concatenating sanitized start and target page titles."""
        start = get_sanitized_page_title(self.start_page_title)
        target = get_sanitized_page_title(self.target_page_title)
        return f"{start}__to__{target}"

class GameError(BaseModel):
    """Structured error information for analysis and debugging."""
    type: ErrorType = Field(..., description="The category of error that occurred.")
    message: str = Field(..., description="Human-readable error description.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context for analysis.")

DEFAULT_SYSTEM_PROMPT_TEMPLATE = (
    "You are in the Wiki Arena. Your goal is to navigate from the starting Wikipedia page to the target Wikipedia page "
    # "by only using the links (page titles) within the current page.\n"
    "using ONLY the content from the current page.\n"
    "Start Page: '{start_page_title}'\n"
    "Target Page: '{target_page_title}'\n\n"
    "Navigate one step closer to the target page by passing a page title on the current page to the tools provided for you.\n"
)

class ModelConfig(BaseModel):
    """Configuration for a specific language model."""
    provider: str = Field(..., description="Model provider: anthropic, openai, random")
    model_name: str = Field(..., description="Specific model name for the provider")
    settings: Dict[str, Any] = Field(default_factory=dict, description="Provider-specific settings")
    
    input_cost_per_1m_tokens: Optional[float] = Field(None, description="Cost per 1M input tokens in USD")
    output_cost_per_1m_tokens: Optional[float] = Field(None, description="Cost per 1M output tokens in USD")
    
class Page(BaseModel):
    """Represents a single Wikipedia page in the game."""
    title: str = Field(..., description="The title of the Wikipedia page.")
    url: str = Field(..., description="The URL of the Wikipedia page.")
    text: Optional[str] = Field(None, description="The text of the Wikipedia page.")
    # TODO(hunter): this should be a list of a defined type
    links: List[str] = Field([], description="A list of link texts found on the page.")

class GameConfig(BaseModel):
    """Holds the initial settings and configuration for a game."""
    start_page_title: str = Field(..., description="The title of the starting Wikipedia page.")
    target_page_title: str = Field(..., description="The title of the target Wikipedia page.")
    max_steps: int = Field(30, description="The maximum number of steps allowed for the game.")
    model: ModelConfig = Field(..., description="Language model configuration.")
    system_prompt_template: Optional[str] = Field(DEFAULT_SYSTEM_PROMPT_TEMPLATE, description="The system prompt for the language model.")
    # what should be in settings?
    # - system prompt? (or should this be in model settings so we can have multiple models with different system prompts?)
    #  - exact or template. if template should we have an id?
    
class Move(BaseModel):
    """Records a single step taken by a player."""
    step: int = Field(..., description="The sequential number of the step.")
    from_page_title: str = Field(..., description="The title of the page before this move.")
    to_page_title: Optional[str] = Field(None, description="The title of the page navigated to (if successful).")
    error: Optional[GameError] = Field(None, description="Structured error information if an error occurred during this step.")

class GameState(BaseModel):
    """Represents the dynamic state of a single ongoing or completed game."""
    config: GameConfig = Field(..., description="The configuration for this game.")
    current_page: Page = Field(..., description="Details of the page the language model is currently on.")
    move_history: List[Move] = Field([], description="A chronological list of moves made in the game.")
    context: List[ContextMessage] = Field([], description="A complete log of the conversation with the model.")
    steps: int = Field(0, description="The number of steps taken.")
    status: GameStatus = Field(GameStatus.NOT_STARTED, description="The current status of the game.")
    start_timestamp: datetime = Field(default_factory=datetime.now, description="The timestamp when the game started.")
    game_id: str = Field(..., description="A unique identifier for this game session.")
    error_message: Optional[str] = Field(None, description="A final error message if the game ended due to an error.")

class GameResult(BaseModel):
    """Summarizes the outcome and key statistics of a completed game."""
    game_id: str = Field(..., description="The unique identifier for the completed game session.")
    config: GameConfig = Field(..., description="The configuration used for this game.")
    status: GameStatus = Field(..., description="The final status of the game (WON, LOST, ERROR).")
    steps: int = Field(..., description="The total number of steps taken.")
    
    # Keep both for different analysis needs
    path_taken: List[str] = Field([], description="Simple page title sequence for path visualization.")
    moves: List[Move] = Field([], description="Complete move history with errors and model responses.")
    
    start_timestamp: datetime = Field(..., description="The timestamp when the game started.")
    end_timestamp: datetime = Field(..., description="The timestamp when the game concluded.")
    error_message: Optional[str] = Field(None, description="A final error message if the game ended due to an error.")
    
    # Pre-aggregated API metrics
    total_input_tokens: int = Field(0, description="Total input tokens across all API calls")
    total_output_tokens: int = Field(0, description="Total output tokens across all API calls") 
    total_tokens: int = Field(0, description="Total tokens across all API calls")
    total_estimated_cost_usd: float = Field(0.0, description="Total estimated cost for all API calls in USD")
    total_api_time_ms: float = Field(0.0, description="Total time spent in API calls in milliseconds")
    average_response_time_ms: float = Field(0.0, description="Average API response time in milliseconds")
    api_call_count: int = Field(0, description="Number of successful API calls made during the game")
    
    # Add metadata for analysis
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional analysis metadata.")

    @classmethod
    def from_game_state(cls, game_state: GameState) -> "GameResult":
        """Convert GameState to GameResult for storage."""
        end_timestamp = datetime.now()
        
        # Build path from moves
        path_taken = []
        if game_state.move_history:
            for move in game_state.move_history:
                if not path_taken:  # First move, add starting page
                    path_taken.append(move.from_page_title)
                if move.to_page_title:  # Successful move
                    path_taken.append(move.to_page_title)
        else:
            # No moves made, just start page
            path_taken.append(game_state.config.start_page_title)
        
        # Calculate aggregated API metrics by iterating through the context
        total_input_tokens = 0
        total_output_tokens = 0
        total_tokens = 0
        total_estimated_cost_usd = 0.0
        total_api_time_ms = 0.0
        api_call_count = 0
        
        for message in game_state.context:
            if isinstance(message, AssistantMessage) and message.metrics:
                total_input_tokens += message.metrics.input_tokens
                total_output_tokens += message.metrics.output_tokens
                total_tokens += message.metrics.total_tokens
                total_estimated_cost_usd += message.metrics.estimated_cost_usd
                total_api_time_ms += message.metrics.response_time_ms
                api_call_count += 1
        
        average_response_time_ms = total_api_time_ms / api_call_count if api_call_count > 0 else 0.0
        
        # Generate analysis metadata
        metadata = {
            "model_name": game_state.config.model.model_name,
            "model_provider": game_state.config.model.provider,
            "links_on_final_page": len(game_state.current_page.links) if game_state.current_page else 0,
            "error_types": [move.error.type.value for move in game_state.move_history if move.error],
            "successful_moves": len([move for move in game_state.move_history if move.to_page_title]),
            # TODO(hunter): we should calculate this from context to count attempts?
            "failed_moves": len([move for move in game_state.move_history if move.error]),
            "target_reached": game_state.status == GameStatus.WON,
            "start_page": game_state.config.start_page_title,
            "target_page": game_state.config.target_page_title,
        }
            
        return cls(
            game_id=game_state.game_id,
            config=game_state.config,
            status=game_state.status, 
            steps=game_state.steps,
            path_taken=path_taken,
            moves=game_state.move_history,
            start_timestamp=game_state.start_timestamp,
            end_timestamp=end_timestamp,
            error_message=game_state.error_message,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            total_tokens=total_tokens,
            total_estimated_cost_usd=total_estimated_cost_usd,
            total_api_time_ms=total_api_time_ms,
            average_response_time_ms=average_response_time_ms,
            api_call_count=api_call_count,
            metadata=metadata
        )
