import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from openai import APITimeoutError, OpenAIError, RateLimitError

from wiki_arena.types import (
    AssistantMessage,
    AssistantToolCall,
    ContextMessage,
    GameState,
    ModelCallMetrics,
)
from wiki_arena.language_models.language_model import (
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
    LanguageModel,
)

from .client import create_client
from .config import OpenRouterModelConfig


logger = logging.getLogger(__name__)


class OpenRouterLanguageModel(LanguageModel):
    """
    LanguageModel implementation for any model on OpenRouter.
    """

    def __init__(self, config: OpenRouterModelConfig):
        super().__init__(config=config)
        self.client = create_client()

    def _calculate_cost(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> float:
        """Calculate cost based on OpenRouter's detailed per-token pricing."""
        cost = 0.0

        # Per-request cost
        if self.config.pricing.request:
            cost += self.config.pricing.request

        # Prompt token cost
        if self.config.pricing.prompt:
            cost += prompt_tokens * self.config.pricing.prompt

        # Completion token cost
        if self.config.pricing.completion:
            cost += completion_tokens * self.config.pricing.completion

        # Cache creation token cost
        if self.config.pricing.input_cache_write and cache_creation_tokens > 0:
            cost += cache_creation_tokens * self.config.pricing.input_cache_write

        # Cache read token cost
        if self.config.pricing.input_cache_read and cache_read_tokens > 0:
            cost += cache_read_tokens * self.config.pricing.input_cache_read

        return cost

    def _format_tools(
        self, mcp_tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        return [{"type": "function", "function": t} for t in mcp_tools]

    def _format_context(
        self, context: List[ContextMessage]
    ) -> List[Dict[str, Any]]:
        messages = []
        for turn in context:
            # TODO: add cache_control to final message for Anthropic and gemini models
            message = {"role": turn.role.value, "content": turn.content}
            if isinstance(turn, AssistantMessage) and turn.tool_calls:
                message["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in turn.tool_calls
                ]
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

        extra_headers = {
            "HTTP-Referer": "https://wikiarena.org/",
            "X-Title": "WikiArena",
        }
        extra_body = {"usage": {"include": True}}

        try:
            start_time = datetime.now()
            response = self.client.chat.completions.create(
                model=self.config.id,
                messages=messages,
                tools=formatted_tools,
                tool_choice="auto",
                extra_headers=extra_headers,
                extra_body=extra_body,
                **self.config.settings,
            )
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000

            usage = response.usage
            prompt_tokens = usage.prompt_tokens
            if self.config.id.includes("gemini"):
                prompt_tokens -= getattr(usage, "prompt_tokens_details", {}).get("cached_tokens", 0)

            completion_tokens = usage.completion_tokens
            total_tokens = usage.total_tokens

            cache_creation_tokens = getattr(usage, "cache_creation_tokens", 0) or 0
            cache_read_tokens = getattr(usage, "cache_read_tokens", 0) or 0

            # TODO: compare both calculate cost methods
            # cost = usage.cost + getattr(usage, "cost_details", {}).get("upstream_inference_cost", 0)
            cost = self._calculate_cost(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cache_creation_tokens=cache_creation_tokens,
                cache_read_tokens=cache_read_tokens,
            )

            metrics = ModelCallMetrics(
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                total_tokens=total_tokens,
                cache_creation_input_tokens=cache_creation_tokens,
                cache_read_input_tokens=cache_read_tokens,
                estimated_cost_usd=cost,
                response_time_ms=duration_ms,
                request_timestamp=start_time,
            )

            message = response.choices[0].message
            tool_calls = []
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    if tool_call.type == "function":
                        tool_calls.append(
                            AssistantToolCall(
                                id=tool_call.id,
                                name=tool_call.function.name,
                                arguments=json.loads(tool_call.function.arguments),
                            )
                        )

            return AssistantMessage(
                content=message.content,
                tool_calls=tool_calls if tool_calls else None,
                metrics=metrics,
            )

        except RateLimitError as e:
            raise LLMRateLimitError from e
        except APITimeoutError as e:
            raise LLMTimeoutError from e
        except OpenAIError as e:
            raise LLMProviderError from e 