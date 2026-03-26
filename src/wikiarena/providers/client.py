from __future__ import annotations

import json
import os
import time
from typing import Any
from typing import Protocol

from anthropic import APITimeoutError as AnthropicTimeoutError
from anthropic import AsyncAnthropic
from anthropic import AnthropicError
from anthropic import RateLimitError as AnthropicRateLimitError
from openai import APITimeoutError as OpenAITimeoutError
from openai import AsyncOpenAI
from openai import OpenAIError
from openai import RateLimitError as OpenAIRateLimitError

from wikiarena.providers.types import ProviderMessage
from wikiarena.providers.types import ProviderMessageRole
from wikiarena.providers.types import ProviderRequest
from wikiarena.providers.types import ProviderResponse
from wikiarena.providers.types import ProviderToolCall
from wikiarena.providers.types import ProviderUsage


class ProviderError(Exception):
    pass


class ProviderConfigurationError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


def _strip_internal_pricing_settings(
    call_settings: dict[str, Any],
) -> None:
    call_settings.pop(
        "input_cost_per_1m_tokens",
        None,
    )
    call_settings.pop(
        "output_cost_per_1m_tokens",
        None,
    )


class ModelProvider(Protocol):
    async def generate(
        self,
        request: ProviderRequest,
    ) -> ProviderResponse: ...


class OpenAIChatProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        extra_headers: dict[str, str] | None = None,
        timeout_s: float | None = None,
    ):
        self.base_url = base_url
        self.timeout_s = timeout_s
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=extra_headers,
        )

    async def generate(
        self,
        request: ProviderRequest,
    ) -> ProviderResponse:
        formatted_messages = _format_messages_for_openai(
            request.messages,
        )
        formatted_tools = _format_tools_for_openai(
            request,
        )

        call_settings = dict(
            request.settings,
        )
        _strip_internal_pricing_settings(
            call_settings,
        )
        timeout_s = call_settings.pop(
            "timeout_s",
            self.timeout_s,
        )
        if timeout_s is not None:
            call_settings["timeout"] = timeout_s

        call_payload: dict[str, Any] = {
            "model": request.model_id,
            "messages": formatted_messages,
            **call_settings,
        }
        if formatted_tools:
            call_payload["tools"] = formatted_tools
            call_payload["tool_choice"] = request.tool_choice

        try:
            started_at = time.perf_counter()
            response = await self.client.chat.completions.create(
                **call_payload,
            )
            duration_ms = (time.perf_counter() - started_at) * 1000.0
        except OpenAIRateLimitError as rate_limit_error:
            raise ProviderRateLimitError(
                "OpenAI provider rate limit exceeded",
            ) from rate_limit_error
        except OpenAITimeoutError as timeout_error:
            raise ProviderTimeoutError(
                "OpenAI provider timed out",
            ) from timeout_error
        except OpenAIError as provider_error:
            raise ProviderError(
                "OpenAI provider request failed",
            ) from provider_error

        message = response.choices[0].message
        tool_calls = []
        if message.tool_calls:
            for tool_call in message.tool_calls:
                if tool_call.type != "function":
                    continue
                tool_calls.append(
                    ProviderToolCall(
                        id=tool_call.id,
                        name=tool_call.function.name,
                        arguments=_parse_json_object(
                            tool_call.function.arguments,
                        ),
                    ),
                )

        response_message = ProviderMessage(
            role=ProviderMessageRole.ASSISTANT,
            content=_extract_openai_content(
                message.content,
            ),
            tool_calls=tool_calls,
        )
        usage = _usage_from_openai_response(
            response,
            duration_ms=duration_ms,
            settings=request.settings,
        )
        return ProviderResponse(
            message=response_message,
            usage=usage,
            provider_response_id=getattr(
                response,
                "id",
                None,
            ),
        )


class AnthropicChatProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        timeout_s: float | None = None,
    ):
        self.base_url = base_url
        self.timeout_s = timeout_s
        self.client = AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_s,
        )

    async def generate(
        self,
        request: ProviderRequest,
    ) -> ProviderResponse:
        enable_prompt_caching = _anthropic_prompt_caching_enabled(
            request.settings,
        )
        system_prompt, messages = _format_messages_for_anthropic(
            request.messages,
        )
        formatted_tools = _format_tools_for_anthropic(
            request,
        )

        call_settings = dict(
            request.settings,
        )
        _strip_internal_pricing_settings(
            call_settings,
        )
        call_settings.pop(
            "anthropic_prompt_caching",
            None,
        )
        max_tokens = call_settings.pop(
            "max_tokens",
            1024,
        )

        call_payload: dict[str, Any] = {
            "model": request.model_id,
            "max_tokens": max_tokens,
            "messages": messages,
            **call_settings,
        }
        if system_prompt:
            call_payload["system"] = system_prompt
        if formatted_tools:
            call_payload["tools"] = formatted_tools
        cache_control = _build_anthropic_cache_control(
            request.settings,
        )
        if cache_control is not None:
            call_payload["cache_control"] = cache_control

        try:
            started_at = time.perf_counter()
            response = await self.client.messages.create(
                **call_payload,
            )
            duration_ms = (time.perf_counter() - started_at) * 1000.0
        except AnthropicRateLimitError as rate_limit_error:
            raise ProviderRateLimitError(
                "Anthropic provider rate limit exceeded",
            ) from rate_limit_error
        except AnthropicTimeoutError as timeout_error:
            raise ProviderTimeoutError(
                "Anthropic provider timed out",
            ) from timeout_error
        except AnthropicError as provider_error:
            raise ProviderError(
                "Anthropic provider request failed",
            ) from provider_error

        assistant_text_parts: list[str] = []
        tool_calls: list[ProviderToolCall] = []
        for block in response.content:
            if block.type == "text":
                assistant_text_parts.append(
                    block.text,
                )
                continue
            if block.type == "tool_use":
                tool_calls.append(
                    ProviderToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    ),
                )

        response_message = ProviderMessage(
            role=ProviderMessageRole.ASSISTANT,
            content="".join(
                assistant_text_parts,
            )
            or None,
            tool_calls=tool_calls,
        )
        usage = ProviderUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            cache_creation_input_tokens=getattr(
                response.usage,
                "cache_creation_input_tokens",
                0,
            )
            or 0,
            cache_read_input_tokens=getattr(
                response.usage,
                "cache_read_input_tokens",
                0,
            )
            or 0,
            estimated_cost_usd=_estimate_token_cost_usd(
                settings=request.settings,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cache_creation_input_tokens=getattr(
                    response.usage,
                    "cache_creation_input_tokens",
                    0,
                )
                or 0,
                cache_read_input_tokens=getattr(
                    response.usage,
                    "cache_read_input_tokens",
                    0,
                )
                or 0,
                anthropic_cache_pricing=enable_prompt_caching,
            ),
            response_time_ms=duration_ms,
        )
        return ProviderResponse(
            message=response_message,
            usage=usage,
            provider_response_id=getattr(
                response,
                "id",
                None,
            ),
        )


