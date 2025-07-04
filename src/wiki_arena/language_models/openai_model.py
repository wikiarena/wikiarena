from typing import Any, Dict, List, Optional
import logging
from datetime import datetime

from openai import OpenAI, OpenAIError
from .language_model import LanguageModel, ToolCall
from wiki_arena.models import GameState, MoveMetrics, ModelConfig

class OpenAIModel(LanguageModel):
    """
    LanguageModel implementation for OpenAI's models.
    """
    DEFAULT_MAX_TOKENS = 1024

    def __init__(self, model_config: ModelConfig):
        super().__init__(model_config)
        try:
            self.client = OpenAI()  # API key is inferred from OPENAI_API_KEY env var
            self.model_name = model_config.model_name
            self.max_tokens = model_config.settings.get("max_tokens", self.DEFAULT_MAX_TOKENS)
        except OpenAIError as e:
            logging.error(f"Failed to initialize OpenAI client: {e}")
            # Depending on desired behavior, you might want to re-raise the error,
            # set a 'failed' state, or handle it in another way.
            # For now, re-raising to make the initialization failure explicit.
            raise

    async def _format_tools_for_provider(
        self,
        mcp_tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Convert MCP tool definitions to OpenAI function calling format.
        
        Args:
            mcp_tools: List of tool definitions in MCP format
            
        Returns:
            Tools formatted for OpenAI's API
        """
        formatted_tools = []
        for mcp_tool in mcp_tools:
            formatted_tools.append({
                "type": "function",
                "function": {
                    "name": mcp_tool["name"],
                    "description": mcp_tool["description"],
                    "parameters": mcp_tool["inputSchema"]
                }
            })
        return formatted_tools

    async def generate_response(
        self,
        tools: List[Dict[str, Any]],
        game_state: GameState,
    ) -> ToolCall:
        """
        Generate a response from the OpenAI model.
        """
        start_time = datetime.now()
        
        formatted_tools = await self._format_tools_for_provider(tools)
        system_prompt = game_state.config.system_prompt_template.format(
            start_page_title=game_state.config.start_page_title,
            target_page_title=game_state.config.target_page_title,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Current Page: {game_state.current_page.title}\\nContent: {"\\n".join(game_state.current_page.links)}"},
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                tools=formatted_tools,
                tool_choice="auto",  # Or "required" or {"type": "function", "function": {"name": "my_function"}}
                max_tokens=self.max_tokens,
            )
            
            end_time = datetime.now()
            response_time_ms = (end_time - start_time).total_seconds() * 1000
            
            logging.debug(f"OpenAIModel: API response received: {response}")

            model_text_response: Optional[str] = None
            tool_name: Optional[str] = None
            tool_arguments_str: Optional[str] = None  # OpenAI returns arguments as a string

            choice = response.choices[0]
            message = choice.message

            if message.content:
                model_text_response = message.content
            else: # TODO(hunter): decide if we want to allow Move and ToolCall objs to have no text response, possible when model directly calls tool
                model_text_response = "" # Ensure empty string if no content

            if message.tool_calls:
                # For simplicity, taking the first tool call if multiple are present
                # OpenAI can technically return multiple tool calls in a single response
                tool_call = message.tool_calls[0]
                if tool_call.type == "function":
                    tool_name = tool_call.function.name
                    tool_arguments_str = tool_call.function.arguments
            
            # TODO(hunter): Consider how to handle message.tool_calls if it's None but a tool was expected,
            # or if no tool call was made but text response is also empty.

            tool_arguments: Optional[Dict[str, Any]] = None
            if tool_arguments_str:
                import json # Delayed import
                try:
                    tool_arguments = json.loads(tool_arguments_str)
                except json.JSONDecodeError as e:
                    logging.error(f"Failed to parse tool arguments JSON: {e}. Arguments string: {tool_arguments_str}")
                    # TODO(hunter): Decide if this should return an error ToolCall or try to recover
                    
                    # Create metrics for failed parsing (record tokens and timing)
                    input_tokens = response.usage.prompt_tokens if response.usage else 0
                    output_tokens = response.usage.completion_tokens if response.usage else 0
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
                    
                    return ToolCall(
                        model_text_response=model_text_response,
                        error_message=f"Failed to parse tool arguments JSON: {tool_arguments_str}",
                        metrics=metrics
                    )

            # Create metrics for successful call
            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0
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

            return ToolCall(
                model_text_response=model_text_response,
                tool_name=tool_name,
                tool_arguments=tool_arguments,
                metrics=metrics
            )
            
        except OpenAIError as e:
            end_time = datetime.now()
            response_time_ms = (end_time - start_time).total_seconds() * 1000
            logging.error(f"OpenAI API call failed: {e}")
            
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
                error_message=f"OpenAI API call failed: {e}",
                metrics=metrics
            ) 