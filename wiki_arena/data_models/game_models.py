from typing import List, Dict, Any, Optional, Type
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

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

# --- Data Models ---

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
    
    def get_storage_key(self) -> str:
        """Generate consistent key for storage naming."""
        if self.provider == "random":
            return "random"
        # Clean model name for filesystem compatibility
        clean_model_name = self.model_name.replace('/', '_').replace('-', '_').replace('.', '_')
        return f"{self.provider}_{clean_model_name}"

# --- Model Registry will be imported later to avoid circular imports ---

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
    timestamp: datetime = Field(default_factory=datetime.now, description="The timestamp when this move occurred.")
    model_response: Optional[str] = Field(None, description="The full text response received from the language model.")
    tool_call_attempt: Optional[Dict[str, Any]] = Field(None, description="Details of the tool call attempted by the model.")
    error: Optional[GameError] = Field(None, description="Structured error information if an error occurred during this step.")

class GameState(BaseModel):
    """Represents the dynamic state of a single ongoing or completed game."""
    config: GameConfig = Field(..., description="The configuration for this game.")
    current_page: Optional[Page] = Field(None, description="Details of the page the language model is currently on.")
    move_history: List[Move] = Field([], description="A chronological list of moves made in the game.")
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
    
    duration: float = Field(..., description="The duration of the game in seconds.")
    start_timestamp: datetime = Field(..., description="The timestamp when the game started.")
    end_timestamp: datetime = Field(..., description="The timestamp when the game concluded.")
    error_message: Optional[str] = Field(None, description="A final error message if the game ended due to an error.")
    
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
        
        # Generate analysis metadata
        metadata = {
            "model_key": game_state.config.model.get_storage_key(),
            "model_provider": game_state.config.model.provider,
            "model_name": game_state.config.model.model_name,
            "links_on_final_page": len(game_state.current_page.links) if game_state.current_page else 0,
            "error_types": [move.error.type.value for move in game_state.move_history if move.error],
            "successful_moves": len([move for move in game_state.move_history if move.to_page_title]),
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
            duration=(end_timestamp - game_state.start_timestamp).total_seconds(),
            start_timestamp=game_state.start_timestamp,
            end_timestamp=end_timestamp,
            error_message=game_state.error_message,
            metadata=metadata
        )

# Example Usage (for testing/demonstration)
if __name__ == "__main__":
    # Example of creating a GameConfig
    example_config = GameConfig(
        start_page_title="Artificial Intelligence",
        target_page_title="Philosophy",
        max_steps=25,
        model=ModelConfig(
            provider="random",
            model_name="random",
            settings={}
        ),
    )
    print("Example GameConfig:")
    print(example_config.model_dump_json(indent=2))

    # Example of creating initial GameState
    initial_state = GameState(
        game_id="game_123",
        config=example_config,
        status=GameStatus.NOT_STARTED
    )
    print("\nExample Initial GameState:")
    print(initial_state.model_dump_json(indent=2))

    # Example of creating a Move
    example_move = Move(
        step=1,
        from_page_title="Artificial Intelligence",
        to_page_title="Machine Learning",
        model_response="Thinking process...\n<tool_code>call_tool('getPageContentAndLinks', {'page_title': 'Machine Learning'})</tool_code>",
        tool_call_attempt={'tool_name': 'getPageContentAndLinks', 'parameters': {'page_title': 'Machine Learning'}},
        timestamp=datetime.now()
    )
    print("\nExample Move:")
    print(example_move.model_dump_json(indent=2))

    # Example of updating GameState with a move
    current_page_info = Page(
        title="Machine Learning",
        url="...",
        text="...",
        links=["Algorithm", "Data", "Model"]
    )
    state_after_move = GameState(
        game_id="game_123",
        config=example_config,
        current_page=current_page_info,
        move_history=[example_move],
        steps=1,
        status=GameStatus.IN_PROGRESS,
        start_timestamp=initial_state.start_timestamp # Carry over start time
    )
    print("\nExample GameState After Move:")
    print(state_after_move.model_dump_json(indent=2))

    # Example of creating a GameResult
    end_time = datetime.now()
    example_result = GameResult(
        game_id="game_123",
        config=example_config,
        status=GameStatus.WON,
        steps=5,
        path_taken=["Artificial Intelligence", "Machine Learning", "Neural Network", "Computer Science", "Philosophy"],
        duration=(end_time - initial_state.start_timestamp).total_seconds(),
        end_timestamp=end_time
    )
    print("\nExample GameResult:")
    print(example_result.model_dump_json(indent=2))