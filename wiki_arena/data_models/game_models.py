from typing import List, Dict, Any, Optional
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
    LOST_FORFEIT = "lost_forfeit"
    ERROR = "error"

# --- Data Models ---

DEFAULT_SYSTEM_PROMPT_TEMPLATE = (
    "You are in the Wiki Arena. Your goal is to navigate from the starting Wikipedia page to the target Wikipedia page "
    "by only using the links (page titles) within the current page.\n"
    "Start Page: '{start_page_title}'\n"
    "Target Page: '{target_page_title}'\n\n"
    "Navigate to the target page using the tools provided for you.\n"
)

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
    model_provider: str = Field(..., description="The name of the Language Model.")
    model_settings: Dict[str, Any] = Field({}, description="Provider-specific settings for the language model.")
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
    model_response: str = Field(..., description="The full text response received from the language model.")
    tool_call_attempt: Optional[Dict[str, Any]] = Field(None, description="Details of the tool call attempted by the model.")
    # TODO(hunter): understand why we have/need both result and error
    tool_call_result: Optional[Any] = Field(None, description="The result received from the MCP tool call.")
    error: Optional[str] = Field(None, description="An error message if an error occurred during this step.")

class GameState(BaseModel):
    """Represents the dynamic state of a single ongoing or completed game."""
    config: GameConfig = Field(..., description="The configuration for this game.")
    current_page: Optional[Page] = Field(None, description="Details of the page the language model is currently on.")
    move_history: List[Move] = Field([], description="A chronological list of moves made in the game.")
    steps: int = Field(0, description="The number of steps taken.")
    status: GameStatus = Field(GameStatus.NOT_STARTED, description="The current status of the game.")
    start_timestamp: datetime = Field(default_factory=datetime.now, description="The timestamp when the game started.")
    end_timestamp: Optional[datetime] = Field(None, description="The timestamp when the game ended.")
    game_id: str = Field(..., description="A unique identifier for this game session.")

class GameResult(BaseModel):
    """Summarizes the outcome and key statistics of a completed game."""
    game_id: str = Field(..., description="The unique identifier for the completed game session.")
    config: GameConfig = Field(..., description="The configuration used for this game.")
    status: GameStatus = Field(..., description="The final status of the game (WON, LOST, ERROR).")
    steps: int = Field(..., description="The total number of steps taken.")
    path_taken: List[str] = Field([], description="The sequence of page titles visited.")
    duration: float = Field(..., description="The duration of the game in seconds.")
    end_timestamp: datetime = Field(..., description="The timestamp when the game concluded.")
    error_message: Optional[str] = Field(None, description="A final error message if the game ended due to an error.")

# Example Usage (for testing/demonstration)
if __name__ == "__main__":
    # Example of creating a GameConfig
    example_config = GameConfig(
        start_page_title="Artificial Intelligence",
        target_page_title="Philosophy",
        max_steps=25,
        model_provider="random",
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
        from_page="Artificial Intelligence",
        chosen_link_text="Machine Learning",
        to_page_title="Machine Learning",
        model_response="Thinking process...\n<tool_code>call_tool('getPageContentAndLinks', {'page_title': 'Machine Learning'})</tool_code>",
        tool_call_attempt={'tool_name': 'getPageContentAndLinks', 'parameters': {'page_title': 'Machine Learning'}},
        tool_call_result={"title": "Machine Learning", "url": "...", "content_preview": "...", "links": ["...", "..."]},
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