def create_provider_client(
    provider_name: str,
    provider_settings: dict[str, Any] | None = None,
) -> ModelProvider:
    resolved_provider_settings = dict(
        provider_settings or {},
    )
    normalized_provider_name = provider_name.strip().lower()

    if normalized_provider_name in {"openai", "openai_compatible"}:
        return OpenAIChatProvider(
            api_key=_require_value(
                _pick_first(
                    resolved_provider_settings.pop("api_key", None),
                    os.getenv("OPENAI_API_KEY"),
                ),
                "api_key",
                provider_name,
            ),
            base_url=_pick_first(
                resolved_provider_settings.pop("base_url", None),
                os.getenv("OPENAI_BASE_URL"),
            ),
            extra_headers=resolved_provider_settings.pop(
                "extra_headers",
                None,
            ),
            timeout_s=resolved_provider_settings.pop(
                "timeout_s",
                None,
            ),
        )

    if normalized_provider_name == "openrouter":
        return OpenAIChatProvider(
            api_key=_require_value(
                _pick_first(
                    resolved_provider_settings.pop("api_key", None),
                    os.getenv("OPENROUTER_API_KEY"),
                ),
                "api_key",
                provider_name,
            ),
            base_url=_pick_first(
                resolved_provider_settings.pop("base_url", None),
                os.getenv("OPENROUTER_BASE_URL"),
                "https://openrouter.ai/api/v1",
            ),
            extra_headers=resolved_provider_settings.pop(
                "extra_headers",
                {
                    "HTTP-Referer": "https://wikiarena.org/",
                    "X-Title": "WikiArena",
                },
            ),
            timeout_s=resolved_provider_settings.pop(
                "timeout_s",
                None,
            ),
        )

    if normalized_provider_name == "anthropic":
        return AnthropicChatProvider(
            api_key=_require_value(
                _pick_first(
                    resolved_provider_settings.pop("api_key", None),
                    os.getenv("ANTHROPIC_API_KEY"),
                ),
                "api_key",
                provider_name,
            ),
            base_url=_pick_first(
                resolved_provider_settings.pop("base_url", None),
                os.getenv("ANTHROPIC_BASE_URL"),
            ),
            timeout_s=resolved_provider_settings.pop(
                "timeout_s",
                None,
            ),
        )

    raise ProviderConfigurationError(
        f"Unsupported provider '{provider_name}'",
    )


def _pick_first(*values: str | None) -> str | None:
    for value in values:
        if value is None:
            continue
        if not value.strip():
            continue
        return value
    return None


def _require_value(
    value: str | None,
    field_name: str,
    provider_name: str,
) -> str:
    if value is None:
        raise ProviderConfigurationError(
            f"Missing required {field_name} for provider '{provider_name}'",
        )
    return value


def _format_messages_for_openai(
    messages: list[ProviderMessage],
) -> list[dict[str, Any]]:
    formatted_messages: list[dict[str, Any]] = []
    for message in messages:
        if message.role in {
            ProviderMessageRole.SYSTEM,
            ProviderMessageRole.USER,
        }:
            formatted_messages.append(
                {
                    "role": message.role.value,
                    "content": message.content or "",
                },
            )
            continue

        if message.role == ProviderMessageRole.ASSISTANT:
            assistant_message = {
                "role": "assistant",
                "content": message.content,
            }
            if message.tool_calls:
                assistant_message["tool_calls"] = [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.name,
                            "arguments": json.dumps(
                                tool_call.arguments,
                            ),
                        },
                    }
                    for tool_call in message.tool_calls
                ]
            formatted_messages.append(
                assistant_message,
            )
            continue

        formatted_messages.append(
            {
                "role": "tool",
                "tool_call_id": message.tool_call_id,
                "content": message.content or "",
            },
        )

    return formatted_messages


def _format_messages_for_anthropic(
    messages: list[ProviderMessage],
) -> tuple[str | list[dict[str, Any]] | None, list[dict[str, Any]]]:
    system_text_parts: list[str] = []
    formatted_messages: list[dict[str, Any]] = []

    for message in messages:
        if message.role == ProviderMessageRole.SYSTEM:
            if message.content:
                system_text_parts.append(
                    message.content,
                )
            continue

        if message.role == ProviderMessageRole.USER:
            formatted_messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": message.content or "",
                        },
                    ],
                },
            )
            continue

        if message.role == ProviderMessageRole.ASSISTANT:
            content_blocks: list[dict[str, Any]] = []
            if message.content:
                content_blocks.append(
                    {
                        "type": "text",
                        "text": message.content,
                    },
                )
            for tool_call in message.tool_calls:
                content_blocks.append(
                    {
                        "type": "tool_use",
                        "id": tool_call.id,
                        "name": tool_call.name,
                        "input": tool_call.arguments,
                    },
                )
            formatted_messages.append(
                {
                    "role": "assistant",
                    "content": content_blocks,
                },
            )
            continue

        formatted_messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": message.tool_call_id,
                        "content": message.content or "",
                        "is_error": message.is_error,
                    },
                ],
            },
        )

    system_prompt = "\n\n".join(
        system_text_parts,
    )
    return system_prompt or None, formatted_messages


