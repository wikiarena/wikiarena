from typing import Any, Dict, List, Optional
import logging
from datetime import datetime

from anthropic import Anthropic, AnthropicError
from .language_model import LanguageModel, ToolCall
from wiki_arena.models import GameState, MoveMetrics, ModelConfig
from mcp.types import Tool

class AnthropicModel(LanguageModel):
    """
    LanguageModel implementation for Anthropic's Claude models.
    """
    DEFAULT_MAX_TOKENS = 1024

    def __init__(self, model_config: ModelConfig):
        super().__init__(model_config)
        try:
            self.client = Anthropic()  # API key is inferred from ANTHROPIC_API_KEY env var
            self.model_name = model_config.model_name
            self.max_tokens = model_config.settings.get("max_tokens", self.DEFAULT_MAX_TOKENS)
        except AnthropicError as e:
            logging.error(f"Failed to initialize Anthropic client: {e}")
            # Depending on desired behavior, you might want to re-raise the error,
            # set a 'failed' state, or handle it in another way.
            # For now, re-raising to make the initialization failure explicit.
            raise
    
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
        
        start_time = datetime.now()

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
        
        try:
            response = self.client.messages.create(
                model=self.model_name,
                max_tokens=self.max_tokens,
                system=system_prompt,
                messages=messages,
                tools=formatted_tools,
            )
            
            end_time = datetime.now()
            response_time_ms = (end_time - start_time).total_seconds() * 1000
            
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

            # Create metrics
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            total_tokens = input_tokens + output_tokens
            estimated_cost = self._calculate_cost(input_tokens, output_tokens)
            
            metrics = MoveMetrics(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=estimated_cost,
                response_time_ms=response_time_ms,
                request_timestamp=start_time
            )

            # TODO(hunter) append model result to messages
            return ToolCall(
                model_text_response=model_text_response,
                tool_name=tool_name,
                tool_arguments=tool_arguments,
                metrics=metrics
            )
            
        except AnthropicError as e:
            end_time = datetime.now()
            response_time_ms = (end_time - start_time).total_seconds() * 1000
            logging.error(f"Anthropic API call failed: {e}")
            
            # Create metrics for failed call (no tokens, but record timing)
            metrics = MoveMetrics(
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                estimated_cost_usd=0.0,
                response_time_ms=response_time_ms,
                request_timestamp=start_time
            )
            
            return ToolCall(
                error_message=f"Anthropic API call failed: {e}",
                metrics=metrics
            )



        
