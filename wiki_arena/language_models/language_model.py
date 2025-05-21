from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from mcp.types import Tool

from pydantic import BaseModel, Field

from wiki_arena.data_models.game_models import GameState, GameConfig

class ToolCall(BaseModel):
    """
    Represents a tool call by an arbitrary language model.
    """
    model_text_response: Optional[str] = Field(None, description="The raw text response or thought process from the language model.")
    tool_name: Optional[str] = Field(None, description="The name of the tool the model chose to call.")
    tool_arguments: Optional[Dict[str, Any]] = Field(None, description="The arguments the model provided for the chosen tool.")
    # TODO(hunter): see if we can remove this or other option
    error_message: Optional[str] = Field(None, description="Any error message if the model failed to produce a valid action.")

class LanguageModel(ABC):
    """
    Abstract base class for Language Model interactions.
    """

    def __init__(self, model_settings: Dict[str, Any]):
        """
        Initializes the Language Model with provider-specific settings and an MCPClient.

        Args:
            model_settings: A dictionary containing configuration for the specific Language Model.
            mcp_client: An instance of MCPClient to interact with the MCP server (e.g., for listing tools).
        """
        self.model_settings = model_settings
        super().__init__()

    @abstractmethod
    async def _format_tools_for_provider(
        self,
        tools: List[Tool],
    ) -> Any: # not sure on type here
        """
        Translate the tools to the language model's format.
        """
        pass

    @abstractmethod
    async def generate_response(
        self,
        tools: List[Tool],
        game_state: GameState,
    ) -> ToolCall:
        """
        Given the current game state, lets the language model choose a tool call.

        This method should be implemented by concrete Language Model classes. It will
        typically involve:
        1. Formatting a prompt based on the game state (current page, target, history, rules, available tools).
        2. Sending the prompt to the Language Model provider.
        3. Parsing the AI's response to extract a tool call (name and arguments) and any textual thoughts.
        4. Returning a ToolCall object.

        Args:
            game_state: The current state of the game.

        Returns:
            A ToolCall object detailing the model's chosen tool call or an error.
        """
        pass

    