def _format_tools_for_openai(
    request: ProviderRequest,
) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
        for tool in request.tools
    ]


def _format_tools_for_anthropic(
    request: ProviderRequest,
) -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for tool in request.tools
    ]


def _extract_openai_content(
    content: Any,
) -> str | None:
    if content is None:
        return None
    if isinstance(
        content,
        str,
    ):
        return content
    if isinstance(
        content,
        list,
    ):
        text_segments = []
        for item in content:
            if (
                isinstance(
                    item,
                    dict,
                )
                and item.get("type") == "text"
            ):
                text_segments.append(
                    item.get("text", ""),
                )
        if text_segments:
            return "".join(
                text_segments,
            )
    return str(
        content,
    )


def _usage_from_openai_response(
    response: Any,
    *,
    duration_ms: float,
    settings: dict[str, Any],
) -> ProviderUsage:
    usage = getattr(
        response,
        "usage",
        None,
    )
    if usage is None:
        return ProviderUsage(
            response_time_ms=duration_ms,
        )

    input_tokens = (
        getattr(
            usage,
            "prompt_tokens",
            0,
        )
        or 0
    )
    output_tokens = (
        getattr(
            usage,
            "completion_tokens",
            0,
        )
        or 0
    )
    total_tokens = (
        getattr(
            usage,
            "total_tokens",
            input_tokens + output_tokens,
        )
        or 0
    )
    return ProviderUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=_estimate_token_cost_usd(
            settings=settings,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
        response_time_ms=duration_ms,
    )


def _estimate_token_cost_usd(
    *,
    settings: dict[str, Any],
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
    anthropic_cache_pricing: bool = False,
) -> float:
    input_cost_per_1m_tokens = settings.get(
        "input_cost_per_1m_tokens",
    )
    output_cost_per_1m_tokens = settings.get(
        "output_cost_per_1m_tokens",
    )
    if input_cost_per_1m_tokens is None or output_cost_per_1m_tokens is None:
        return 0.0

    estimated_cost = (input_tokens / 1_000_000) * float(input_cost_per_1m_tokens) + (
        output_tokens / 1_000_000
    ) * float(output_cost_per_1m_tokens)

    if anthropic_cache_pricing:
        estimated_cost += (
            (cache_creation_input_tokens / 1_000_000)
            * float(input_cost_per_1m_tokens)
            * 1.25
        )
        estimated_cost += (
            (cache_read_input_tokens / 1_000_000)
            * float(input_cost_per_1m_tokens)
            * 0.1
        )

    return estimated_cost


def _anthropic_prompt_caching_enabled(
    settings: dict[str, Any],
) -> bool:
    return bool(
        settings.get(
            "anthropic_prompt_caching",
            True,
        ),
    )


def _build_anthropic_cache_control(
    settings: dict[str, Any],
) -> dict[str, Any] | None:
    if not _anthropic_prompt_caching_enabled(
        settings,
    ):
        return None

    cache_control: dict[str, Any] = {
        "type": "ephemeral",
    }
    cache_ttl = settings.get(
        "anthropic_cache_ttl",
    )
    if cache_ttl is not None:
        cache_control["ttl"] = cache_ttl
    return cache_control


def _parse_json_object(
    payload: str | dict[str, Any],
) -> dict[str, Any]:
    if isinstance(
        payload,
        dict,
    ):
        return payload

    try:
        parsed = json.loads(
            payload,
        )
    except json.JSONDecodeError:
        return {
            "raw": payload,
        }

    if isinstance(
        parsed,
        dict,
    ):
        return parsed
    return {
        "raw": payload,
    }
