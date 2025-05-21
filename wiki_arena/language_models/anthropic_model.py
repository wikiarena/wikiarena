from typing import Any, Dict, List, Optional
import logging

from anthropic import Anthropic, AnthropicError
from .language_model import LanguageModel, ToolCall
from wiki_arena.data_models.game_models import GameState
from mcp.types import Tool

class AnthropicModel(LanguageModel):
    """
    LanguageModel implementation for Anthropic's Claude models.
    """
    DEFAULT_MODEL_NAME = "claude-3-5-haiku-latest"
    DEFAULT_MAX_TOKENS = 1024

    def __init__(self, model_settings: Dict[str, Any]):
        super().__init__(model_settings)
        try:
            self.client = Anthropic()  # API key is inferred from ANTHROPIC_API_KEY env var
            self.model_name = model_settings.get("model_name", self.DEFAULT_MODEL_NAME)
            self.max_tokens = model_settings.get("max_tokens", self.DEFAULT_MAX_TOKENS)
        except AnthropicError as e:
            logging.error(f"Failed to initialize Anthropic client: {e}")
            # Depending on desired behavior, you might want to re-raise the error,
            # set a 'failed' state, or handle it in another way.
            # For now, re-raising to make the initialization failure explicit.
            raise
    
    # TODO(hunter): does this need to be async?
    async def _format_tools_for_provider(
        self,
        tools: List[Tool],
    ) -> List[Dict[str, Any]]:
        """
        Translate the tools to the language model's format.
        """
        formatted_tools = []
        for mcp_tool in tools:
            formatted_tools.append({
                "name": mcp_tool.name,
                "description": mcp_tool.description or f"Tool named {mcp_tool.name} without a description.", # Ensure description is present
                "input_schema": mcp_tool.inputSchema
            })
        return formatted_tools

    async def generate_response(
        self,
        tools: List[Tool],
        game_state: GameState,
    ) -> ToolCall:
        # TODO(hunter): error handling for game state

        # TODO(hunter): should I cache the tools? lets not for now since they come every time
        formatted_tools = await self._format_tools_for_provider(tools)
        system_prompt = game_state.config.system_prompt_template.format(
            start_page_title=game_state.config.start_page_title,
            target_page_title=game_state.config.target_page_title,
        )
        # TODO(hunter): cache messages
        messages = [
            {"role": "user", "content": [
                {"type": "text", "text": f"Current Page: {game_state.current_page.title}"},
                {"type": "text", "text": f"Content: {"\n".join(game_state.current_page.links)}"},
            ]},
        ]
        # logging.info(f"<system_prompt>\n{system_prompt}\n</system_prompt>")
        
        # # Logging the messages in a format simulating how a model might see them, with role tags.
        # logging.info("--- BEGIN Formatted Messages for LLM (Simulated View) ---")
        # for msg in messages:
        #     role_name = msg['role']
        #     logging.info(f"<{role_name}>") # Example: <user>
            
        #     # msg['content'] is expected to be a list of content blocks.
        #     # For this model, it's typically: [{"type": "text", "text": "..."}]
        #     for content_block in msg['content']: # Original 'content' var renamed to 'content_block' for clarity
        #         logging.info(content_block['text'])

        #     logging.info(f"</{role_name}>") # Example: </user>
        #     # This separator helps distinguish between multiple messages if `messages` list grows.
        # logging.info("--- END Formatted Messages for LLM (Simulated View) ---")
        
        response = self.client.messages.create(
            model=self.model_name,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=messages,
            tools=formatted_tools,
        )
        logging.debug(f"AnthropicModel: API response received: {response}")

        # TODO(hunter): add parse model response to tool call function
        model_text_response: Optional[str] = None
        tool_name: Optional[str] = None
        tool_arguments: Optional[Dict[str, Any]] = None
        
        for content_block in response.content:
            if content_block.type == "text":
                model_text_response = (model_text_response or "") + content_block.text
            elif content_block.type == "tool_use":
                tool_name = content_block.name
                tool_arguments = content_block.input

        # TODO(hunter) append model result to messages
        return ToolCall(
            model_text_response=model_text_response,
            tool_name=tool_name,
            tool_arguments=tool_arguments
        )



        
