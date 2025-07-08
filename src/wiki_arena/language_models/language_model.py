import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from wiki_arena.models import ContextMessage, ModelConfig, GameState, AssistantMessage


logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    """Base exception for all language model provider errors."""
    pass

class LLMRateLimitError(LLMProviderError):
    """Raised when a provider rate limit is exceeded."""
    pass

class LLMTimeoutError(LLMProviderError):
    """Raised when a provider API call times out."""
    pass


class LanguageModel(ABC):
    """
    Abstract base class for all language models.
    """

    def __init__(self, model_config: ModelConfig):
        """
        Initializes the Language Model with a structured ModelConfig.

        Args:
            model_config: A ModelConfig object containing provider, model name, pricing, and settings.
        """
        self.model_config = model_config
        # Keep backward compatibility for now
        self.model_settings = model_config.settings
        super().__init__()

    @abstractmethod
    def _calculate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> float:
        """Calculate cost based on model pricing and token usage."""
        pass

    @abstractmethod
    def _format_tools(
        self,
        mcp_tools: List[Dict[str, Any]],
    ) -> Any:
        """
        Convert MCP tool definitions to the provider's format.
        
        Args:
            mcp_tools: List of tool definitions in MCP format
            
        Returns:
            Tools formatted for the specific provider's API
        """
        pass

    @abstractmethod
    def _format_context(self, context: List[ContextMessage]) -> Any:
        """
        Convert the generic `ContextMessage` list to the provider's format.
        """
        pass

    @abstractmethod
    async def generate_response(
        self,
        tools: List[Dict[str, Any]],
        context: List[ContextMessage],
        game_state: GameState, # the random model NEEDS this, others not so much
    ) -> AssistantMessage:
        """
        Given the current context and available tools, get the next assistant message.

        This method should be implemented by concrete Language Model classes. It will
        typically involve:
        1. Converting the generic `ContextMessage` list to the provider's specific format.
        2. Converting tools from MCP format to provider format
        3. Sending the prompt to the Language Model provider.
        4. Parsing the AI's response into a standard `AssistantMessage` object,
           which may include text and/or tool call requests.

        Args:
            tools: List of available tools in MCP format
            context: The full context so far.

        Returns:
            An `AssistantMessage` object from the model.
        """
        pass
