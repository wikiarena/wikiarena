from __future__ import annotations

import base64
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from typing import Protocol

from anthropic import APITimeoutError as AnthropicTimeoutError
from anthropic import AsyncAnthropic
from anthropic import AnthropicError
from anthropic import RateLimitError as AnthropicRateLimitError
import httpx
from openai import APITimeoutError as OpenAITimeoutError
from openai import AsyncOpenAI
from openai import OpenAIError
from openai import RateLimitError as OpenAIRateLimitError

from wikiarena.providers.types import ProviderMessage
from wikiarena.providers.types import ProviderMessageRole
from wikiarena.providers.types import ProviderReasoningItem
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


_CODEX_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
_CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
_CODEX_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
_CODEX_DEFAULT_ORIGINATOR = "wikiarena"
_CODEX_DEFAULT_USER_AGENT = "wikiarena/codex"
_CODEX_AUTH_REFRESH_MARGIN_S = 60.0


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
    ):
        self.base_url = base_url
        self.timeout_s = timeout_s
        self.default_api_mode = default_api_mode
        self.supported_api_modes = frozenset(
            supported_api_modes or {"chat_completions", "responses"},
        )
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
            return await self._generate_with_responses_api(
                request,
            )
        if resolved_api_mode == "chat_completions":
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
        call_settings.pop(
            "thinking",
            None,
        )
        call_settings.pop(
            "output_config",
            None,
        )

        previous_response_id = None
        response_input = request.messages
        if (
            openai_use_previous_response_id
            and self._previous_response_id is not None
        ):
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
        http_client: Any | None = None,
    ):
        self.auth_file = Path(
            auth_file,
        ).expanduser()
        self.base_url = base_url or _CODEX_RESPONSES_URL
        self.timeout_s = timeout_s
        self.originator = originator
        self.user_agent = user_agent
        self.client = http_client or httpx.AsyncClient(
            timeout=timeout_s,
        )

    async def generate(
        self,
        request: ProviderRequest,
    ) -> ProviderResponse:
        auth_state = _load_codex_auth_state(
            self.auth_file,
        )
        auth_state = await self._refresh_auth_state_if_needed(
            auth_state,
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
        max_output_tokens = call_settings.pop(
            "max_tokens",
            None,
        )
        call_settings.pop(
            "openai_api_mode",
            None,
        )
        call_settings.pop(
            "openai_use_previous_response_id",
            None,
        )
        if call_settings.pop(
            "openai_reasoning_summary",
            None,
        ) is not None:
            raise ProviderConfigurationError(
                "Codex provider does not support openai_reasoning_summary",
            )
        if bool(
            call_settings.pop(
                "openai_include_encrypted_reasoning",
                False,
            ),
        ):
            raise ProviderConfigurationError(
                "Codex provider does not support openai_include_encrypted_reasoning",
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
            **call_settings,
        }
        formatted_tools = _format_tools_for_openai_responses(
            request,
        )
        if formatted_tools:
            call_payload["tools"] = formatted_tools
            call_payload["tool_choice"] = request.tool_choice
        if max_output_tokens is not None:
            call_payload["max_output_tokens"] = max_output_tokens
        reasoning_config = _build_codex_reasoning_config(
            effort=reasoning_effort,
        )
        if reasoning_config is not None:
            call_payload["reasoning"] = reasoning_config

        try:
            output_items, completed_response, duration_ms = (
                await self._stream_response(
                    auth_state=auth_state,
                    call_payload=call_payload,
                )
            )
        except _CodexAuthRefreshRequired:
            auth_state = await self._refresh_auth_state(
                auth_state,
            )
            output_items, completed_response, duration_ms = await self._stream_response(
                auth_state=auth_state,
                call_payload=call_payload,
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
    ) -> tuple[list[dict[str, Any]], dict[str, Any], float]:
        headers = _build_codex_request_headers(
            access_token=auth_state.access_token,
            account_id=auth_state.account_id,
            originator=self.originator,
            user_agent=self.user_agent,
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
            output_items, completed_response = await _parse_codex_sse_stream(
                response,
            )

        duration_ms = (time.perf_counter() - started_at) * 1000.0
        return output_items, completed_response, duration_ms

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
        id_token = _string_or_none(
            refreshed_tokens.get(
                "id_token",
            ),
        ) or auth_state.id_token
        new_refresh_token = _string_or_none(
            refreshed_tokens.get(
                "refresh_token",
            ),
        ) or refresh_token
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
        persisted_payload["last_refresh"] = datetime.now(
            UTC,
        ).isoformat().replace(
            "+00:00",
            "Z",
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
        output_config = call_settings.pop(
            "output_config",
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
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            cache_creation_input_tokens=cache_creation_input_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
            input_token_details={
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
            },
            estimated_cost_usd=_estimate_token_cost_usd(
                settings=request.settings,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cache_creation_input_tokens=cache_creation_input_tokens,
                cache_read_input_tokens=cache_read_input_tokens,
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


def _require_string_field(
    value: Any,
    *,
    field_name: str,
    context: str,
) -> str:
    if isinstance(
        value,
        str,
    ) and value:
        return value
    raise ProviderConfigurationError(
        f"{context} is missing {field_name}",
    )


def _string_or_none(
    value: Any,
) -> str | None:
    if isinstance(
        value,
        str,
    ) and value:
        return value
    return None


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
    return auth_state.expires_at_s <= (
        time.time() + _CODEX_AUTH_REFRESH_MARGIN_S
    )


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
    if len(
        parts,
    ) != 3:
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


def _build_codex_reasoning_config(
    *,
    effort: str | None,
) -> dict[str, str] | None:
    if effort is None:
        return None
    return {
        "effort": effort,
    }


def _build_codex_request_headers(
    *,
    access_token: str,
    account_id: str | None,
    originator: str,
    user_agent: str,
) -> dict[str, str]:
    headers = {
        "Accept": "text/event-stream",
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "originator": originator,
        "User-Agent": user_agent,
        "session_id": f"wikiarena-{uuid.uuid4()}",
    }
    if account_id is not None:
        headers["ChatGPT-Account-Id"] = account_id
    return headers


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
        if not raw_line.startswith(
            "data: ",
        ):
            continue
        payload_text = raw_line[6:]
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
            continue
        if event_type == "response.completed":
            response_payload = event.get(
                "response",
            )
            if isinstance(
                response_payload,
                dict,
            ):
                completed_response = response_payload
            continue
        if event_type == "error":
            detail = _string_or_none(
                event.get(
                    "message",
                ),
            ) or "Codex stream error"
            raise ProviderError(
                f"Codex provider request failed: {detail}",
            )

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
        character
        if character.isalnum() or character in {"_", "-"}
        else "_"
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
            if formatted_message.get(
                "role",
            ) != "user":
                continue
            content_blocks = formatted_message.get(
                "content",
            )
            if not isinstance(
                content_blocks,
                list,
            ) or not content_blocks:
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
        if getattr(
            content_item,
            "type",
            None,
        ) != "output_text":
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
        if isinstance(
            text_value,
            str,
        ) and text_value.strip():
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
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
        response_time_ms=duration_ms,
    )


def _usage_from_openai_responses_response(
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
            input_tokens=input_tokens,
            output_tokens=output_tokens,
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
    if settings.get(
        "openai_api_mode",
    ) is not None:
        return str(
            settings["openai_api_mode"],
        )
    if settings.get(
        "openai_reasoning_summary",
    ) is not None:
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
