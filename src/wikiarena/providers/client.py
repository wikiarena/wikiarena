from __future__ import annotations

import asyncio
import base64
import copy
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx
from anthropic import AnthropicError, AsyncAnthropic
from anthropic import APITimeoutError as AnthropicTimeoutError
from anthropic import RateLimitError as AnthropicRateLimitError
from openai import APITimeoutError as OpenAITimeoutError
from openai import AsyncOpenAI, OpenAIError
from openai import RateLimitError as OpenAIRateLimitError

from wikiarena.providers.types import (
    ProviderMessage,
    ProviderMessageRole,
    ProviderReasoningItem,
    ProviderRequest,
    ProviderResponse,
    ProviderToolCall,
    ProviderUsage,
)


class ProviderError(Exception):
    pass


class ProviderConfigurationError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


_CODEX_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
_CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
_CODEX_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
_CODEX_DEFAULT_ORIGINATOR = "wikiarena"
_CODEX_DEFAULT_USER_AGENT = "wikiarena/codex"
_CODEX_WEBSOCKET_BETA_HEADER_VALUE = "responses_websockets=2026-02-06"
_CODEX_AUTH_REFRESH_MARGIN_S = 60.0
_PROMPT_CACHE_KEY_PREFIX = "wikiarena"

_CODEX_IGNORED_SETTINGS = {
    # The ChatGPT Codex endpoint rejects these even though other OpenAI APIs accept them.
    "max_tokens",
    "prompt_cache_retention",
    "temperature",
    "top_p",
}
_CODEX_PASSTHROUGH_SETTINGS = {
    "client_metadata",
    "parallel_tool_calls",
    "text",
}


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
    call_settings.pop(
        "cache_read_input_cost_per_1m_tokens",
        None,
    )
    call_settings.pop(
        "cached_input_cost_per_1m_tokens",
        None,
    )
    call_settings.pop(
        "cache_creation_input_cost_per_1m_tokens",
        None,
    )
    call_settings.pop(
        "long_context_threshold_input_tokens",
        None,
    )
    call_settings.pop(
        "long_context_input_cost_per_1m_tokens",
        None,
    )
    call_settings.pop(
        "long_context_output_cost_per_1m_tokens",
        None,
    )
    call_settings.pop(
        "long_context_cache_read_input_cost_per_1m_tokens",
        None,
    )
    call_settings.pop(
        "long_context_cached_input_cost_per_1m_tokens",
        None,
    )
    call_settings.pop(
        "long_context_cache_creation_input_cost_per_1m_tokens",
        None,
    )


def _default_prompt_cache_key() -> str:
    return f"{_PROMPT_CACHE_KEY_PREFIX}-{uuid.uuid4()}"


def _strip_openai_internal_settings(
    call_settings: dict[str, Any],
) -> None:
    for key in (
        "openai_api_mode",
        "openai_include_encrypted_reasoning",
        "openai_reasoning_summary",
        "openai_use_previous_response_id",
        "output_config",
        "thinking",
    ):
        call_settings.pop(
            key,
            None,
        )


def _reject_priority_service_tier(
    call_settings: dict[str, Any],
    *,
    provider_name: str,
) -> None:
    service_tier = call_settings.get(
        "service_tier",
    )
    if service_tier is None:
        return
    normalized_service_tier = (
        str(
            service_tier,
        )
        .strip()
        .lower()
    )
    if normalized_service_tier in {
        "fast",
        "priority",
    }:
        raise ProviderConfigurationError(
            f"{provider_name} provider priority service_tier is disabled",
        )


class ModelProvider(Protocol):
    async def generate(
        self,
        request: ProviderRequest,
    ) -> ProviderResponse: ...


@dataclass
class _CodexAuthState:
    auth_file: Path
    access_token: str
    refresh_token: str | None
    account_id: str | None
    id_token: str | None
    expires_at_s: float | None
    raw_payload: dict[str, Any]


class _CodexAuthRefreshRequired(ProviderError):
    pass


class _CodexWebSocketFallbackToHttp(ProviderError):
    pass


@dataclass(frozen=True)
class _AnthropicVertexConfig:
    base_url: str
    model_base_url: str
    project: str
    location: str
    cosmos_app_id: str
    cosmos_app_scope: str
    aiml_gateway_app_context_key_name: str
    keymaker_base_url: str | None
    keymaker_app_context_env_var: str
    require_app_context: bool = True
    token_expiry_window_seconds_default: int = 1800
    beta_headers: tuple[str, ...] = ()


@dataclass(frozen=True)
class _TokenPricing:
    input_cost_per_1m_tokens: float
    output_cost_per_1m_tokens: float
    cache_read_input_cost_per_1m_tokens: float | None = None
    cache_creation_input_cost_per_1m_tokens: float | None = None
    long_context_threshold_input_tokens: int | None = None
    long_context_input_cost_per_1m_tokens: float | None = None
    long_context_output_cost_per_1m_tokens: float | None = None
    long_context_cache_read_input_cost_per_1m_tokens: float | None = None
    long_context_cache_creation_input_cost_per_1m_tokens: float | None = None


_OPENAI_STANDARD_MODEL_PRICING = {
    "gpt-5.5": _TokenPricing(5.0, 30.0, 0.50, None, 272_000, 10.0, 45.0, 1.0),
    "gpt-5.5-pro": _TokenPricing(30.0, 180.0, None, None, 272_000, 60.0, 270.0),
    "gpt-5.4": _TokenPricing(2.50, 15.0, 0.25, None, 272_000, 5.0, 22.50, 0.50),
    "gpt-5.4-mini": _TokenPricing(0.75, 4.50, 0.075),
    "gpt-5.4-nano": _TokenPricing(0.20, 1.25, 0.02),
    "gpt-5.4-pro": _TokenPricing(30.0, 180.0, None, None, 272_000, 60.0, 270.0),
}

_ANTHROPIC_MODEL_PRICING = {
    "claude-opus-4-7": _TokenPricing(5.0, 25.0, 0.50, 6.25),
    "claude-opus-4-6": _TokenPricing(5.0, 25.0, 0.50, 6.25),
    "claude-opus-4-5": _TokenPricing(5.0, 25.0, 0.50, 6.25),
    "claude-sonnet-4-6": _TokenPricing(3.0, 15.0, 0.30, 3.75),
    "claude-sonnet-4-5": _TokenPricing(3.0, 15.0, 0.30, 3.75),
    "claude-sonnet-4": _TokenPricing(3.0, 15.0, 0.30, 3.75),
    "claude-haiku-4-5": _TokenPricing(1.0, 5.0, 0.10, 1.25),
    "claude-haiku-3-5": _TokenPricing(0.80, 4.0, 0.08, 1.0),
    "claude-haiku-3": _TokenPricing(0.25, 1.25, 0.03, 0.30),
}


class OpenAIChatProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        extra_headers: dict[str, str] | None = None,
        timeout_s: float | None = None,
        default_api_mode: str = "chat_completions",
        supported_api_modes: set[str] | None = None,
        prompt_cache_key: str | None = None,
        pricing_provider_name: str = "openai",
    ):
        self.base_url = base_url
        self.timeout_s = timeout_s
        self.default_api_mode = default_api_mode
        self.supported_api_modes = frozenset(
            supported_api_modes or {"chat_completions", "responses"},
        )
        self.prompt_cache_key = prompt_cache_key
        self.pricing_provider_name = pricing_provider_name
        self._previous_response_id: str | None = None
        self._last_request_message_count = 0
        self._last_response_message: ProviderMessage | None = None
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=extra_headers,
        )

    async def generate(
        self,
        request: ProviderRequest,
    ) -> ProviderResponse:
        resolved_api_mode = _resolve_openai_api_mode(
            request.settings,
            default_api_mode=self.default_api_mode,
        )
        if resolved_api_mode not in self.supported_api_modes:
            supported_modes = ", ".join(
                sorted(
                    self.supported_api_modes,
                ),
            )
            raise ProviderConfigurationError(
                f"Unsupported openai_api_mode '{resolved_api_mode}'. "
                f"Supported modes for this provider: {supported_modes}",
            )
        if resolved_api_mode == "responses":
            _require_token_pricing(
                settings=request.settings,
                model_id=request.model_id,
                provider_name=self.pricing_provider_name,
            )
            return await self._generate_with_responses_api(
                request,
            )
        if resolved_api_mode == "chat_completions":
            _require_token_pricing(
                settings=request.settings,
                model_id=request.model_id,
                provider_name=self.pricing_provider_name,
            )
            return await self._generate_with_chat_completions(
                request,
            )
        raise ProviderConfigurationError(
            f"Unsupported openai_api_mode '{resolved_api_mode}'",
        )

    async def _generate_with_chat_completions(
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
        _strip_openai_internal_settings(
            call_settings,
        )
        _reject_priority_service_tier(
            call_settings,
            provider_name="OpenAI",
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
                f"OpenAI provider request failed: {provider_error}",
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
            thinking=_extract_openai_thinking_content(
                message,
            ),
            tool_calls=tool_calls,
        )
        usage = _usage_from_openai_response(
            response,
            model_id=request.model_id,
            provider_name=self.pricing_provider_name,
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

    async def _generate_with_responses_api(
        self,
        request: ProviderRequest,
    ) -> ProviderResponse:
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
        reasoning_effort = call_settings.pop(
            "reasoning_effort",
            None,
        )
        call_settings.pop(
            "openai_api_mode",
            None,
        )
        openai_reasoning_summary = call_settings.pop(
            "openai_reasoning_summary",
            None,
        )
        openai_include_encrypted_reasoning = bool(
            call_settings.pop(
                "openai_include_encrypted_reasoning",
                False,
            ),
        )
        openai_use_previous_response_id = bool(
            call_settings.pop(
                "openai_use_previous_response_id",
                True,
            ),
        )
        max_output_tokens = call_settings.pop(
            "max_tokens",
            None,
        )
        prompt_cache_key = call_settings.pop(
            "prompt_cache_key",
            self.prompt_cache_key,
        )
        call_settings.pop(
            "thinking",
            None,
        )
        call_settings.pop(
            "output_config",
            None,
        )
        _reject_priority_service_tier(
            call_settings,
            provider_name="OpenAI",
        )

        previous_response_id = None
        response_input = request.messages
        if openai_use_previous_response_id and self._previous_response_id is not None:
            previous_response_id = self._previous_response_id
            response_input = _messages_since_last_openai_response(
                request.messages,
                last_request_message_count=self._last_request_message_count,
                last_response_message=self._last_response_message,
            )

        formatted_input = _format_messages_for_openai_responses(
            response_input,
        )
        formatted_tools = _format_tools_for_openai_responses(
            request,
        )
        call_payload: dict[str, Any] = {
            "model": request.model_id,
            "input": formatted_input,
            **call_settings,
        }
        if formatted_tools:
            call_payload["tools"] = formatted_tools
            call_payload["tool_choice"] = request.tool_choice
        if previous_response_id is not None:
            call_payload["previous_response_id"] = previous_response_id
        if max_output_tokens is not None:
            call_payload["max_output_tokens"] = max_output_tokens
        if prompt_cache_key is not None:
            call_payload["prompt_cache_key"] = prompt_cache_key
        reasoning_config = _build_openai_responses_reasoning_config(
            effort=reasoning_effort,
            summary=openai_reasoning_summary,
        )
        if reasoning_config is not None:
            call_payload["reasoning"] = reasoning_config
        include_values: list[str] = []
        if openai_include_encrypted_reasoning:
            include_values.append(
                "reasoning.encrypted_content",
            )
        if include_values:
            call_payload["include"] = include_values
        if timeout_s is not None:
            call_payload["timeout"] = timeout_s

        try:
            started_at = time.perf_counter()
            response = await self.client.responses.create(
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
                f"OpenAI provider request failed: {provider_error}",
            ) from provider_error

        response_message = _provider_message_from_openai_responses_output(
            response.output,
        )
        usage = _usage_from_openai_responses_response(
            response,
            model_id=request.model_id,
            provider_name=self.pricing_provider_name,
            duration_ms=duration_ms,
            settings=request.settings,
        )
        self._previous_response_id = getattr(
            response,
            "id",
            None,
        )
        self._last_request_message_count = len(
            request.messages,
        )
        self._last_response_message = response_message.model_copy(
            deep=True,
        )
        return ProviderResponse(
            message=response_message,
            usage=usage,
            provider_response_id=self._previous_response_id,
        )


class CodexChatProvider:
    def __init__(
        self,
        *,
        auth_file: str | Path,
        base_url: str | None = None,
        timeout_s: float | None = None,
        originator: str = _CODEX_DEFAULT_ORIGINATOR,
        user_agent: str = _CODEX_DEFAULT_USER_AGENT,
        prompt_cache_key: str | None = None,
        http_client: Any | None = None,
        codex_transport: str | None = None,
        websocket_connect: Any | None = None,
        websocket_prewarm: bool = False,
    ):
        self.auth_file = Path(
            auth_file,
        ).expanduser()
        self.base_url = base_url or _CODEX_RESPONSES_URL
        self.timeout_s = timeout_s
        self.originator = originator
        self.user_agent = user_agent
        self.prompt_cache_key = prompt_cache_key or _default_prompt_cache_key()
        self._codex_session_id = self.prompt_cache_key
        self._codex_window_id = f"{self._codex_session_id}:0"
        self._codex_turn_state: str | None = None
        self.codex_transport = _resolve_codex_transport(
            codex_transport,
            http_client=http_client,
            websocket_connect=websocket_connect,
        )
        self.websocket_connect = websocket_connect or _connect_codex_websocket
        self.websocket_prewarm = websocket_prewarm
        self._codex_ws_connection: Any | None = None
        self._codex_ws_last_request: dict[str, Any] | None = None
        self._codex_ws_last_response_id: str | None = None
        self._codex_ws_last_output_items: list[dict[str, Any]] = []
        self.client = http_client or httpx.AsyncClient(
            timeout=timeout_s,
        )

    async def generate(
        self,
        request: ProviderRequest,
    ) -> ProviderResponse:
        _require_token_pricing(
            settings=request.settings,
            model_id=request.model_id,
            provider_name="codex",
        )
        call_settings = dict(
            request.settings,
        )
        _strip_internal_pricing_settings(
            call_settings,
        )
        reasoning_effort = call_settings.pop(
            "reasoning_effort",
            None,
        )
        for setting_name in _CODEX_IGNORED_SETTINGS:
            call_settings.pop(
                setting_name,
                None,
            )
        prompt_cache_key = call_settings.pop(
            "prompt_cache_key",
            self.prompt_cache_key,
        )
        self._ensure_codex_session_identity(
            prompt_cache_key,
        )
        codex_transport = _resolve_codex_transport(
            call_settings.pop(
                "codex_transport",
                self.codex_transport,
            ),
            http_client=None,
            websocket_connect=self.websocket_connect,
        )
        codex_websocket_prewarm = bool(
            call_settings.pop(
                "codex_websocket_prewarm",
                self.websocket_prewarm,
            ),
        )
        service_tier = _pop_codex_service_tier(
            call_settings,
        )
        call_settings.pop(
            "openai_api_mode",
            None,
        )
        call_settings.pop(
            "openai_use_previous_response_id",
            None,
        )
        openai_reasoning_summary = call_settings.pop(
            "openai_reasoning_summary",
            None,
        )
        openai_include_encrypted_reasoning = bool(
            call_settings.pop(
                "openai_include_encrypted_reasoning",
                False,
            ),
        )
        include_values = _pop_include_values(
            call_settings,
        )
        if openai_include_encrypted_reasoning:
            include_values.append(
                "reasoning.encrypted_content",
            )
        call_settings.pop(
            "thinking",
            None,
        )
        call_settings.pop(
            "output_config",
            None,
        )
        call_settings.pop(
            "timeout_s",
            None,
        )
        passthrough_settings = _pop_codex_passthrough_settings(
            call_settings,
        )
        if call_settings:
            unsupported_settings = ", ".join(
                sorted(
                    call_settings,
                ),
            )
            raise ProviderConfigurationError(
                f"Codex provider does not support settings: {unsupported_settings}",
            )

        instructions, response_input = _split_system_instructions_for_codex(
            request.messages,
        )
        call_payload: dict[str, Any] = {
            "model": request.model_id,
            "instructions": instructions,
            "input": _format_messages_for_openai_responses(
                response_input,
            ),
            "store": False,
            "stream": True,
            "prompt_cache_key": prompt_cache_key,
            **passthrough_settings,
        }
        if service_tier is not None:
            call_payload["service_tier"] = service_tier
        formatted_tools = _format_tools_for_openai_responses(
            request,
        )
        if formatted_tools:
            call_payload["tools"] = formatted_tools
            call_payload["tool_choice"] = request.tool_choice
        reasoning_config = _build_codex_reasoning_config(
            effort=reasoning_effort,
            summary=openai_reasoning_summary,
        )
        if reasoning_config is not None:
            call_payload["reasoning"] = reasoning_config
        if include_values:
            call_payload["include"] = _unique_preserving_order(
                include_values,
            )

        auth_state = _load_codex_auth_state(
            self.auth_file,
        )
        auth_state = await self._refresh_auth_state_if_needed(
            auth_state,
        )

        try:
            output_items, completed_response, duration_ms = await self._stream_response(
                auth_state=auth_state,
                call_payload=call_payload,
                codex_transport=codex_transport,
                websocket_prewarm=codex_websocket_prewarm,
            )
        except _CodexAuthRefreshRequired:
            auth_state = await self._refresh_auth_state(
                auth_state,
            )
            output_items, completed_response, duration_ms = await self._stream_response(
                auth_state=auth_state,
                call_payload=call_payload,
                codex_transport=codex_transport,
                websocket_prewarm=codex_websocket_prewarm,
            )
        except httpx.TimeoutException as timeout_error:
            raise ProviderTimeoutError(
                "Codex provider timed out",
            ) from timeout_error
        except httpx.HTTPError as provider_error:
            raise ProviderError(
                f"Codex provider request failed: {provider_error}",
            ) from provider_error

        response_message = _provider_message_from_openai_responses_output(
            [
                _namespace_from_mapping(
                    item,
                )
                for item in output_items
            ],
        )
        usage = _usage_from_openai_responses_response(
            _namespace_from_mapping(
                {
                    "usage": completed_response.get(
                        "usage",
                    ),
                },
            ),
            model_id=request.model_id,
            provider_name="codex",
            duration_ms=duration_ms,
            settings=request.settings,
        )
        return ProviderResponse(
            message=response_message,
            usage=usage,
            provider_response_id=_string_or_none(
                completed_response.get(
                    "id",
                ),
            ),
        )

    async def _stream_response(
        self,
        *,
        auth_state: _CodexAuthState,
        call_payload: dict[str, Any],
        codex_transport: str,
        websocket_prewarm: bool,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], float]:
        if codex_transport in {"websocket", "websocket_only"}:
            try:
                return await self._stream_response_websocket(
                    auth_state=auth_state,
                    call_payload=call_payload,
                    websocket_prewarm=websocket_prewarm,
                )
            except _CodexWebSocketFallbackToHttp:
                if codex_transport == "websocket_only":
                    raise ProviderError(
                        "Codex websocket transport failed and HTTP fallback is disabled",
                    )
                return await self._stream_response_http(
                    auth_state=auth_state,
                    call_payload=call_payload,
                )
        return await self._stream_response_http(
            auth_state=auth_state,
            call_payload=call_payload,
        )

    async def _stream_response_http(
        self,
        *,
        auth_state: _CodexAuthState,
        call_payload: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any], float]:
        headers = _build_codex_request_headers(
            access_token=auth_state.access_token,
            account_id=auth_state.account_id,
            originator=self.originator,
            user_agent=self.user_agent,
            session_id=self._codex_session_id,
            window_id=self._codex_window_id,
            turn_state=self._codex_turn_state,
        )
        started_at = time.perf_counter()
        async with self.client.stream(
            "POST",
            self.base_url,
            headers=headers,
            json=call_payload,
        ) as response:
            if response.status_code == 401:
                raise _CodexAuthRefreshRequired(
                    "Codex access token expired",
                )
            if response.status_code == 429:
                detail = await _read_codex_error_detail(
                    response,
                )
                raise ProviderRateLimitError(
                    f"Codex provider rate limit exceeded: {detail}",
                )
            if response.status_code >= 400:
                detail = await _read_codex_error_detail(
                    response,
                )
                raise ProviderError(
                    f"Codex provider request failed: {detail}",
                )
            self._capture_codex_turn_state(
                response,
            )
            output_items, completed_response = await _parse_codex_sse_stream(
                response,
            )

        duration_ms = (time.perf_counter() - started_at) * 1000.0
        return output_items, completed_response, duration_ms

    async def _stream_response_websocket(
        self,
        *,
        auth_state: _CodexAuthState,
        call_payload: dict[str, Any],
        websocket_prewarm: bool,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], float]:
        started_at = time.perf_counter()
        await self._ensure_codex_websocket_connection(
            auth_state=auth_state,
        )
        if websocket_prewarm:
            await self._prewarm_codex_websocket(
                call_payload,
            )

        request_payload = self._prepare_codex_websocket_request(
            call_payload,
        )
        self._codex_ws_last_request = copy.deepcopy(
            call_payload,
        )
        output_items, completed_response = await self._send_codex_websocket_request(
            request_payload,
        )
        self._record_codex_websocket_response(
            output_items=output_items,
            completed_response=completed_response,
        )
        duration_ms = (time.perf_counter() - started_at) * 1000.0
        return output_items, completed_response, duration_ms

    async def _ensure_codex_websocket_connection(
        self,
        *,
        auth_state: _CodexAuthState,
    ) -> None:
        if self._codex_ws_connection is not None and not bool(
            getattr(
                self._codex_ws_connection,
                "closed",
                False,
            ),
        ):
            return

        headers = _build_codex_websocket_headers(
            access_token=auth_state.access_token,
            account_id=auth_state.account_id,
            originator=self.originator,
            user_agent=self.user_agent,
            session_id=self._codex_session_id,
            window_id=self._codex_window_id,
            turn_state=self._codex_turn_state,
        )
        connection = await self.websocket_connect(
            _codex_websocket_url(
                self.base_url,
            ),
            headers=headers,
            timeout_s=self.timeout_s,
        )
        self._codex_ws_connection = connection
        self._capture_codex_turn_state_from_headers(
            getattr(
                connection,
                "response_headers",
                None,
            ),
        )

    async def _prewarm_codex_websocket(
        self,
        call_payload: dict[str, Any],
    ) -> None:
        if self._codex_ws_last_request is not None:
            return
        request_payload = {
            "type": "response.create",
            **copy.deepcopy(
                call_payload,
            ),
            "generate": False,
        }
        output_items, completed_response = await self._send_codex_websocket_request(
            request_payload,
        )
        self._codex_ws_last_request = copy.deepcopy(
            call_payload,
        )
        self._record_codex_websocket_response(
            output_items=output_items,
            completed_response=completed_response,
        )

    def _prepare_codex_websocket_request(
        self,
        call_payload: dict[str, Any],
    ) -> dict[str, Any]:
        request_payload = {
            "type": "response.create",
            **copy.deepcopy(
                call_payload,
            ),
        }
        previous_response_id = self._codex_ws_last_response_id
        incremental_input = _codex_incremental_input(
            current_request=call_payload,
            previous_request=self._codex_ws_last_request,
            previous_output_items=self._codex_ws_last_output_items,
            allow_empty_delta=True,
        )
        if previous_response_id is not None and incremental_input is not None:
            request_payload["previous_response_id"] = previous_response_id
            request_payload["input"] = incremental_input
        return request_payload

    async def _send_codex_websocket_request(
        self,
        request_payload: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        connection = self._codex_ws_connection
        if connection is None:
            raise ProviderError(
                "Codex websocket connection is unavailable",
            )
        try:
            await connection.send(
                json.dumps(
                    request_payload,
                ),
            )
            return await _parse_codex_websocket_stream(
                connection,
            )
        except ProviderError:
            self._codex_ws_connection = None
            raise
        except Exception as error:
            self._codex_ws_connection = None
            raise ProviderError(
                f"Codex websocket request failed: {error}",
            ) from error

    def _record_codex_websocket_response(
        self,
        *,
        output_items: list[dict[str, Any]],
        completed_response: dict[str, Any],
    ) -> None:
        response_id = _string_or_none(
            completed_response.get(
                "id",
            ),
        )
        self._codex_ws_last_response_id = response_id
        self._codex_ws_last_output_items = _codex_output_items_for_incremental_baseline(
            output_items,
        )

    def _ensure_codex_session_identity(
        self,
        prompt_cache_key: str | None,
    ) -> None:
        if prompt_cache_key is None or prompt_cache_key == self._codex_session_id:
            return
        self.prompt_cache_key = prompt_cache_key
        self._codex_session_id = prompt_cache_key
        self._codex_window_id = f"{self._codex_session_id}:0"
        self._codex_turn_state = None
        self._codex_ws_connection = None
        self._codex_ws_last_request = None
        self._codex_ws_last_response_id = None
        self._codex_ws_last_output_items = []

    def _capture_codex_turn_state(
        self,
        response: Any,
    ) -> None:
        headers = getattr(
            response,
            "headers",
            None,
        )
        if headers is None:
            return
        turn_state = _string_or_none(
            headers.get(
                "x-codex-turn-state",
            ),
        )
        if turn_state is not None:
            self._codex_turn_state = turn_state

    def _capture_codex_turn_state_from_headers(
        self,
        headers: Any,
    ) -> None:
        if headers is None:
            return
        turn_state = _string_or_none(
            headers.get(
                "x-codex-turn-state",
            ),
        )
        if turn_state is not None:
            self._codex_turn_state = turn_state

    async def _refresh_auth_state_if_needed(
        self,
        auth_state: _CodexAuthState,
    ) -> _CodexAuthState:
        if not _codex_auth_token_needs_refresh(
            auth_state,
        ):
            return auth_state
        return await self._refresh_auth_state(
            auth_state,
        )

    async def _refresh_auth_state(
        self,
        auth_state: _CodexAuthState,
    ) -> _CodexAuthState:
        refresh_token = auth_state.refresh_token
        if refresh_token is None:
            raise ProviderConfigurationError(
                f"Codex auth file is missing tokens.refresh_token: {auth_state.auth_file}",
            )

        response = await self.client.post(
            _CODEX_OAUTH_TOKEN_URL,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": _CODEX_OAUTH_CLIENT_ID,
            },
        )
        if response.status_code >= 400:
            detail = _codex_refresh_error_detail(
                response,
            )
            raise ProviderError(
                f"Codex provider request failed: {detail}",
            )

        refreshed_tokens = response.json()
        if not isinstance(
            refreshed_tokens,
            dict,
        ):
            raise ProviderError(
                "Codex provider request failed: invalid refresh response",
            )
        persisted_payload = dict(
            auth_state.raw_payload,
        )
        persisted_tokens = dict(
            persisted_payload.get(
                "tokens",
                {},
            ),
        )
        access_token = _require_string_field(
            refreshed_tokens.get(
                "access_token",
            ),
            field_name="access_token",
            context="Codex refresh response",
        )
        id_token = (
            _string_or_none(
                refreshed_tokens.get(
                    "id_token",
                ),
            )
            or auth_state.id_token
        )
        new_refresh_token = (
            _string_or_none(
                refreshed_tokens.get(
                    "refresh_token",
                ),
            )
            or refresh_token
        )
        account_id = _extract_codex_account_id(
            id_token=id_token,
            access_token=access_token,
            fallback_account_id=auth_state.account_id,
        )

        persisted_tokens["access_token"] = access_token
        persisted_tokens["refresh_token"] = new_refresh_token
        if id_token is not None:
            persisted_tokens["id_token"] = id_token
        if account_id is not None:
            persisted_tokens["account_id"] = account_id
        persisted_payload["tokens"] = persisted_tokens
        persisted_payload["last_refresh"] = (
            datetime.now(
                UTC,
            )
            .isoformat()
            .replace(
                "+00:00",
                "Z",
            )
        )
        auth_state.auth_file.write_text(
            json.dumps(
                persisted_payload,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )

        return _load_codex_auth_state(
            auth_state.auth_file,
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
        _require_token_pricing(
            settings=request.settings,
            model_id=request.model_id,
            provider_name="anthropic",
            anthropic_cache_pricing=_anthropic_prompt_caching_enabled(
                request.settings,
            ),
        )
        cache_control = _build_anthropic_cache_control(
            request.settings,
        )
        system_prompt, messages = _format_messages_for_anthropic(
            request.messages,
            cache_control=cache_control,
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
        call_settings.pop(
            "anthropic_cache_ttl",
            None,
        )
        call_settings.pop(
            "timeout_s",
            None,
        )
        output_config = call_settings.pop(
            "output_config",
            None,
        )
        max_tokens = call_settings.pop(
            "max_tokens",
            _default_anthropic_max_tokens(
                model_id=request.model_id,
                thinking=call_settings.get(
                    "thinking",
                ),
                output_config=output_config,
            ),
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
        if output_config is not None:
            call_payload["output_config"] = output_config

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
                f"Anthropic provider request failed: {provider_error}",
            ) from provider_error

        assistant_text_parts: list[str] = []
        assistant_thinking_parts: list[str] = []
        tool_calls: list[ProviderToolCall] = []
        for block in response.content:
            if block.type == "thinking":
                thinking_text = getattr(
                    block,
                    "thinking",
                    None,
                )
                if thinking_text:
                    assistant_thinking_parts.append(
                        thinking_text,
                    )
                continue
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
            thinking="\n\n".join(
                assistant_thinking_parts,
            )
            or None,
            content="".join(
                assistant_text_parts,
            )
            or None,
            tool_calls=tool_calls,
        )
        cache_creation_input_tokens = (
            getattr(
                response.usage,
                "cache_creation_input_tokens",
                0,
            )
            or 0
        )
        cache_read_input_tokens = (
            getattr(
                response.usage,
                "cache_read_input_tokens",
                0,
            )
            or 0
        )
        usage = ProviderUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=(
                response.usage.input_tokens
                + response.usage.output_tokens
                + cache_creation_input_tokens
                + cache_read_input_tokens
            ),
            cache_creation_input_tokens=cache_creation_input_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
            input_token_details={
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
            },
            estimated_cost_usd=_estimate_token_cost_usd(
                settings=request.settings,
                model_id=request.model_id,
                provider_name="anthropic",
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cache_creation_input_tokens=cache_creation_input_tokens,
                cache_read_input_tokens=cache_read_input_tokens,
                input_tokens_include_cache_tokens=False,
                anthropic_cache_pricing=_anthropic_prompt_caching_enabled(
                    request.settings,
                ),
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


class _AnthropicVertexKeymakerClient:
    _ALL_OBJECTS_PATH = "/kmsapi/v1/keyobject/all"

    def __init__(
        self,
        *,
        base_url: str,
        app_context_env_var: str,
        http_client: httpx.AsyncClient,
    ) -> None:
        self.base_url = base_url.rstrip(
            "/",
        )
        self.app_context_env_var = app_context_env_var
        self.http_client = http_client
        self._cache: dict[str, str] = {}

    async def get(
        self,
        key_name: str,
    ) -> str:
        if key_name in self._cache:
            return self._cache[key_name]
        await self._refresh_cache()
        if key_name in self._cache:
            return self._cache[key_name]
        raise ProviderConfigurationError(
            f"Keymaker key not found: {key_name}",
        )

    async def _refresh_cache(
        self,
    ) -> None:
        app_context = os.getenv(
            self.app_context_env_var,
        )
        if not app_context:
            raise ProviderConfigurationError(
                f"Missing required {self.app_context_env_var} for Anthropic Vertex Keymaker auth",
            )

        response = await self.http_client.get(
            f"{self.base_url}{self._ALL_OBJECTS_PATH}",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-KM-APP-CONTEXT": _maybe_base64_decode(
                    app_context,
                )
                or "",
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise ProviderConfigurationError(
                f"Keymaker request failed: HTTP {error.response.status_code}",
            ) from error

        data = response.json() or {}
        cache: dict[str, str] = {}
        for item in data.get(
            "nonkeys",
            [],
        ):
            nonkey = item.get(
                "nonkey",
                {},
            )
            if (
                nonkey.get(
                    "state",
                )
                != "enabled"
            ):
                continue
            name = nonkey.get(
                "name",
            )
            if not name:
                continue
            cache[name] = (
                _maybe_base64_decode(
                    nonkey.get(
                        "encoded_key_data",
                        "",
                    ),
                )
                or ""
            )

        for item in data.get(
            "secretkeys",
            [],
        ):
            secretkey = item.get(
                "secretkey",
                {},
            )
            if (
                secretkey.get(
                    "state",
                )
                != "enabled"
            ):
                continue
            name = secretkey.get(
                "name",
            )
            if not name:
                continue
            cache[name] = (
                _maybe_base64_decode(
                    secretkey.get(
                        "encoded_secret_key",
                    )
                    or secretkey.get(
                        "encoded_key_data",
                        "",
                    ),
                )
                or ""
            )

        self._cache = cache


class AnthropicVertexChatProvider:
    def __init__(
        self,
        *,
        config: _AnthropicVertexConfig,
        timeout_s: float | None = None,
        http_client: httpx.AsyncClient | None = None,
        keymaker_client: _AnthropicVertexKeymakerClient | None = None,
    ) -> None:
        self.config = config
        self.timeout_s = timeout_s
        self.base_url = config.base_url
        self.http_client = http_client or httpx.AsyncClient(
            timeout=timeout_s or 300.0,
        )
        self.keymaker_client = keymaker_client
        self._auth_token: str | None = None
        self._auth_expires_at: datetime | None = None

    async def generate(
        self,
        request: ProviderRequest,
    ) -> ProviderResponse:
        _require_token_pricing(
            settings=request.settings,
            model_id=request.model_id,
            provider_name="anthropic",
            anthropic_cache_pricing=True,
        )
        cache_control = {
            "type": "ephemeral",
            "ttl": "5m",
        }
        system_prompt, messages = _format_messages_for_anthropic(
            request.messages,
            cache_control=cache_control,
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
        call_settings.pop(
            "anthropic_cache_ttl",
            None,
        )
        vertex_anthropic_streaming = bool(
            call_settings.pop(
                "vertex_anthropic_streaming",
                True,
            ),
        )
        timeout_s = call_settings.pop(
            "timeout_s",
            self.timeout_s,
        )
        output_config = call_settings.pop(
            "output_config",
            None,
        )
        max_tokens = call_settings.pop(
            "max_tokens",
            _default_anthropic_max_tokens(
                model_id=request.model_id,
                thinking=call_settings.get(
                    "thinking",
                ),
                output_config=output_config,
            ),
        )

        payload: dict[str, Any] = {
            "anthropic_version": "vertex-2023-10-16",
            "messages": messages,
            "max_tokens": max_tokens,
            **call_settings,
        }
        if system_prompt:
            payload["system"] = system_prompt
        if formatted_tools:
            payload["tools"] = formatted_tools
        if output_config is not None:
            payload["output_config"] = output_config

        await self._ensure_token()
        started_at = time.perf_counter()
        if vertex_anthropic_streaming:
            data = await self._stream_raw_predict(
                request.model_id,
                payload,
                timeout_s=timeout_s,
            )
        else:
            response = await self._post_raw_predict(
                request.model_id,
                payload,
                timeout_s=timeout_s,
            )
            data = response.json() or {}
        duration_ms = (time.perf_counter() - started_at) * 1000.0

        assistant_text_parts: list[str] = []
        assistant_thinking_parts: list[str] = []
        tool_calls: list[ProviderToolCall] = []
        for block in data.get(
            "content",
            [],
        ):
            if not isinstance(
                block,
                dict,
            ):
                continue
            block_type = block.get(
                "type",
            )
            if block_type == "thinking":
                thinking_text = block.get(
                    "thinking",
                )
                if thinking_text:
                    assistant_thinking_parts.append(
                        thinking_text,
                    )
                continue
            if block_type == "text":
                assistant_text_parts.append(
                    block.get(
                        "text",
                        "",
                    ),
                )
                continue
            if block_type == "tool_use":
                tool_calls.append(
                    ProviderToolCall(
                        id=block.get(
                            "id",
                            "",
                        ),
                        name=block.get(
                            "name",
                            "",
                        ),
                        arguments=block.get(
                            "input",
                            {},
                        )
                        or {},
                    ),
                )

        response_message = ProviderMessage(
            role=ProviderMessageRole.ASSISTANT,
            thinking="\n\n".join(
                assistant_thinking_parts,
            )
            or None,
            content="".join(
                assistant_text_parts,
            )
            or None,
            tool_calls=tool_calls,
        )
        usage_data = (
            data.get(
                "usage",
                {},
            )
            or {}
        )
        input_tokens = int(
            usage_data.get(
                "input_tokens",
                0,
            )
            or 0,
        )
        output_tokens = int(
            usage_data.get(
                "output_tokens",
                0,
            )
            or 0,
        )
        cache_creation_input_tokens = int(
            usage_data.get(
                "cache_creation_input_tokens",
                0,
            )
            or 0,
        )
        cache_read_input_tokens = int(
            usage_data.get(
                "cache_read_input_tokens",
                0,
            )
            or 0,
        )
        usage = ProviderUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=(
                input_tokens
                + output_tokens
                + cache_creation_input_tokens
                + cache_read_input_tokens
            ),
            cache_creation_input_tokens=cache_creation_input_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
            input_token_details={
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
            },
            estimated_cost_usd=_estimate_token_cost_usd(
                settings={
                    **request.settings,
                    "anthropic_cache_ttl": "5m",
                },
                model_id=request.model_id,
                provider_name="anthropic",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_creation_input_tokens=cache_creation_input_tokens,
                cache_read_input_tokens=cache_read_input_tokens,
                input_tokens_include_cache_tokens=False,
                anthropic_cache_pricing=True,
            ),
            response_time_ms=duration_ms,
        )
        return ProviderResponse(
            message=response_message,
            usage=usage,
            provider_response_id=data.get(
                "id",
            ),
        )

    async def _ensure_token(
        self,
    ) -> None:
        if (
            self._auth_token
            and self._auth_expires_at
            and datetime.now()
            + timedelta(
                minutes=5,
            )
            < self._auth_expires_at
        ):
            return

        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self.config.require_app_context:
            if self.config.keymaker_base_url is None:
                raise ProviderConfigurationError(
                    "Missing required WIKIARENA_VERTEX_KEYMAKER_BASE_URL for Anthropic Vertex auth",
                )
            keymaker_client = self.keymaker_client
            if keymaker_client is None:
                keymaker_client = _AnthropicVertexKeymakerClient(
                    base_url=self.config.keymaker_base_url,
                    app_context_env_var=self.config.keymaker_app_context_env_var,
                    http_client=self.http_client,
                )
                self.keymaker_client = keymaker_client
            headers["x-cosmos-application-context"] = await keymaker_client.get(
                self.config.aiml_gateway_app_context_key_name,
            )

        response = await self._post_json_with_retries(
            f"{self.config.base_url.rstrip('/')}/v1/aimlgenaigatewayserv/gcpAuth/generateImpersonationAuthToken",
            headers=headers,
            payload={
                "gcp_project_name": self.config.project,
                "cosmos_app_id": self.config.cosmos_app_id,
                "cosmos_app_scope": self.config.cosmos_app_scope,
            },
            provider_name="Anthropic Vertex token endpoint",
            max_attempts=3,
        )
        data = response.json() or {}
        self._auth_token = data.get(
            "auth_token",
        )
        if not self._auth_token:
            raise ProviderConfigurationError(
                "Anthropic Vertex token endpoint did not return auth_token",
            )
        token_ttl = int(
            data.get(
                "token_expiry_window_seconds",
                self.config.token_expiry_window_seconds_default,
            )
            or self.config.token_expiry_window_seconds_default,
        )
        self._auth_expires_at = datetime.now() + timedelta(
            seconds=token_ttl,
        )

    async def _post_raw_predict(
        self,
        model_id: str,
        payload: dict[str, Any],
        *,
        timeout_s: float | None,
    ) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self._auth_token}",
            "x-cosmos-app-id": self.config.cosmos_app_id,
            "Content-Type": "application/json",
        }
        if self.config.beta_headers:
            headers["anthropic-beta"] = ",".join(
                dict.fromkeys(
                    self.config.beta_headers,
                ),
            )
        return await self._post_json_with_retries(
            (
                f"{self.config.model_base_url.rstrip('/')}/v1/projects/"
                f"{self.config.project}/locations/{self.config.location}/publishers/"
                f"anthropic/models/{model_id}:rawPredict"
            ),
            headers=headers,
            payload=payload,
            provider_name="Anthropic Vertex",
            max_attempts=5,
            timeout_s=timeout_s,
            retry_timeouts=False,
        )

    async def _stream_raw_predict(
        self,
        model_id: str,
        payload: dict[str, Any],
        *,
        timeout_s: float | None,
    ) -> dict[str, Any]:
        headers = {
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {self._auth_token}",
            "x-cosmos-app-id": self.config.cosmos_app_id,
            "Content-Type": "application/json",
        }
        if self.config.beta_headers:
            headers["anthropic-beta"] = ",".join(
                dict.fromkeys(
                    self.config.beta_headers,
                ),
            )
        url = (
            f"{self.config.model_base_url.rstrip('/')}/v1/projects/"
            f"{self.config.project}/locations/{self.config.location}/publishers/"
            f"anthropic/models/{model_id}:streamRawPredict"
        )
        stream_payload = {
            **payload,
            "stream": True,
        }
        last_error: Exception | None = None
        for attempt in range(
            5,
        ):
            try:
                async with self.http_client.stream(
                    "POST",
                    url,
                    headers=headers,
                    json=stream_payload,
                    timeout=timeout_s,
                ) as response:
                    response.raise_for_status()
                    return await _parse_anthropic_sse_stream(
                        response,
                    )
            except httpx.HTTPStatusError as error:
                status_code = error.response.status_code
                last_error = error
                if status_code == 401:
                    self._auth_token = None
                    self._auth_expires_at = None
                    raise ProviderConfigurationError(
                        "Anthropic Vertex authentication failed: HTTP 401",
                    ) from error
                if status_code == 429:
                    if attempt < 4:
                        await _sleep_for_retry(
                            error.response.headers.get(
                                "Retry-After",
                            ),
                            attempt=attempt,
                        )
                        continue
                    raise ProviderRateLimitError(
                        "Anthropic Vertex rate limit exceeded",
                    ) from error
                if status_code >= 500 and attempt < 4:
                    await _sleep_for_retry(
                        None,
                        attempt=attempt,
                    )
                    continue
                raise ProviderError(
                    f"Anthropic Vertex request failed: HTTP {status_code}: {error.response.text}",
                ) from error
            except httpx.TimeoutException as error:
                raise ProviderTimeoutError(
                    "Anthropic Vertex timed out",
                ) from error
            except httpx.RequestError as error:
                last_error = error
                if attempt < 4:
                    await _sleep_for_retry(
                        None,
                        attempt=attempt,
                    )
                    continue
                raise ProviderError(
                    f"Anthropic Vertex request failed: {error}",
                ) from error

        raise ProviderError(
            "Anthropic Vertex request failed",
        ) from last_error

    async def _post_json_with_retries(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
        provider_name: str,
        max_attempts: int,
        timeout_s: float | None = None,
        retry_timeouts: bool = True,
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(
            max_attempts,
        ):
            try:
                response = await self.http_client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=timeout_s,
                )
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as error:
                status_code = error.response.status_code
                last_error = error
                if status_code == 401:
                    self._auth_token = None
                    self._auth_expires_at = None
                    raise ProviderConfigurationError(
                        f"{provider_name} authentication failed: HTTP 401",
                    ) from error
                if status_code == 429:
                    if attempt < max_attempts - 1:
                        await _sleep_for_retry(
                            error.response.headers.get(
                                "Retry-After",
                            ),
                            attempt=attempt,
                        )
                        continue
                    raise ProviderRateLimitError(
                        f"{provider_name} rate limit exceeded",
                    ) from error
                if status_code >= 500 and attempt < max_attempts - 1:
                    await _sleep_for_retry(
                        None,
                        attempt=attempt,
                    )
                    continue
                raise ProviderError(
                    f"{provider_name} request failed: HTTP {status_code}: {error.response.text}",
                ) from error
            except httpx.TimeoutException as error:
                last_error = error
                if retry_timeouts and attempt < max_attempts - 1:
                    await _sleep_for_retry(
                        None,
                        attempt=attempt,
                    )
                    continue
                raise ProviderTimeoutError(
                    f"{provider_name} timed out",
                ) from error
            except httpx.RequestError as error:
                last_error = error
                if attempt < max_attempts - 1:
                    await _sleep_for_retry(
                        None,
                        attempt=attempt,
                    )
                    continue
                raise ProviderError(
                    f"{provider_name} request failed: {error}",
                ) from error

        raise ProviderError(
            f"{provider_name} request failed",
        ) from last_error


def create_provider_client(
    provider_name: str,
    provider_settings: dict[str, Any] | None = None,
) -> ModelProvider:
    resolved_provider_settings = dict(
        provider_settings or {},
    )
    normalized_provider_name = provider_name.strip().lower()

    if normalized_provider_name in {"openai", "openai-compatible"}:
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
            default_api_mode=(
                "responses"
                if normalized_provider_name == "openai"
                else "chat_completions"
            ),
            supported_api_modes=(
                {"responses"}
                if normalized_provider_name == "openai"
                else {"chat_completions", "responses"}
            ),
            prompt_cache_key=_pick_first(
                resolved_provider_settings.pop(
                    "prompt_cache_key",
                    None,
                ),
                _default_prompt_cache_key()
                if normalized_provider_name == "openai"
                else None,
            ),
            pricing_provider_name=normalized_provider_name,
        )

    if normalized_provider_name == "codex":
        auth_file = _resolve_codex_auth_file(
            resolved_provider_settings.pop(
                "auth_file",
                None,
            ),
            provider_name=provider_name,
        )
        return CodexChatProvider(
            auth_file=auth_file,
            base_url=_pick_first(
                resolved_provider_settings.pop(
                    "base_url",
                    None,
                ),
            ),
            timeout_s=resolved_provider_settings.pop(
                "timeout_s",
                None,
            ),
            originator=_pick_first(
                resolved_provider_settings.pop(
                    "originator",
                    None,
                ),
                _CODEX_DEFAULT_ORIGINATOR,
            )
            or _CODEX_DEFAULT_ORIGINATOR,
            user_agent=_pick_first(
                resolved_provider_settings.pop(
                    "user_agent",
                    None,
                ),
                _CODEX_DEFAULT_USER_AGENT,
            )
            or _CODEX_DEFAULT_USER_AGENT,
            prompt_cache_key=resolved_provider_settings.pop(
                "prompt_cache_key",
                None,
            ),
            codex_transport=resolved_provider_settings.pop(
                "codex_transport",
                None,
            ),
            websocket_prewarm=bool(
                resolved_provider_settings.pop(
                    "codex_websocket_prewarm",
                    False,
                ),
            ),
        )

    if normalized_provider_name == "claude-code":
        from wikiarena.providers.claude_code import ClaudeCodeProvider

        return ClaudeCodeProvider(
            claude_bin=resolved_provider_settings.pop(
                "claude_bin",
                None,
            ),
            oauth_token=_pick_first(
                resolved_provider_settings.pop(
                    "oauth_token",
                    None,
                ),
                os.getenv(
                    "CLAUDE_CODE_OAUTH_TOKEN",
                ),
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
            default_api_mode="chat_completions",
            supported_api_modes={"chat_completions"},
            pricing_provider_name="openrouter",
        )

    if normalized_provider_name == "anthropic":
        anthropic_transport = _pick_first(
            resolved_provider_settings.pop(
                "anthropic_transport",
                None,
            ),
            os.getenv(
                "WIKIARENA_ANTHROPIC_TRANSPORT",
            ),
            "messages",
        )
        if (
            str(
                anthropic_transport,
            )
            .strip()
            .lower()
            == "vertex"
        ):
            return AnthropicVertexChatProvider(
                config=_anthropic_vertex_config_from_environment(
                    resolved_provider_settings,
                ),
                timeout_s=resolved_provider_settings.pop(
                    "timeout_s",
                    None,
                ),
            )

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


def _resolve_codex_auth_file(
    configured_auth_file: str | None,
    *,
    provider_name: str,
) -> Path:
    auth_file_value = _pick_first(
        configured_auth_file,
        os.getenv(
            "CODEX_AUTH_FILE",
        ),
    )
    if auth_file_value is None:
        default_auth_file = _default_codex_auth_file()
        if default_auth_file.exists():
            return default_auth_file
        raise ProviderConfigurationError(
            f"Missing required auth_file for provider '{provider_name}'",
        )

    auth_file = Path(
        auth_file_value,
    ).expanduser()
    if not auth_file.exists():
        raise ProviderConfigurationError(
            f"Codex auth file not found: {auth_file}",
        )
    return auth_file


def _default_codex_auth_file() -> Path:
    return Path.home() / ".codex" / "auth.json"


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


def _anthropic_vertex_config_from_environment(
    provider_settings: dict[str, Any],
) -> _AnthropicVertexConfig:
    base_url = _require_value(
        _pick_first(
            provider_settings.pop(
                "vertex_base_url",
                None,
            ),
            os.getenv(
                "WIKIARENA_VERTEX_BASE_URL",
            ),
        ),
        "WIKIARENA_VERTEX_BASE_URL",
        "anthropic",
    )
    model_base_url = _pick_first(
        provider_settings.pop(
            "vertex_model_base_url",
            None,
        ),
        os.getenv(
            "WIKIARENA_VERTEX_MODEL_BASE_URL",
        ),
        "https://aiplatform.googleapis.com",
    )
    project = _require_value(
        _pick_first(
            provider_settings.pop(
                "vertex_project",
                None,
            ),
            os.getenv(
                "WIKIARENA_VERTEX_PROJECT",
            ),
        ),
        "WIKIARENA_VERTEX_PROJECT",
        "anthropic",
    )
    location = _pick_first(
        provider_settings.pop(
            "vertex_location",
            None,
        ),
        os.getenv(
            "WIKIARENA_VERTEX_LOCATION",
        ),
        "global",
    )
    cosmos_app_id = _require_value(
        _pick_first(
            provider_settings.pop(
                "vertex_cosmos_app_id",
                None,
            ),
            os.getenv(
                "WIKIARENA_VERTEX_COSMOS_APP_ID",
            ),
        ),
        "WIKIARENA_VERTEX_COSMOS_APP_ID",
        "anthropic",
    )
    cosmos_app_scope = _require_value(
        _pick_first(
            provider_settings.pop(
                "vertex_cosmos_app_scope",
                None,
            ),
            os.getenv(
                "WIKIARENA_VERTEX_COSMOS_APP_SCOPE",
            ),
        ),
        "WIKIARENA_VERTEX_COSMOS_APP_SCOPE",
        "anthropic",
    )
    aiml_gateway_app_context_key_name = _require_value(
        _pick_first(
            provider_settings.pop(
                "vertex_aiml_gateway_app_context_key_name",
                None,
            ),
            os.getenv(
                "WIKIARENA_VERTEX_AIML_GATEWAY_APP_CONTEXT_KEY_NAME",
            ),
        ),
        "WIKIARENA_VERTEX_AIML_GATEWAY_APP_CONTEXT_KEY_NAME",
        "anthropic",
    )
    beta_headers_value = _pick_first(
        provider_settings.pop(
            "vertex_anthropic_beta_headers",
            None,
        ),
        os.getenv(
            "WIKIARENA_VERTEX_ANTHROPIC_BETA_HEADERS",
        ),
    )
    require_app_context = _bool_from_setting(
        _pick_first(
            provider_settings.pop(
                "vertex_require_app_context",
                None,
            ),
            os.getenv(
                "WIKIARENA_VERTEX_REQUIRE_APP_CONTEXT",
            ),
        ),
        default=True,
    )
    return _AnthropicVertexConfig(
        base_url=base_url,
        model_base_url=model_base_url or "https://aiplatform.googleapis.com",
        project=project,
        location=location or "global",
        cosmos_app_id=cosmos_app_id,
        cosmos_app_scope=cosmos_app_scope,
        aiml_gateway_app_context_key_name=aiml_gateway_app_context_key_name,
        keymaker_base_url=_pick_first(
            provider_settings.pop(
                "vertex_keymaker_base_url",
                None,
            ),
            os.getenv(
                "WIKIARENA_VERTEX_KEYMAKER_BASE_URL",
            ),
        ),
        keymaker_app_context_env_var=_pick_first(
            provider_settings.pop(
                "vertex_keymaker_app_context_env_var",
                None,
            ),
            os.getenv(
                "WIKIARENA_VERTEX_KEYMAKER_APP_CONTEXT_ENV_VAR",
            ),
            "KM_APP_CONTEXT_FCIAGENT",
        )
        or "KM_APP_CONTEXT_FCIAGENT",
        require_app_context=require_app_context,
        token_expiry_window_seconds_default=int(
            _pick_first(
                provider_settings.pop(
                    "vertex_token_expiry_window_seconds_default",
                    None,
                ),
                os.getenv(
                    "WIKIARENA_VERTEX_TOKEN_EXPIRY_WINDOW_SECONDS_DEFAULT",
                ),
                "1800",
            )
            or "1800",
        ),
        beta_headers=_split_header_list(
            beta_headers_value,
        ),
    )


def _split_header_list(
    value: str | None,
) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(
        item.strip()
        for item in value.split(
            ",",
        )
        if item.strip()
    )


def _bool_from_setting(
    value: str | None,
    *,
    default: bool,
) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True
    if normalized in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False
    raise ProviderConfigurationError(
        f"Unsupported boolean setting value: {value}",
    )


def _maybe_base64_decode(
    value: str | None,
) -> str | None:
    if not value:
        return value
    if (
        len(
            value,
        )
        % 4
        != 0
    ):
        return value
    if not re.match(
        r"^[A-Za-z0-9+/]*={0,2}$",
        value,
    ):
        return value
    try:
        return base64.b64decode(
            value,
        ).decode(
            "utf-8",
        )
    except Exception:
        return value


async def _sleep_for_retry(
    retry_after: str | None,
    *,
    attempt: int,
) -> None:
    delay_s: float | None = None
    if retry_after:
        try:
            delay_s = float(
                retry_after,
            )
        except ValueError:
            delay_s = None
    if delay_s is None:
        delay_s = min(
            0.5 * (2**attempt),
            8.0,
        )
    await asyncio.sleep(
        delay_s,
    )


def _require_string_field(
    value: Any,
    *,
    field_name: str,
    context: str,
) -> str:
    if (
        isinstance(
            value,
            str,
        )
        and value
    ):
        return value
    raise ProviderConfigurationError(
        f"{context} is missing {field_name}",
    )


def _string_or_none(
    value: Any,
) -> str | None:
    if (
        isinstance(
            value,
            str,
        )
        and value
    ):
        return value
    return None


def _default_anthropic_max_tokens(
    *,
    model_id: str,
    thinking: Any,
    output_config: Any,
) -> int:
    if model_id in {
        "claude-opus-4-7",
        "claude-opus-4-6",
    } and (
        isinstance(
            thinking,
            dict,
        )
        and thinking.get(
            "type",
        )
        == "adaptive"
    ):
        return 128_000

    if (
        model_id
        in {
            "claude-opus-4-7",
            "claude-opus-4-6",
        }
        and isinstance(
            output_config,
            dict,
        )
        and output_config.get(
            "effort",
        )
        in {
            "max",
            "xhigh",
        }
    ):
        return 128_000

    if model_id in {
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-sonnet-4-6",
    }:
        return 64_000

    return 1024


def _load_codex_auth_state(
    auth_file: Path,
) -> _CodexAuthState:
    if not auth_file.exists():
        raise ProviderConfigurationError(
            f"Codex auth file not found: {auth_file}",
        )

    try:
        raw_payload = json.loads(
            auth_file.read_text(),
        )
    except (OSError, json.JSONDecodeError) as error:
        raise ProviderConfigurationError(
            f"Failed to read Codex auth file: {auth_file}",
        ) from error

    if not isinstance(
        raw_payload,
        dict,
    ):
        raise ProviderConfigurationError(
            f"Codex auth file has invalid JSON structure: {auth_file}",
        )

    raw_tokens = raw_payload.get(
        "tokens",
    )
    if not isinstance(
        raw_tokens,
        dict,
    ):
        raise ProviderConfigurationError(
            f"Codex auth file is missing tokens: {auth_file}",
        )

    access_token = _require_string_field(
        raw_tokens.get(
            "access_token",
        ),
        field_name="tokens.access_token",
        context=f"Codex auth file {auth_file}",
    )
    refresh_token = _string_or_none(
        raw_tokens.get(
            "refresh_token",
        ),
    )
    id_token = _string_or_none(
        raw_tokens.get(
            "id_token",
        ),
    )
    account_id = _extract_codex_account_id(
        id_token=id_token,
        access_token=access_token,
        fallback_account_id=_string_or_none(
            raw_tokens.get(
                "account_id",
            ),
        ),
    )

    return _CodexAuthState(
        auth_file=auth_file,
        access_token=access_token,
        refresh_token=refresh_token,
        account_id=account_id,
        id_token=id_token,
        expires_at_s=_extract_jwt_expiry_s(
            access_token,
        ),
        raw_payload=raw_payload,
    )


def _codex_auth_token_needs_refresh(
    auth_state: _CodexAuthState,
) -> bool:
    if auth_state.expires_at_s is None:
        return False
    return auth_state.expires_at_s <= (time.time() + _CODEX_AUTH_REFRESH_MARGIN_S)


def _extract_codex_account_id(
    *,
    id_token: str | None,
    access_token: str | None,
    fallback_account_id: str | None,
) -> str | None:
    for token in (
        id_token,
        access_token,
    ):
        claims = _parse_jwt_claims(
            token,
        )
        account_id = _extract_codex_account_id_from_claims(
            claims,
        )
        if account_id is not None:
            return account_id
    return fallback_account_id


def _parse_jwt_claims(
    token: str | None,
) -> dict[str, Any] | None:
    if token is None:
        return None
    parts = token.split(
        ".",
    )
    if (
        len(
            parts,
        )
        != 3
    ):
        return None
    payload = parts[1]
    padding = "=" * (
        -len(
            payload,
        )
        % 4
    )
    try:
        decoded_payload = base64.urlsafe_b64decode(
            payload + padding,
        )
        claims = json.loads(
            decoded_payload.decode(),
        )
    except (
        ValueError,
        json.JSONDecodeError,
    ):
        return None
    if not isinstance(
        claims,
        dict,
    ):
        return None
    return claims


def _extract_codex_account_id_from_claims(
    claims: dict[str, Any] | None,
) -> str | None:
    if not isinstance(
        claims,
        dict,
    ):
        return None
    direct_account_id = _string_or_none(
        claims.get(
            "chatgpt_account_id",
        ),
    )
    if direct_account_id is not None:
        return direct_account_id

    auth_claims = claims.get(
        "https://api.openai.com/auth",
    )
    if isinstance(
        auth_claims,
        dict,
    ):
        nested_account_id = _string_or_none(
            auth_claims.get(
                "chatgpt_account_id",
            ),
        )
        if nested_account_id is not None:
            return nested_account_id
        organizations = auth_claims.get(
            "organizations",
        )
        if isinstance(
            organizations,
            list,
        ):
            for organization in organizations:
                if not isinstance(
                    organization,
                    dict,
                ):
                    continue
                organization_id = _string_or_none(
                    organization.get(
                        "id",
                    ),
                )
                if organization_id is not None:
                    return organization_id

    organizations = claims.get(
        "organizations",
    )
    if isinstance(
        organizations,
        list,
    ):
        for organization in organizations:
            if not isinstance(
                organization,
                dict,
            ):
                continue
            organization_id = _string_or_none(
                organization.get(
                    "id",
                ),
            )
            if organization_id is not None:
                return organization_id
    return None


def _extract_jwt_expiry_s(
    token: str | None,
) -> float | None:
    claims = _parse_jwt_claims(
        token,
    )
    if not isinstance(
        claims,
        dict,
    ):
        return None
    exp = claims.get(
        "exp",
    )
    if isinstance(
        exp,
        (int, float),
    ):
        return float(
            exp,
        )
    return None


def _split_system_instructions_for_codex(
    messages: list[ProviderMessage],
) -> tuple[str, list[ProviderMessage]]:
    instruction_parts: list[str] = []
    remaining_messages: list[ProviderMessage] = []
    for message in messages:
        if message.role == ProviderMessageRole.SYSTEM:
            if message.content:
                instruction_parts.append(
                    message.content,
                )
            continue
        remaining_messages.append(
            message,
        )

    instructions = "\n\n".join(
        instruction_parts,
    ).strip()
    return instructions, remaining_messages


def _pop_codex_service_tier(
    call_settings: dict[str, Any],
) -> str | None:
    service_tier = call_settings.pop(
        "service_tier",
        None,
    )
    if service_tier is None:
        return None

    normalized_service_tier = (
        str(
            service_tier,
        )
        .strip()
        .lower()
    )
    if normalized_service_tier in {
        "",
        "auto",
        "default",
    }:
        return None
    if normalized_service_tier in {
        "fast",
        "priority",
    }:
        raise ProviderConfigurationError(
            "Codex provider priority service_tier is disabled",
        )
    raise ProviderConfigurationError(
        "Codex provider only supports service_tier='auto' or service_tier='default'",
    )


def _pop_include_values(
    call_settings: dict[str, Any],
) -> list[str]:
    include_value = call_settings.pop(
        "include",
        None,
    )
    if include_value is None:
        return []
    if isinstance(
        include_value,
        str,
    ):
        return [include_value]
    if isinstance(
        include_value,
        list,
    ):
        return [
            item
            for item in include_value
            if isinstance(
                item,
                str,
            )
        ]
    raise ProviderConfigurationError(
        "Codex provider include setting must be a string or list of strings",
    )


def _pop_codex_passthrough_settings(
    call_settings: dict[str, Any],
) -> dict[str, Any]:
    passthrough_settings: dict[str, Any] = {}
    for setting_name in _CODEX_PASSTHROUGH_SETTINGS:
        if setting_name not in call_settings:
            continue
        passthrough_settings[setting_name] = call_settings.pop(
            setting_name,
        )
    return passthrough_settings


def _unique_preserving_order(
    values: list[str],
) -> list[str]:
    unique_values: list[str] = []
    seen_values: set[str] = set()
    for value in values:
        if value in seen_values:
            continue
        seen_values.add(
            value,
        )
        unique_values.append(
            value,
        )
    return unique_values


def _build_codex_reasoning_config(
    *,
    effort: str | None,
    summary: str | None,
) -> dict[str, str] | None:
    reasoning_config: dict[str, str] = {}
    if effort is not None:
        reasoning_config["effort"] = effort
    if summary is not None:
        reasoning_config["summary"] = summary
    return reasoning_config or None


def _build_codex_request_headers(
    *,
    access_token: str,
    account_id: str | None,
    originator: str,
    user_agent: str,
    session_id: str,
    window_id: str,
    turn_state: str | None,
) -> dict[str, str]:
    headers = {
        "Accept": "text/event-stream",
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "originator": originator,
        "User-Agent": user_agent,
        "session_id": session_id,
        "x-client-request-id": session_id,
        "x-codex-window-id": window_id,
    }
    if turn_state is not None:
        headers["x-codex-turn-state"] = turn_state
    if account_id is not None:
        headers["ChatGPT-Account-Id"] = account_id
    return headers


def _build_codex_websocket_headers(
    *,
    access_token: str,
    account_id: str | None,
    originator: str,
    user_agent: str,
    session_id: str,
    window_id: str,
    turn_state: str | None,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "originator": originator,
        "User-Agent": user_agent,
        "session_id": session_id,
        "x-client-request-id": session_id,
        "x-codex-window-id": window_id,
        "OpenAI-Beta": _CODEX_WEBSOCKET_BETA_HEADER_VALUE,
    }
    if turn_state is not None:
        headers["x-codex-turn-state"] = turn_state
    if account_id is not None:
        headers["ChatGPT-Account-Id"] = account_id
    return headers


def _resolve_codex_transport(
    raw_transport: Any,
    *,
    http_client: Any | None,
    websocket_connect: Any | None,
) -> str:
    if raw_transport is None:
        if http_client is not None and websocket_connect is None:
            return "http"
        return "websocket"

    normalized_transport = (
        str(
            raw_transport,
        )
        .strip()
        .lower()
    )
    if normalized_transport in {
        "http",
        "http_sse",
        "sse",
    }:
        return "http"
    if normalized_transport in {
        "auto",
        "websocket",
        "websockets",
        "ws",
    }:
        return "websocket"
    if normalized_transport in {
        "websocket_only",
        "websocket-only",
        "ws_only",
        "ws-only",
    }:
        return "websocket_only"
    raise ProviderConfigurationError(
        f"Unsupported Codex transport '{raw_transport}'",
    )


def _codex_websocket_url(
    response_url: str,
) -> str:
    parsed_url = urlsplit(
        response_url,
    )
    scheme = parsed_url.scheme
    if scheme == "https":
        scheme = "wss"
    elif scheme == "http":
        scheme = "ws"
    return urlunsplit(
        (
            scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.query,
            parsed_url.fragment,
        ),
    )


async def _connect_codex_websocket(
    url: str,
    *,
    headers: dict[str, str],
    timeout_s: float | None,
) -> Any:
    try:
        import websockets
        from websockets.exceptions import InvalidStatusCode
    except ImportError as error:
        raise ProviderConfigurationError(
            "Codex websocket transport requires the 'websockets' package",
        ) from error

    try:
        return await websockets.connect(
            url,
            extra_headers=headers,
            user_agent_header=None,
            open_timeout=timeout_s,
        )
    except InvalidStatusCode as error:
        status_code = getattr(
            error,
            "status_code",
            None,
        )
        if status_code == 401:
            raise _CodexAuthRefreshRequired(
                "Codex access token expired",
            ) from error
        if status_code == 426:
            raise _CodexWebSocketFallbackToHttp(
                "Codex websocket upgrade is unavailable",
            ) from error
        if status_code == 429:
            raise ProviderRateLimitError(
                "Codex provider rate limit exceeded during websocket connect",
            ) from error
        raise ProviderError(
            f"Codex websocket connect failed: HTTP {status_code}",
        ) from error


def _codex_incremental_input(
    *,
    current_request: dict[str, Any],
    previous_request: dict[str, Any] | None,
    previous_output_items: list[dict[str, Any]],
    allow_empty_delta: bool,
) -> list[dict[str, Any]] | None:
    if previous_request is None:
        return None

    previous_without_input = copy.deepcopy(
        previous_request,
    )
    current_without_input = copy.deepcopy(
        current_request,
    )
    previous_input = previous_without_input.pop(
        "input",
        [],
    )
    current_input = current_without_input.pop(
        "input",
        [],
    )
    if previous_without_input != current_without_input:
        return None
    if not isinstance(
        previous_input,
        list,
    ) or not isinstance(
        current_input,
        list,
    ):
        return None

    baseline = [
        *copy.deepcopy(
            previous_input,
        ),
        *copy.deepcopy(
            previous_output_items,
        ),
    ]
    baseline_length = len(
        baseline,
    )
    if current_input[:baseline_length] != baseline:
        return None
    if not allow_empty_delta and baseline_length == len(
        current_input,
    ):
        return None
    return copy.deepcopy(
        current_input[baseline_length:],
    )


def _codex_output_items_for_incremental_baseline(
    output_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    response_message = _provider_message_from_openai_responses_output(
        [
            _namespace_from_mapping(
                item,
            )
            for item in output_items
        ],
    )
    return _format_messages_for_openai_responses(
        [
            response_message,
        ],
    )


async def _read_codex_error_detail(
    response: Any,
) -> str:
    raw_body = await response.aread()
    body_text = raw_body.decode(
        "utf-8",
        errors="replace",
    ).strip()
    if not body_text:
        return f"HTTP {response.status_code}"
    try:
        payload = json.loads(
            body_text,
        )
    except json.JSONDecodeError:
        return body_text
    if isinstance(
        payload,
        dict,
    ):
        detail = _string_or_none(
            payload.get(
                "detail",
            ),
        )
        if detail is not None:
            return detail
        error_message = _string_or_none(
            payload.get(
                "error",
            ),
        )
        if error_message is not None:
            return error_message
    return body_text


def _codex_refresh_error_detail(
    response: Any,
) -> str:
    body_text = _string_or_none(
        getattr(
            response,
            "text",
            None,
        ),
    )
    if body_text is None:
        return f"Codex token refresh failed with status {response.status_code}"
    try:
        payload = json.loads(
            body_text,
        )
    except json.JSONDecodeError:
        return body_text
    if isinstance(
        payload,
        dict,
    ):
        detail = _string_or_none(
            payload.get(
                "detail",
            ),
        )
        if detail is not None:
            return detail
        error_message = _string_or_none(
            payload.get(
                "error_description",
            ),
        ) or _string_or_none(
            payload.get(
                "error",
            ),
        )
        if error_message is not None:
            return error_message
    return body_text


async def _parse_codex_sse_stream(
    response: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output_items: list[dict[str, Any]] = []
    completed_response: dict[str, Any] = {}

    async for raw_line in response.aiter_lines():
        if not raw_line:
            continue
        if raw_line.startswith(
            "event: ",
        ):
            continue
        if raw_line.startswith(
            "data: ",
        ):
            payload_text = raw_line[6:]
        else:
            payload_text = raw_line
        if payload_text == "[DONE]":
            break
        try:
            event = json.loads(
                payload_text,
            )
        except json.JSONDecodeError as error:
            raise ProviderError(
                "Codex provider request failed: invalid SSE payload",
            ) from error
        if not isinstance(
            event,
            dict,
        ):
            continue
        if _handle_codex_response_event(
            event=event,
            output_items=output_items,
            completed_response=completed_response,
        ):
            continue

    if not output_items:
        completed_output = completed_response.get(
            "output",
        )
        if isinstance(
            completed_output,
            list,
        ):
            output_items = [
                item
                for item in completed_output
                if isinstance(
                    item,
                    dict,
                )
            ]
    return output_items, completed_response


async def _parse_anthropic_sse_stream(
    response: Any,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "content": [],
        "usage": {},
    }
    content_blocks: dict[int, dict[str, Any]] = {}
    tool_input_buffers: dict[int, list[str]] = {}

    async for raw_line in response.aiter_lines():
        if not raw_line:
            continue
        if raw_line.startswith(
            "event: ",
        ):
            continue
        if raw_line.startswith(
            "data: ",
        ):
            payload_text = raw_line[6:]
        else:
            payload_text = raw_line
        if payload_text == "[DONE]":
            break
        try:
            event = json.loads(
                payload_text,
            )
        except json.JSONDecodeError as error:
            raise ProviderError(
                "Anthropic Vertex request failed: invalid SSE payload",
            ) from error
        if not isinstance(
            event,
            dict,
        ):
            continue
        event_type = event.get(
            "type",
        )
        if event_type == "message":
            message.update(
                event,
            )
            break
        if event_type == "error":
            error_payload = event.get(
                "error",
            )
            if isinstance(
                error_payload,
                dict,
            ):
                detail = (
                    _string_or_none(
                        error_payload.get(
                            "message",
                        ),
                    )
                    or _string_or_none(
                        error_payload.get(
                            "type",
                        ),
                    )
                    or "stream error"
                )
            else:
                detail = "stream error"
            raise ProviderError(
                f"Anthropic Vertex request failed: {detail}",
            )
        if event_type == "message_start":
            message_payload = event.get(
                "message",
            )
            if isinstance(
                message_payload,
                dict,
            ):
                message.update(
                    {
                        key: value
                        for key, value in message_payload.items()
                        if key != "content"
                    },
                )
                usage = message_payload.get(
                    "usage",
                )
                if isinstance(
                    usage,
                    dict,
                ):
                    message.setdefault(
                        "usage",
                        {},
                    ).update(
                        usage,
                    )
            continue
        if event_type == "content_block_start":
            index = event.get(
                "index",
            )
            content_block = event.get(
                "content_block",
            )
            if isinstance(
                index,
                int,
            ) and isinstance(
                content_block,
                dict,
            ):
                block = copy.deepcopy(
                    content_block,
                )
                block_type = block.get(
                    "type",
                )
                if block_type == "text":
                    block.setdefault(
                        "text",
                        "",
                    )
                elif block_type == "thinking":
                    block.setdefault(
                        "thinking",
                        "",
                    )
                elif block_type == "tool_use":
                    tool_input_buffers[index] = []
                    block.setdefault(
                        "input",
                        {},
                    )
                content_blocks[index] = block
            continue
        if event_type == "content_block_delta":
            index = event.get(
                "index",
            )
            delta = event.get(
                "delta",
            )
            if not isinstance(
                index,
                int,
            ) or not isinstance(
                delta,
                dict,
            ):
                continue
            block = content_blocks.setdefault(
                index,
                {},
            )
            delta_type = delta.get(
                "type",
            )
            if delta_type == "text_delta":
                block["text"] = (
                    str(
                        block.get(
                            "text",
                            "",
                        ),
                    )
                    + str(
                        delta.get(
                            "text",
                            "",
                        ),
                    )
                )
            elif delta_type == "thinking_delta":
                block["thinking"] = (
                    str(
                        block.get(
                            "thinking",
                            "",
                        ),
                    )
                    + str(
                        delta.get(
                            "thinking",
                            "",
                        ),
                    )
                )
            elif delta_type == "input_json_delta":
                tool_input_buffers.setdefault(
                    index,
                    [],
                ).append(
                    str(
                        delta.get(
                            "partial_json",
                            "",
                        ),
                    ),
                )
            elif delta_type == "signature_delta" and delta.get(
                "signature",
            ):
                block["signature"] = delta.get(
                    "signature",
                )
            continue
        if event_type == "content_block_stop":
            index = event.get(
                "index",
            )
            if isinstance(
                index,
                int,
            ) and index in tool_input_buffers:
                raw_input = "".join(
                    tool_input_buffers[index],
                )
                if raw_input:
                    try:
                        content_blocks[index]["input"] = json.loads(
                            raw_input,
                        )
                    except json.JSONDecodeError as error:
                        raise ProviderError(
                            "Anthropic Vertex request failed: invalid streamed tool input",
                        ) from error
            continue
        if event_type == "message_delta":
            delta = event.get(
                "delta",
            )
            if isinstance(
                delta,
                dict,
            ):
                message.update(
                    delta,
                )
            usage = event.get(
                "usage",
            )
            if isinstance(
                usage,
                dict,
            ):
                message.setdefault(
                    "usage",
                    {},
                ).update(
                    usage,
                )
            continue
        if event_type == "message_stop":
            break

    if content_blocks:
        message["content"] = [
            content_blocks[index]
            for index in sorted(
                content_blocks,
            )
        ]
    return message


async def _parse_codex_websocket_stream(
    websocket: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output_items: list[dict[str, Any]] = []
    completed_response: dict[str, Any] = {}

    while True:
        try:
            raw_message = await websocket.recv()
        except StopAsyncIteration:
            break
        except Exception as error:
            if completed_response and error.__class__.__name__.startswith(
                "ConnectionClosed",
            ):
                break
            raise
        if isinstance(
            raw_message,
            bytes,
        ):
            raw_message = raw_message.decode(
                "utf-8",
                errors="replace",
            )
        if not isinstance(
            raw_message,
            str,
        ):
            continue
        try:
            event = json.loads(
                raw_message,
            )
        except json.JSONDecodeError as error:
            raise ProviderError(
                "Codex provider request failed: invalid websocket payload",
            ) from error
        if not isinstance(
            event,
            dict,
        ):
            continue
        completed = _handle_codex_response_event(
            event=event,
            output_items=output_items,
            completed_response=completed_response,
        )
        if completed:
            break

    if not output_items:
        completed_output = completed_response.get(
            "output",
        )
        if isinstance(
            completed_output,
            list,
        ):
            output_items = [
                item
                for item in completed_output
                if isinstance(
                    item,
                    dict,
                )
            ]
    return output_items, completed_response


def _handle_codex_response_event(
    *,
    event: dict[str, Any],
    output_items: list[dict[str, Any]],
    completed_response: dict[str, Any],
) -> bool:
    event_type = event.get(
        "type",
    )
    if event_type == "response.output_item.done":
        item = event.get(
            "item",
        )
        if isinstance(
            item,
            dict,
        ):
            output_items.append(
                item,
            )
        return False
    if event_type == "response.completed":
        response_payload = event.get(
            "response",
        )
        if isinstance(
            response_payload,
            dict,
        ):
            completed_response.clear()
            completed_response.update(
                response_payload,
            )
        return True
    if event_type == "error":
        detail = (
            _string_or_none(
                event.get(
                    "message",
                ),
            )
            or "Codex stream error"
        )
        raise ProviderError(
            f"Codex provider request failed: {detail}",
        )
    return False


def _namespace_from_mapping(
    value: Any,
) -> Any:
    if isinstance(
        value,
        dict,
    ):
        return SimpleNamespace(
            **{
                key: _namespace_from_mapping(
                    nested_value,
                )
                for key, nested_value in value.items()
            },
        )
    if isinstance(
        value,
        list,
    ):
        return [
            _namespace_from_mapping(
                item,
            )
            for item in value
        ]
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


def _format_messages_for_openai_responses(
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
                    "type": "message",
                    "role": message.role.value,
                    "content": message.content or "",
                },
            )
            continue

        if message.role == ProviderMessageRole.ASSISTANT:
            for reasoning_item in message.reasoning_items:
                formatted_messages.append(
                    _format_openai_reasoning_item(
                        reasoning_item,
                    ),
                )
            if message.content:
                formatted_messages.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": message.content,
                    },
                )
            for tool_call in message.tool_calls:
                function_call_item_id = (
                    _normalize_openai_responses_function_call_item_id(
                        tool_call.id,
                    )
                )
                function_call_call_id = (
                    _normalize_openai_responses_function_call_call_id(
                        tool_call.id,
                    )
                )
                formatted_messages.append(
                    {
                        "type": "function_call",
                        "id": function_call_item_id,
                        "call_id": function_call_call_id,
                        "name": tool_call.name,
                        "arguments": json.dumps(
                            tool_call.arguments,
                            ensure_ascii=False,
                        ),
                        "status": "completed",
                    },
                )
            continue

        formatted_messages.append(
            {
                "type": "function_call_output",
                "call_id": _normalize_openai_responses_function_call_call_id(
                    message.tool_call_id,
                ),
                "output": message.content or "",
                "status": "completed",
            },
        )

    return formatted_messages


def _normalize_openai_responses_function_call_item_id(
    raw_id: str,
) -> str:
    if raw_id.startswith(
        "fc_",
    ):
        return raw_id
    normalized_suffix = _normalize_openai_responses_id_suffix(
        raw_id,
    )
    return f"fc_{normalized_suffix}"


def _normalize_openai_responses_function_call_call_id(
    raw_id: str | None,
) -> str:
    normalized_suffix = _normalize_openai_responses_id_suffix(
        raw_id or "replayed",
    )
    if raw_id is not None and raw_id.startswith(
        "call_",
    ):
        return raw_id
    return f"call_{normalized_suffix}"


def _normalize_openai_responses_id_suffix(
    raw_id: str,
) -> str:
    candidate = raw_id
    if candidate.startswith(
        "call_",
    ):
        candidate = candidate.removeprefix(
            "call_",
        )
    elif candidate.startswith(
        "fc_",
    ):
        candidate = candidate.removeprefix(
            "fc_",
        )
    normalized_characters = [
        character if character.isalnum() or character in {"_", "-"} else "_"
        for character in candidate
    ]
    normalized = "".join(
        normalized_characters,
    ).strip("_")
    if normalized:
        return normalized
    return "replayed"


def _format_messages_for_anthropic(
    messages: list[ProviderMessage],
    *,
    cache_control: dict[str, Any] | None = None,
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

    if cache_control is not None:
        for formatted_message in reversed(
            formatted_messages,
        ):
            if (
                formatted_message.get(
                    "role",
                )
                != "user"
            ):
                continue
            content_blocks = formatted_message.get(
                "content",
            )
            if (
                not isinstance(
                    content_blocks,
                    list,
                )
                or not content_blocks
            ):
                continue
            last_block = content_blocks[-1]
            if isinstance(
                last_block,
                dict,
            ):
                last_block["cache_control"] = dict(
                    cache_control,
                )
                break

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


def _format_tools_for_openai_responses(
    request: ProviderRequest,
) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
            "strict": False,
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


def _extract_openai_thinking_content(
    message: Any,
) -> str | None:
    direct_reasoning = getattr(
        message,
        "reasoning",
        None,
    )
    if isinstance(
        direct_reasoning,
        str,
    ):
        stripped_reasoning = direct_reasoning.strip()
        if stripped_reasoning:
            return stripped_reasoning

    content = getattr(
        message,
        "content",
        None,
    )
    if not isinstance(
        content,
        list,
    ):
        return None

    reasoning_segments: list[str] = []
    for item in content:
        if isinstance(
            item,
            dict,
        ):
            item_type = item.get(
                "type",
            )
            if item_type not in {
                "reasoning",
                "thinking",
            }:
                continue
            segment = item.get("thinking") or item.get("text") or item.get("content")
            if (
                isinstance(
                    segment,
                    str,
                )
                and segment.strip()
            ):
                reasoning_segments.append(
                    segment,
                )
            continue

        item_type = getattr(
            item,
            "type",
            None,
        )
        if item_type not in {
            "reasoning",
            "thinking",
        }:
            continue
        segment = (
            getattr(item, "thinking", None)
            or getattr(item, "text", None)
            or getattr(item, "content", None)
        )
        if (
            isinstance(
                segment,
                str,
            )
            and segment.strip()
        ):
            reasoning_segments.append(
                segment,
            )

    if not reasoning_segments:
        return None
    return "\n\n".join(
        reasoning_segments,
    )


def _provider_message_from_openai_responses_output(
    output_items: list[Any],
) -> ProviderMessage:
    assistant_text_parts: list[str] = []
    tool_calls: list[ProviderToolCall] = []
    reasoning_items: list[ProviderReasoningItem] = []
    thinking_parts: list[str] = []

    for item in output_items:
        item_type = getattr(
            item,
            "type",
            None,
        )
        if item_type == "message":
            assistant_text_parts.extend(
                _extract_openai_responses_message_text_parts(
                    item,
                ),
            )
            continue
        if item_type == "function_call":
            call_id = getattr(
                item,
                "call_id",
                None,
            ) or getattr(
                item,
                "id",
                None,
            )
            if not isinstance(
                call_id,
                str,
            ):
                continue
            tool_calls.append(
                ProviderToolCall(
                    id=call_id,
                    name=getattr(
                        item,
                        "name",
                        "",
                    ),
                    arguments=_parse_json_object(
                        getattr(
                            item,
                            "arguments",
                            "{}",
                        ),
                    ),
                ),
            )
            continue
        if item_type != "reasoning":
            continue
        summary_text = _extract_openai_reasoning_summary_text(
            item,
        )
        if summary_text:
            thinking_parts.append(
                summary_text,
            )
        reasoning_items.append(
            ProviderReasoningItem(
                id=getattr(
                    item,
                    "id",
                    "reasoning",
                ),
                summary=summary_text or None,
                encrypted_content=getattr(
                    item,
                    "encrypted_content",
                    None,
                ),
                status=getattr(
                    item,
                    "status",
                    None,
                ),
            ),
        )

    return ProviderMessage(
        role=ProviderMessageRole.ASSISTANT,
        content="".join(
            assistant_text_parts,
        )
        or None,
        thinking="\n\n".join(
            thinking_parts,
        )
        or None,
        reasoning_items=reasoning_items,
        tool_calls=tool_calls,
    )


def _extract_openai_responses_message_text_parts(
    message_item: Any,
) -> list[str]:
    text_parts: list[str] = []
    content_items = getattr(
        message_item,
        "content",
        [],
    )
    for content_item in content_items:
        if (
            getattr(
                content_item,
                "type",
                None,
            )
            != "output_text"
        ):
            continue
        text_value = getattr(
            content_item,
            "text",
            None,
        )
        if isinstance(
            text_value,
            str,
        ):
            text_parts.append(
                text_value,
            )
    return text_parts


def _extract_openai_reasoning_summary_text(
    reasoning_item: Any,
) -> str:
    summary_parts: list[str] = []
    for summary_item in getattr(
        reasoning_item,
        "summary",
        [],
    ):
        text_value = getattr(
            summary_item,
            "text",
            None,
        )
        if (
            isinstance(
                text_value,
                str,
            )
            and text_value.strip()
        ):
            summary_parts.append(
                text_value,
            )
    return "\n\n".join(
        summary_parts,
    )


def _format_openai_reasoning_item(
    reasoning_item: ProviderReasoningItem,
) -> dict[str, Any]:
    summary_items: list[dict[str, str]] = []
    if reasoning_item.summary:
        summary_items = [
            {
                "type": "summary_text",
                "text": reasoning_item.summary,
            },
        ]
    payload: dict[str, Any] = {
        "type": "reasoning",
        "id": reasoning_item.id,
        "summary": summary_items,
    }
    if reasoning_item.encrypted_content:
        payload["encrypted_content"] = reasoning_item.encrypted_content
    return payload


def _build_openai_responses_reasoning_config(
    *,
    effort: str | None,
    summary: str | None,
) -> dict[str, str] | None:
    reasoning_config: dict[str, str] = {}
    if effort is not None:
        reasoning_config["effort"] = effort
    if summary is not None:
        reasoning_config["summary"] = summary
    return reasoning_config or None


def _messages_since_last_openai_response(
    messages: list[ProviderMessage],
    *,
    last_request_message_count: int,
    last_response_message: ProviderMessage | None,
) -> list[ProviderMessage]:
    pending_messages = list(
        messages[last_request_message_count:],
    )
    if (
        last_response_message is not None
        and pending_messages
        and pending_messages[0] == last_response_message
    ):
        return pending_messages[1:]
    return pending_messages


def _usage_from_openai_response(
    response: Any,
    *,
    model_id: str,
    provider_name: str,
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
    input_token_details = _extract_token_details(
        getattr(
            usage,
            "prompt_tokens_details",
            None,
        ),
    )
    output_token_details = _extract_token_details(
        getattr(
            usage,
            "completion_tokens_details",
            None,
        ),
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
        cache_read_input_tokens=input_token_details.get(
            "cached_tokens",
            0,
        ),
        input_token_details=input_token_details,
        output_token_details=output_token_details,
        estimated_cost_usd=_estimate_token_cost_usd(
            settings=settings,
            model_id=model_id,
            provider_name=provider_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=input_token_details.get(
                "cached_tokens",
                0,
            ),
        ),
        response_time_ms=duration_ms,
    )


def _usage_from_openai_responses_response(
    response: Any,
    *,
    model_id: str,
    provider_name: str,
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

    input_token_details = _extract_token_details(
        getattr(
            usage,
            "input_tokens_details",
            None,
        ),
    )
    output_token_details = _extract_token_details(
        getattr(
            usage,
            "output_tokens_details",
            None,
        ),
    )
    input_tokens = (
        getattr(
            usage,
            "input_tokens",
            0,
        )
        or 0
    )
    output_tokens = (
        getattr(
            usage,
            "output_tokens",
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
        cache_read_input_tokens=input_token_details.get(
            "cached_tokens",
            0,
        ),
        input_token_details=input_token_details,
        output_token_details=output_token_details,
        estimated_cost_usd=_estimate_token_cost_usd(
            settings=settings,
            model_id=model_id,
            provider_name=provider_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=input_token_details.get(
                "cached_tokens",
                0,
            ),
        ),
        response_time_ms=duration_ms,
    )


def _extract_token_details(
    details: Any,
) -> dict[str, int]:
    if details is None:
        return {}

    if hasattr(
        details,
        "model_dump",
    ):
        raw_values = details.model_dump(
            exclude_none=True,
        )
    elif isinstance(
        details,
        dict,
    ):
        raw_values = details
    else:
        candidate_fields = [
            "accepted_prediction_tokens",
            "audio_tokens",
            "cached_tokens",
            "reasoning_tokens",
            "rejected_prediction_tokens",
        ]
        raw_values = {
            field_name: getattr(
                details,
                field_name,
            )
            for field_name in candidate_fields
            if getattr(
                details,
                field_name,
                None,
            )
            is not None
        }

    token_details: dict[str, int] = {}
    for key, value in raw_values.items():
        if not isinstance(
            value,
            (int, float),
        ):
            continue
        token_details[key] = int(
            value,
        )
    return token_details


def _resolve_openai_api_mode(
    settings: dict[str, Any],
    *,
    default_api_mode: str,
) -> str:
    if (
        settings.get(
            "openai_api_mode",
        )
        is not None
    ):
        return str(
            settings["openai_api_mode"],
        )
    if (
        settings.get(
            "openai_reasoning_summary",
        )
        is not None
    ):
        return "responses"
    if bool(
        settings.get(
            "openai_include_encrypted_reasoning",
            False,
        ),
    ):
        return "responses"
    return default_api_mode


def _estimate_token_cost_usd(
    *,
    settings: dict[str, Any],
    model_id: str | None = None,
    provider_name: str | None = None,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
    input_tokens_include_cache_tokens: bool = True,
    anthropic_cache_pricing: bool = False,
) -> float:
    pricing = _resolve_token_pricing(
        settings=settings,
        model_id=model_id,
        provider_name=provider_name,
        anthropic_cache_pricing=anthropic_cache_pricing,
    )
    if pricing is None:
        raise _missing_pricing_error(
            model_id=model_id,
            provider_name=provider_name,
        )
    pricing = _apply_long_context_pricing(
        pricing=pricing,
        context_input_tokens=_context_input_tokens_for_pricing(
            input_tokens=input_tokens,
            cache_creation_input_tokens=cache_creation_input_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
            input_tokens_include_cache_tokens=input_tokens_include_cache_tokens,
        ),
    )

    input_cost_per_1m_tokens = pricing.input_cost_per_1m_tokens
    output_cost_per_1m_tokens = pricing.output_cost_per_1m_tokens
    cache_read_input_cost_per_1m_tokens = (
        pricing.cache_read_input_cost_per_1m_tokens
        if pricing.cache_read_input_cost_per_1m_tokens is not None
        else input_cost_per_1m_tokens
    )
    cache_creation_input_cost_per_1m_tokens = (
        pricing.cache_creation_input_cost_per_1m_tokens
        if pricing.cache_creation_input_cost_per_1m_tokens is not None
        else input_cost_per_1m_tokens
    )
    non_cached_input_tokens = input_tokens
    if input_tokens_include_cache_tokens and not anthropic_cache_pricing:
        non_cached_input_tokens = max(
            input_tokens - cache_creation_input_tokens - cache_read_input_tokens,
            0,
        )

    estimated_cost = (
        (non_cached_input_tokens / 1_000_000) * input_cost_per_1m_tokens
        + (cache_creation_input_tokens / 1_000_000)
        * cache_creation_input_cost_per_1m_tokens
        + (cache_read_input_tokens / 1_000_000) * cache_read_input_cost_per_1m_tokens
        + (output_tokens / 1_000_000) * output_cost_per_1m_tokens
    )

    return estimated_cost


def _require_token_pricing(
    *,
    settings: dict[str, Any],
    model_id: str,
    provider_name: str,
    anthropic_cache_pricing: bool = False,
) -> None:
    if (
        _resolve_token_pricing(
            settings=settings,
            model_id=model_id,
            provider_name=provider_name,
            anthropic_cache_pricing=anthropic_cache_pricing,
        )
        is not None
    ):
        return
    raise _missing_pricing_error(
        model_id=model_id,
        provider_name=provider_name,
    )


def _missing_pricing_error(
    *,
    model_id: str | None,
    provider_name: str | None,
) -> ProviderConfigurationError:
    provider_label = provider_name or "unknown"
    model_label = model_id or "unknown"
    return ProviderConfigurationError(
        "Missing pricing for "
        f"provider '{provider_label}' model '{model_label}'. "
        "Add input_cost_per_1m_tokens and output_cost_per_1m_tokens "
        "to model settings, or add the model to the default pricing table.",
    )


def _resolve_token_pricing(
    *,
    settings: dict[str, Any],
    model_id: str | None,
    provider_name: str | None,
    anthropic_cache_pricing: bool,
) -> _TokenPricing | None:
    default_pricing = _default_token_pricing(
        model_id=model_id,
        provider_name=provider_name,
        settings=settings,
    )
    explicit_base_pricing = (
        "input_cost_per_1m_tokens" in settings
        or "output_cost_per_1m_tokens" in settings
    )
    default_optional_pricing = None if explicit_base_pricing else default_pricing

    input_cost = _float_setting(
        settings,
        "input_cost_per_1m_tokens",
        default_pricing.input_cost_per_1m_tokens if default_pricing else None,
    )
    output_cost = _float_setting(
        settings,
        "output_cost_per_1m_tokens",
        default_pricing.output_cost_per_1m_tokens if default_pricing else None,
    )
    if input_cost is None or output_cost is None:
        return None

    cache_read_cost = _float_setting(
        settings,
        "cache_read_input_cost_per_1m_tokens",
        _float_setting(
            settings,
            "cached_input_cost_per_1m_tokens",
            default_optional_pricing.cache_read_input_cost_per_1m_tokens
            if default_optional_pricing
            else None,
        ),
    )
    if "cache_creation_input_cost_per_1m_tokens" in settings:
        cache_creation_cost = _float_setting(
            settings,
            "cache_creation_input_cost_per_1m_tokens",
            None,
        )
    elif anthropic_cache_pricing:
        cache_creation_cost = input_cost * _anthropic_cache_creation_multiplier(
            settings,
        )
    else:
        cache_creation_cost = (
            default_optional_pricing.cache_creation_input_cost_per_1m_tokens
            if default_optional_pricing
            else None
        )

    if cache_read_cost is None and anthropic_cache_pricing:
        cache_read_cost = input_cost * 0.1

    return _TokenPricing(
        input_cost_per_1m_tokens=input_cost,
        output_cost_per_1m_tokens=output_cost,
        cache_read_input_cost_per_1m_tokens=cache_read_cost,
        cache_creation_input_cost_per_1m_tokens=cache_creation_cost,
        long_context_threshold_input_tokens=_int_setting(
            settings,
            "long_context_threshold_input_tokens",
            default_optional_pricing.long_context_threshold_input_tokens
            if default_optional_pricing
            else None,
        ),
        long_context_input_cost_per_1m_tokens=_float_setting(
            settings,
            "long_context_input_cost_per_1m_tokens",
            default_optional_pricing.long_context_input_cost_per_1m_tokens
            if default_optional_pricing
            else None,
        ),
        long_context_output_cost_per_1m_tokens=_float_setting(
            settings,
            "long_context_output_cost_per_1m_tokens",
            default_optional_pricing.long_context_output_cost_per_1m_tokens
            if default_optional_pricing
            else None,
        ),
        long_context_cache_read_input_cost_per_1m_tokens=_float_setting(
            settings,
            "long_context_cache_read_input_cost_per_1m_tokens",
            _float_setting(
                settings,
                "long_context_cached_input_cost_per_1m_tokens",
                default_optional_pricing.long_context_cache_read_input_cost_per_1m_tokens
                if default_optional_pricing
                else None,
            ),
        ),
        long_context_cache_creation_input_cost_per_1m_tokens=_float_setting(
            settings,
            "long_context_cache_creation_input_cost_per_1m_tokens",
            default_optional_pricing.long_context_cache_creation_input_cost_per_1m_tokens
            if default_optional_pricing
            else None,
        ),
    )


def _default_token_pricing(
    *,
    model_id: str | None,
    provider_name: str | None,
    settings: dict[str, Any],
) -> _TokenPricing | None:
    normalized_model_id = _normalize_pricing_model_id(
        model_id,
    )
    if normalized_model_id is None:
        return None

    if _pricing_provider_uses_anthropic_pricing(
        provider_name,
        normalized_model_id,
    ):
        return _lookup_model_pricing(
            normalized_model_id,
            _ANTHROPIC_MODEL_PRICING,
        )

    if _pricing_provider_uses_openai_pricing(
        provider_name,
        normalized_model_id,
    ):
        return _lookup_model_pricing(
            normalized_model_id,
            _OPENAI_STANDARD_MODEL_PRICING,
        )

    return None


def _normalize_pricing_model_id(
    model_id: str | None,
) -> str | None:
    if model_id is None:
        return None
    normalized_model_id = model_id.strip().lower()
    if not normalized_model_id:
        return None
    if "/" in normalized_model_id:
        normalized_model_id = normalized_model_id.rsplit(
            "/",
            1,
        )[-1]
    if ":" in normalized_model_id:
        normalized_model_id = normalized_model_id.split(
            ":",
            1,
        )[0]
    return normalized_model_id


def _pricing_provider_uses_openai_pricing(
    provider_name: str | None,
    model_id: str,
) -> bool:
    return (provider_name or "").strip().lower() in {
        "codex",
        "openai",
        "openai-compatible",
        "openrouter",
    } or model_id.startswith(
        "gpt-",
    )


def _pricing_provider_uses_anthropic_pricing(
    provider_name: str | None,
    model_id: str,
) -> bool:
    return (provider_name or "").strip().lower() == "anthropic" or model_id.startswith(
        "claude-",
    )


def _lookup_model_pricing(
    model_id: str,
    pricing_table: dict[str, _TokenPricing],
) -> _TokenPricing | None:
    if model_id in pricing_table:
        return pricing_table[model_id]
    matching_model_ids = [
        pricing_model_id
        for pricing_model_id in pricing_table
        if model_id.startswith(
            f"{pricing_model_id}-",
        )
    ]
    if not matching_model_ids:
        return None
    return pricing_table[
        max(
            matching_model_ids,
            key=len,
        )
    ]


def _context_input_tokens_for_pricing(
    *,
    input_tokens: int,
    cache_creation_input_tokens: int,
    cache_read_input_tokens: int,
    input_tokens_include_cache_tokens: bool,
) -> int:
    if input_tokens_include_cache_tokens:
        return input_tokens
    return input_tokens + cache_creation_input_tokens + cache_read_input_tokens


def _apply_long_context_pricing(
    *,
    pricing: _TokenPricing,
    context_input_tokens: int,
) -> _TokenPricing:
    threshold = pricing.long_context_threshold_input_tokens
    if threshold is None or context_input_tokens <= threshold:
        return pricing
    return _TokenPricing(
        input_cost_per_1m_tokens=(
            pricing.long_context_input_cost_per_1m_tokens
            if pricing.long_context_input_cost_per_1m_tokens is not None
            else pricing.input_cost_per_1m_tokens
        ),
        output_cost_per_1m_tokens=(
            pricing.long_context_output_cost_per_1m_tokens
            if pricing.long_context_output_cost_per_1m_tokens is not None
            else pricing.output_cost_per_1m_tokens
        ),
        cache_read_input_cost_per_1m_tokens=(
            pricing.long_context_cache_read_input_cost_per_1m_tokens
            if pricing.long_context_cache_read_input_cost_per_1m_tokens is not None
            else pricing.cache_read_input_cost_per_1m_tokens
        ),
        cache_creation_input_cost_per_1m_tokens=(
            pricing.long_context_cache_creation_input_cost_per_1m_tokens
            if pricing.long_context_cache_creation_input_cost_per_1m_tokens is not None
            else pricing.cache_creation_input_cost_per_1m_tokens
        ),
    )


def _anthropic_cache_creation_multiplier(
    settings: dict[str, Any],
) -> float:
    cache_ttl = (
        str(
            settings.get(
                "anthropic_cache_ttl",
                "5m",
            ),
        )
        .strip()
        .lower()
    )
    if cache_ttl == "1h":
        return 2.0
    return 1.25


def _int_setting(
    settings: dict[str, Any],
    setting_name: str,
    default: int | None,
) -> int | None:
    value = settings.get(
        setting_name,
        default,
    )
    if value is None:
        return None
    return int(
        value,
    )


def _float_setting(
    settings: dict[str, Any],
    setting_name: str,
    default: float | None,
) -> float | None:
    value = settings.get(
        setting_name,
        default,
    )
    if value is None:
        return None
    return float(
        value,
    )


def _anthropic_prompt_caching_enabled(
    settings: dict[str, Any],
) -> bool:
    return bool(
        settings.get(
            "anthropic_prompt_caching",
            False,
        ),
    )


def _build_anthropic_cache_control(
    settings: dict[str, Any],
) -> dict[str, Any] | None:
    if not _anthropic_prompt_caching_enabled(
        settings,
    ):
        return None

    cache_ttl = settings.get(
        "anthropic_cache_ttl",
        "5m",
    )
    if cache_ttl not in {
        "5m",
        "1h",
    }:
        raise ProviderConfigurationError(
            "WikiArena only supports Anthropic prompt caching with ttl='5m' or ttl='1h'",
        )

    return {
        "type": "ephemeral",
        "ttl": cache_ttl,
    }


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
