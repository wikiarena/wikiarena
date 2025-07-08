import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from anthropic import (
    Anthropic,
    AnthropicError,
    RateLimitError,
    APITimeoutError,
)
from wiki_arena.models import (
    AssistantMessage,
    AssistantToolCall,
    ContextMessage,
    ModelCallMetrics,
    ModelConfig,
    GameState,
    ToolResultMessage,
    UserMessage,
)
from .language_model import (
    LanguageModel,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)


logger = logging.getLogger(__name__)


class AnthropicModel(LanguageModel):
    """
    LanguageModel implementation for Anthropic's Claude models.
    """
    DEFAULT_MAX_TOKENS = 1024

    def __init__(self, model_config: ModelConfig):
        super().__init__(model_config)
        self.client = Anthropic()  # API key is inferred from ANTHROPIC_API_KEY env var
        self.model_name = model_config.model_name
        self.max_tokens = model_config.settings.get("max_tokens", self.DEFAULT_MAX_TOKENS)

    def _calculate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> float:
        """Calculate cost based on Anthropic's pricing and token usage, including caching."""
        if not self.model_config.input_cost_per_1m_tokens or not self.model_config.output_cost_per_1m_tokens:
            return 0.0

        # Regular input and output tokens are priced at standard rates
        input_cost = (input_tokens / 1_000_000) * self.model_config.input_cost_per_1m_tokens
        output_cost = (output_tokens / 1_000_000) * self.model_config.output_cost_per_1m_tokens

        # Cache token costs
        # 5-minute cache write tokens are 1.25 times the base input tokens price
        cache_creation_cost = (cache_creation_tokens / 1_000_000) * self.model_config.input_cost_per_1m_tokens * 1.25
        # Cache read tokens are 0.1 times the base input tokens price
        cache_read_cost = (cache_read_tokens / 1_000_000) * self.model_config.input_cost_per_1m_tokens * 0.1

        return input_cost + output_cost + cache_creation_cost + cache_read_cost

    def _format_tools(self, mcp_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert MCP tool definitions to Anthropic tool format."""
        formatted_tools = []
        for mcp_tool in mcp_tools:
            formatted_tools.append({
                "name": mcp_tool["name"],
                "description": mcp_tool["description"],
                "input_schema": mcp_tool["inputSchema"]
            })
        return formatted_tools

    def _format_context(self, context: List[ContextMessage]) -> tuple[Optional[List[Dict[str, Any]]], List[Dict[str, Any]]]:
        """Converts the universal context to Anthropic's format."""
        system_prompt_blocks: Optional[List[Dict[str, Any]]] = None
        messages: List[Dict[str, Any]] = []
        
        # Extract the system prompt first.
        if context and context[0].role == "system":
            system_prompt_blocks = [{"type": "text", "text": context[0].content}]
            # Add cache control to the system prompt's content block.
            system_prompt_blocks[0]["cache_control"] = {"type": "ephemeral"}
            context = context[1:]

        for turn in context:
            if isinstance(turn, (UserMessage, ToolResultMessage)):
                # Anthropic uses 'user' role for both user and tool result messages. 
                # For simplicity here, we assume a back-and-forth conversation.
                if isinstance(turn, ToolResultMessage):
                    messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": turn.tool_call_id,
                            "content": turn.content,
                            "is_error": turn.is_error,
                        }]
                    })
                else: # UserMessage
                    content = turn.content
                    if not isinstance(content, list):
                        content = [{"type": "text", "text": content}]
                    messages.append({"role": "user", "content": content})
            elif isinstance(turn, AssistantMessage):
                content = []
                if turn.content:
                    content.append({"type": "text", "text": turn.content})
                if turn.tool_calls:
                    for tool_call in turn.tool_calls:
                        content.append({
                            "type": "tool_use",
                            "id": tool_call.id,
                            "name": tool_call.name,
                            "input": tool_call.arguments,
                        })
                messages.append({"role": "assistant", "content": content})
        
        # Add cache control to the last content block of the last message
        if messages:
            last_message_content = messages[-1]["content"]
            if last_message_content:
                last_message_content[-1]["cache_control"] = {"type": "ephemeral"}

        return system_prompt_blocks, messages

    async def generate_response(
        self,
        tools: List[Dict[str, Any]],
        context: List[ContextMessage],
        game_state: GameState,
    ) -> AssistantMessage:
        
        system_prompt_blocks, messages = self._format_context(context)
        formatted_tools = self._format_tools(tools)
        
        logger.debug(f"Sending request to Anthropic with system prompt: {system_prompt_blocks}")
        logger.debug(f"Sending request to Anthropic with messages: {json.dumps(messages, indent=2)}")

        try:
            start_time = datetime.now()
            response = self.client.messages.create(
                model=self.model_name,
                max_tokens=self.max_tokens,
                system=system_prompt_blocks,
                messages=messages,
                tools=formatted_tools,
            )
            
            # Calculate metrics for logging
            usage = response.usage
            input_tokens = usage.input_tokens
            output_tokens = usage.output_tokens
            cache_creation_tokens = getattr(usage, 'cache_creation_input_tokens', 0) or 0
            cache_read_tokens = getattr(usage, 'cache_read_input_tokens', 0) or 0

            total_tokens = input_tokens + output_tokens
            cost = self._calculate_cost(input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens)
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000

            log_parts = [
                f"Input: {input_tokens}",
                f"Output: {output_tokens}",
            ]
            if cache_creation_tokens > 0:
                log_parts.append(f"Cache Creation: {cache_creation_tokens}")
            if cache_read_tokens > 0:
                log_parts.append(f"Cache Read: {cache_read_tokens}")
            
            log_parts.extend([
                f"Total: {total_tokens}",
                f"Cost: ${cost:.4f}",
                f"Duration: {duration_ms:.1f}ms"
            ])
            logger.info(f"Response Tokens: {' | '.join(log_parts)}")

            metrics = ModelCallMetrics(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cache_creation_input_tokens=cache_creation_tokens,
                cache_read_input_tokens=cache_read_tokens,
                estimated_cost_usd=cost,
                response_time_ms=duration_ms,
                request_timestamp=start_time
            )

            model_text_response = None
            tool_calls = []
            
            for content_block in response.content:
                if content_block.type == "text":
                    model_text_response = (model_text_response or "") + content_block.text
                elif content_block.type == "tool_use":
                    tool_calls.append(
                        AssistantToolCall(
                            id=content_block.id,
                            name=content_block.name,
                            arguments=content_block.input,
                        )
                    )

            return AssistantMessage(
                content=model_text_response,
                tool_calls=tool_calls if tool_calls else None,
                metrics=metrics
            )
            
        except RateLimitError as e:
            logger.error(f"Anthropic API rate limit exceeded: {e}", exc_info=True)
            raise LLMRateLimitError from e
        except APITimeoutError as e:
            logger.error(f"Anthropic API call timed out: {e}", exc_info=True)
            raise LLMTimeoutError from e
        except AnthropicError as e:
            logger.error(f"Anthropic API call failed: {e}", exc_info=True)
            raise LLMProviderError from e
