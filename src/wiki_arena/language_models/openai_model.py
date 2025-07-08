import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from openai import (
    OpenAI,
    OpenAIError,
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
)
from .language_model import (
    LanguageModel,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from wiki_arena.models import (
    AssistantMessage,
    AssistantToolCall,
    ContextMessage,
    ModelCallMetrics,
    ModelConfig,
    GameState,
)

logger = logging.getLogger(__name__)

class OpenAIModel(LanguageModel):
    def __init__(self, model_config: ModelConfig):
        super().__init__(model_config)
        self.client = OpenAI() # Assumes OPENAI_API_KEY is set in environment

    def _calculate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> float:
        """Calculate cost based on OpenAI's pricing and token usage, including caching."""
        input_cost = (input_tokens / 1_000_000) * self.model_config.input_cost_per_1m_tokens
        output_cost = (output_tokens / 1_000_000) * self.model_config.output_cost_per_1m_tokens
        return input_cost + output_cost

    def _format_tools(self, mcp_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # OpenAI uses a format that is very similar to MCP, but it's called 'function'
        return [{"type": "function", "function": t} for t in mcp_tools]

    def _format_context(self, context: List[ContextMessage]) -> List[Dict[str, Any]]:
        """Converts the universal conversation history to OpenAI's format."""
        messages = []
        for turn in context:
            message = {"role": turn.role.value, "content": turn.content}
            # Handle assistant messages with tool calls
            if isinstance(turn, AssistantMessage) and turn.tool_calls:
                message["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": str(tc.arguments)},
                    }
                    for tc in turn.tool_calls
                ]
            # Handle tool response messages
            if turn.role == "tool":
                message = {
                    "role": "tool",
                    "tool_call_id": turn.tool_call_id,
                    "content": turn.content,
                }
            messages.append(message)
        return messages


    async def generate_response(
        self,
        tools: List[Dict[str, Any]],
        context: List[ContextMessage],
        game_state: GameState,
    ) -> AssistantMessage:
        
        formatted_tools = self._format_tools(tools)
        messages = self._format_context(context)

        try:
            logger.debug(f"Sending request with messages: {messages}")
            start_time = datetime.now()
            response = self.client.chat.completions.create(
                model=self.model_config.model_name,
                messages=messages,
                tools=formatted_tools,
                tool_choice="auto",
                max_tokens=self.model_config.settings.get("max_tokens", 1024),
                # TODO(hunter): cache control
                # TODO(hunter): timeout
            )
            logger.debug(f"API response received: {response}")

            # Calculate metrics for logging
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            total_tokens = response.usage.total_tokens
            cost = self._calculate_cost(input_tokens, output_tokens)
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000

            log_parts = [
                f"Input: {input_tokens}",
                f"Output: {output_tokens}",
                f"Total: {total_tokens}",
                f"Cost: ${cost:.4f}",
                f"Duration: {duration_ms:.1f}ms"
            ]
            logger.info(f"Response Tokens: {' | '.join(log_parts)}")

            metrics = ModelCallMetrics(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=cost,
                response_time_ms=duration_ms,
                request_timestamp=start_time,
            )

            choice = response.choices[0]
            message = choice.message

            model_text_response = message.content
            tool_calls = []

            if message.tool_calls:
                for tool_call in message.tool_calls:
                    if tool_call.type == "function":
                        try:
                            arguments = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            # Handle error, maybe create a special message or log it
                            logger.error(f"Failed to parse arguments for tool {tool_call.function.name}: {tool_call.function.arguments}")
                            arguments = {"error": "failed to parse arguments"}

                        tool_calls.append(
                            AssistantToolCall(
                                id=tool_call.id,
                                name=tool_call.function.name,
                                arguments=arguments,
                            )
                        )

            return AssistantMessage(
                content=model_text_response,
                tool_calls=tool_calls if tool_calls else None,
                metrics=metrics
            )

        except RateLimitError as e:
            logger.error(f"OpenAI API rate limit exceeded: {e}", exc_info=True)
            raise LLMRateLimitError from e
        except APITimeoutError as e:
            logger.error(f"OpenAI API call timed out: {e}", exc_info=True)
            raise LLMTimeoutError from e
        except OpenAIError as e:
            logger.error(f"Error generating response from OpenAI: {e}", exc_info=True)
            raise LLMProviderError from e