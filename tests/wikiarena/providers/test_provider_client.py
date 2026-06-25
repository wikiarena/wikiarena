from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from anthropic import AnthropicError
from openai import OpenAIError

from wikiarena.providers.client import (
    _CODEX_OAUTH_CLIENT_ID,
    _CODEX_OAUTH_TOKEN_URL,
    AnthropicChatProvider,
    AnthropicVertexChatProvider,
    CodexChatProvider,
    OpenAIChatProvider,
    ProviderConfigurationError,
    ProviderError,
    ProviderTimeoutError,
    _anthropic_prompt_caching_enabled,
    _AnthropicVertexConfig,
    _build_anthropic_cache_control,
    _CodexWebSocketFallbackToHttp,
    _estimate_token_cost_usd,
    _format_messages_for_anthropic,
    _format_messages_for_openai_responses,
)
from wikiarena.providers.types import (
    ProviderMessage,
    ProviderMessageRole,
    ProviderReasoningItem,
    ProviderRequest,
    ProviderToolCall,
)


def _create_test_jwt(
    payload: dict[str, object],
) -> str:
    header = (
        base64.urlsafe_b64encode(
            b'{"alg":"none"}',
        )
        .decode()
        .rstrip("=")
    )
    body = (
        base64.urlsafe_b64encode(
            json.dumps(
                payload,
            ).encode(),
        )
        .decode()
        .rstrip("=")
    )
    return f"{header}.{body}.sig"


class _FakeHTTPResponse:
    def __init__(
        self,
        data: dict[str, object],
    ) -> None:
        self._data = data
        self.headers: dict[str, str] = {}
        self.status_code = 200
        self.text = json.dumps(
            data,
        )

    def json(
        self,
    ) -> dict[str, object]:
        return self._data

    def raise_for_status(
        self,
    ) -> None:
        return None


class _FakeAnthropicVertexHTTPClient:
    def __init__(
        self,
    ) -> None:
        self.get_calls: list[dict[str, object]] = []
        self.post_calls: list[dict[str, object]] = []
        self.stream_calls: list[dict[str, object]] = []

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
    ) -> _FakeHTTPResponse:
        self.get_calls.append(
            {
                "url": url,
                "headers": headers,
            },
        )
        return _FakeHTTPResponse(
            {
                "nonkeys": [
                    {
                        "nonkey": {
                            "state": "enabled",
                            "name": "gateway-context",
                            "encoded_key_data": "gateway-secret",
                        },
                    },
                ],
            },
        )

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float | None = None,
    ) -> _FakeHTTPResponse:
        self.post_calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            },
        )
        if url.endswith(
            "/gcpAuth/generateImpersonationAuthToken",
        ):
            return _FakeHTTPResponse(
                {
                    "auth_token": "vertex-token",
                    "token_expiry_window_seconds": 1800,
                },
            )
        return _FakeHTTPResponse(
            {
                "id": "msg_vertex",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "Reasoning summary",
                    },
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "navigate",
                        "input": {
                            "to_page_title": "OpenAI",
                        },
                    },
                ],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cache_creation_input_tokens": 40,
                    "cache_read_input_tokens": 60,
                },
            },
        )

    def stream(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float | None = None,
    ) -> "_FakeStreamContext":
        self.stream_calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            },
        )
        return _FakeStreamContext(
            _FakeStreamResponse(
                status_code=200,
                lines=[
                    'event: message_start',
                    'data: {"type":"message_start","message":{"id":"msg_vertex","type":"message","role":"assistant","content":[],"usage":{"input_tokens":100,"cache_creation_input_tokens":40,"cache_read_input_tokens":60,"output_tokens":1}}}',
                    'event: content_block_start',
                    'data: {"type":"content_block_start","index":0,"content_block":{"type":"thinking","thinking":""}}',
                    'event: content_block_delta',
                    'data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"Reasoning summary"}}',
                    'event: content_block_stop',
                    'data: {"type":"content_block_stop","index":0}',
                    'event: content_block_start',
                    'data: {"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"toolu_1","name":"navigate","input":{}}}',
                    'event: content_block_delta',
                    'data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{\\"to_page_title\\":"}}',
                    'event: content_block_delta',
                    'data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"\\"OpenAI\\"}"}}',
                    'event: content_block_stop',
                    'data: {"type":"content_block_stop","index":1}',
                    'event: message_delta',
                    'data: {"type":"message_delta","delta":{"stop_reason":"tool_use"},"usage":{"output_tokens":20}}',
                    'event: message_stop',
                    'data: {"type":"message_stop"}',
                ],
            ),
        )


class _FakeStreamContext:
    def __init__(
        self,
        response: "_FakeStreamResponse",
    ) -> None:
        self._response = response

    async def __aenter__(
        self,
    ) -> "_FakeStreamResponse":
        return self._response

    async def __aexit__(
        self,
        exc_type,
        exc,
        tb,
    ) -> bool:
        return False


class _FakeStreamResponse:
    def __init__(
        self,
        *,
        status_code: int,
        lines: list[str] | None = None,
        text: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._lines = list(
            lines or [],
        )
        self._text = text or ""
        self.headers = dict(
            headers or {},
        )

    async def aiter_lines(
        self,
    ):
        for line in self._lines:
            yield line

    async def aread(
        self,
    ) -> bytes:
        return self._text.encode()

    def raise_for_status(
        self,
    ) -> None:
        if self.status_code < 400:
            return
        request = httpx.Request(
            "POST",
            "https://example.test/stream",
        )
        response = httpx.Response(
            self.status_code,
            text=self._text,
            request=request,
        )
        raise httpx.HTTPStatusError(
            "stream request failed",
            request=request,
            response=response,
        )


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        json_body: dict[str, object] | None = None,
        text: str | None = None,
    ) -> None:
        self.status_code = status_code
        self._json_body = dict(
            json_body or {},
        )
        self.text = text or ""

    def json(
        self,
    ) -> dict[str, object]:
        return dict(
            self._json_body,
        )


class _FakeCodexHttpClient:
    def __init__(
        self,
        *,
        stream_responses: list[_FakeStreamResponse] | None = None,
        post_responses: list[_FakeResponse] | None = None,
    ) -> None:
        self._stream_responses = list(
            stream_responses or [],
        )
        self._post_responses = list(
            post_responses or [],
        )
        self.stream_calls: list[dict[str, object]] = []
        self.post_calls: list[dict[str, object]] = []

    def stream(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
    ) -> _FakeStreamContext:
        self.stream_calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(
                    headers or {},
                ),
                "json": dict(
                    json or {},
                ),
            },
        )
        return _FakeStreamContext(
            self._stream_responses.pop(
                0,
            ),
        )

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: dict[str, object] | None = None,
    ) -> _FakeResponse:
        self.post_calls.append(
            {
                "url": url,
                "headers": dict(
                    headers or {},
                ),
                "data": dict(
                    data or {},
                ),
            },
        )
        return self._post_responses.pop(
            0,
        )


class _FakeCodexWebSocket:
    def __init__(
        self,
        *,
        messages: list[str],
        response_headers: dict[str, str] | None = None,
    ) -> None:
        self._messages = list(
            messages,
        )
        self.response_headers = dict(
            response_headers or {},
        )
        self.sent_messages: list[dict[str, object]] = []
        self.closed = False

    async def send(
        self,
        message: str,
    ) -> None:
        self.sent_messages.append(
            json.loads(
                message,
            ),
        )

    async def recv(
        self,
    ) -> str:
        if not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(
            0,
        )


class _FakeCodexWebSocketConnector:
    def __init__(
        self,
        connection: _FakeCodexWebSocket,
    ) -> None:
        self.connection = connection
        self.calls: list[dict[str, object]] = []

    async def __call__(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_s: float | None,
    ) -> _FakeCodexWebSocket:
        self.calls.append(
            {
                "url": url,
                "headers": dict(
                    headers,
                ),
                "timeout_s": timeout_s,
            },
        )
        return self.connection


def test_estimate_token_cost_usd_uses_configured_pricing() -> None:
    estimated_cost = _estimate_token_cost_usd(
        settings={
            "input_cost_per_1m_tokens": 3.0,
            "output_cost_per_1m_tokens": 15.0,
        },
        input_tokens=1_000,
        output_tokens=500,
    )

    assert estimated_cost == pytest.approx(0.0105)


def test_estimate_token_cost_usd_includes_anthropic_cache_costs() -> None:
    estimated_cost = _estimate_token_cost_usd(
        settings={
            "input_cost_per_1m_tokens": 3.0,
            "output_cost_per_1m_tokens": 15.0,
        },
        input_tokens=1_000,
        output_tokens=500,
        cache_creation_input_tokens=2_000,
        cache_read_input_tokens=3_000,
        anthropic_cache_pricing=True,
    )

    assert estimated_cost == pytest.approx(0.0189)


def test_estimate_token_cost_usd_uses_default_openai_model_pricing() -> None:
    estimated_cost = _estimate_token_cost_usd(
        settings={},
        model_id="gpt-5.4",
        provider_name="openai",
        input_tokens=10_000,
        output_tokens=100,
        cache_read_input_tokens=4_000,
    )

    assert estimated_cost == pytest.approx(0.0175)


def test_estimate_token_cost_usd_uses_long_context_openai_pricing() -> None:
    estimated_cost = _estimate_token_cost_usd(
        settings={},
        model_id="gpt-5.4",
        provider_name="openai",
        input_tokens=272_001,
        output_tokens=100,
    )

    assert estimated_cost == pytest.approx(1.362255)


def test_estimate_token_cost_usd_does_not_mix_explicit_base_with_default_cache_pricing() -> (
    None
):
    estimated_cost = _estimate_token_cost_usd(
        settings={
            "input_cost_per_1m_tokens": 3.0,
            "output_cost_per_1m_tokens": 15.0,
        },
        model_id="gpt-5.4",
        provider_name="openai",
        input_tokens=10_000,
        output_tokens=100,
        cache_read_input_tokens=4_000,
    )

    assert estimated_cost == pytest.approx(0.0315)


def test_estimate_token_cost_usd_does_not_mix_explicit_base_with_default_long_context_pricing() -> (
    None
):
    estimated_cost = _estimate_token_cost_usd(
        settings={
            "input_cost_per_1m_tokens": 3.0,
            "output_cost_per_1m_tokens": 15.0,
        },
        model_id="gpt-5.4",
        provider_name="openai",
        input_tokens=272_001,
        output_tokens=100,
    )

    assert estimated_cost == pytest.approx(0.817503)


def test_estimate_token_cost_usd_does_not_price_legacy_openai_models() -> None:
    with pytest.raises(
        ProviderConfigurationError,
        match="Missing pricing for provider 'codex' model 'gpt-5.2'",
    ):
        _estimate_token_cost_usd(
            settings={},
            model_id="gpt-5.2",
            provider_name="codex",
            input_tokens=1_000,
            output_tokens=100,
        )


def test_estimate_token_cost_usd_honors_zero_cache_pricing_override() -> None:
    estimated_cost = _estimate_token_cost_usd(
        settings={
            "input_cost_per_1m_tokens": 3.0,
            "output_cost_per_1m_tokens": 15.0,
            "cache_read_input_cost_per_1m_tokens": 0.0,
            "cache_creation_input_cost_per_1m_tokens": 0.0,
        },
        input_tokens=2_000,
        output_tokens=0,
        cache_creation_input_tokens=1_000,
        cache_read_input_tokens=1_000,
    )

    assert estimated_cost == 0.0


def test_estimate_token_cost_usd_uses_default_anthropic_model_pricing() -> None:
    estimated_cost = _estimate_token_cost_usd(
        settings={},
        model_id="claude-sonnet-4-6",
        provider_name="anthropic",
        input_tokens=1_000,
        output_tokens=500,
        cache_creation_input_tokens=2_000,
        cache_read_input_tokens=3_000,
        input_tokens_include_cache_tokens=False,
    )

    assert estimated_cost == pytest.approx(0.0189)


def test_estimate_token_cost_usd_uses_anthropic_one_hour_cache_write_pricing() -> None:
    estimated_cost = _estimate_token_cost_usd(
        settings={
            "anthropic_cache_ttl": "1h",
        },
        model_id="claude-sonnet-4-6",
        provider_name="anthropic",
        input_tokens=1_000,
        output_tokens=500,
        cache_creation_input_tokens=2_000,
        cache_read_input_tokens=3_000,
        input_tokens_include_cache_tokens=False,
        anthropic_cache_pricing=True,
    )

    assert estimated_cost == pytest.approx(0.0234)


def test_format_messages_for_anthropic_does_not_embed_cache_markers() -> None:
    system_prompt, messages = _format_messages_for_anthropic(
        [
            ProviderMessage(
                role=ProviderMessageRole.SYSTEM,
                content="system prompt",
            ),
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="user turn",
            ),
        ],
    )

    assert system_prompt == "system prompt"
    assert "cache_control" not in messages[-1]["content"][-1]


def test_format_messages_for_anthropic_applies_cache_marker_to_last_user_block() -> (
    None
):
    cache_control = {
        "type": "ephemeral",
        "ttl": "5m",
    }
    system_prompt, messages = _format_messages_for_anthropic(
        [
            ProviderMessage(
                role=ProviderMessageRole.SYSTEM,
                content="system prompt",
            ),
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="first user turn",
            ),
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="second user turn",
            ),
        ],
        cache_control=cache_control,
    )

    assert system_prompt == "system prompt"
    assert "cache_control" not in messages[0]["content"][-1]
    assert messages[-1]["content"][-1]["cache_control"] == cache_control


def test_format_messages_for_anthropic_applies_cache_marker_to_tool_result_block() -> (
    None
):
    cache_control = {
        "type": "ephemeral",
        "ttl": "5m",
    }
    _, messages = _format_messages_for_anthropic(
        [
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="Navigate from Apple to Berry.",
            ),
            ProviderMessage(
                role=ProviderMessageRole.ASSISTANT,
                tool_calls=[
                    ProviderToolCall(
                        id="bootstrap_navigate_start",
                        name="navigate",
                        arguments={
                            "to_page_title": "Apple",
                        },
                    ),
                ],
            ),
            ProviderMessage(
                role=ProviderMessageRole.TOOL,
                tool_call_id="bootstrap_navigate_start",
                content="You are currently on Apple. Links: Fruit, Banana, Carpel",
                is_error=False,
            ),
        ],
        cache_control=cache_control,
    )

    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"][-1]["type"] == "tool_result"
    assert messages[-1]["content"][-1]["cache_control"] == cache_control


def test_anthropic_prompt_caching_defaults_to_disabled() -> None:
    assert _anthropic_prompt_caching_enabled({}) is False
    assert _anthropic_prompt_caching_enabled({"anthropic_prompt_caching": True}) is True
    assert (
        _anthropic_prompt_caching_enabled({"anthropic_prompt_caching": False}) is False
    )


def test_build_anthropic_cache_control_requires_explicit_enable() -> None:
    assert _build_anthropic_cache_control({}) is None
    assert _build_anthropic_cache_control({"anthropic_prompt_caching": False}) is None
    assert _build_anthropic_cache_control(
        {
            "anthropic_prompt_caching": True,
        }
    ) == {
        "type": "ephemeral",
        "ttl": "5m",
    }


def test_build_anthropic_cache_control_allows_explicit_1h() -> None:
    assert _build_anthropic_cache_control(
        {
            "anthropic_prompt_caching": True,
            "anthropic_cache_ttl": "1h",
        }
    ) == {
        "type": "ephemeral",
        "ttl": "1h",
    }


def test_build_anthropic_cache_control_rejects_unsupported_ttls() -> None:
    with pytest.raises(
        ProviderConfigurationError,
        match="WikiArena only supports Anthropic prompt caching with ttl='5m' or ttl='1h'",
    ):
        _build_anthropic_cache_control(
            {
                "anthropic_prompt_caching": True,
                "anthropic_cache_ttl": "30m",
            }
        )


def test_format_messages_for_openai_responses_normalizes_synthetic_tool_call_ids() -> (
    None
):
    formatted_messages = _format_messages_for_openai_responses(
        [
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="hello",
            ),
            ProviderMessage(
                role=ProviderMessageRole.ASSISTANT,
                tool_calls=[
                    ProviderToolCall(
                        id="bootstrap_navigate_start",
                        name="navigate",
                        arguments={
                            "to_page_title": "Start",
                        },
                    ),
                ],
            ),
            ProviderMessage(
                role=ProviderMessageRole.TOOL,
                tool_call_id="bootstrap_navigate_start",
                content="ok",
            ),
        ],
    )

    assert formatted_messages == [
        {
            "type": "message",
            "role": "user",
            "content": "hello",
        },
        {
            "type": "function_call",
            "id": "fc_bootstrap_navigate_start",
            "call_id": "call_bootstrap_navigate_start",
            "name": "navigate",
            "arguments": '{"to_page_title": "Start"}',
            "status": "completed",
        },
        {
            "type": "function_call_output",
            "call_id": "call_bootstrap_navigate_start",
            "output": "ok",
            "status": "completed",
        },
    ]


def test_format_messages_for_openai_responses_omits_reasoning_status() -> None:
    formatted_messages = _format_messages_for_openai_responses(
        [
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="hello",
            ),
            ProviderMessage(
                role=ProviderMessageRole.ASSISTANT,
                reasoning_items=[
                    ProviderReasoningItem(
                        id="rs_1",
                        summary="Reasoning summary",
                        encrypted_content="encrypted-blob",
                        status="completed",
                    ),
                ],
            ),
        ],
    )

    assert formatted_messages == [
        {
            "type": "message",
            "role": "user",
            "content": "hello",
        },
        {
            "type": "reasoning",
            "id": "rs_1",
            "summary": [
                {
                    "type": "summary_text",
                    "text": "Reasoning summary",
                },
            ],
            "encrypted_content": "encrypted-blob",
        },
    ]


@pytest.mark.asyncio
async def test_codex_provider_generates_response_from_sse_items(
    tmp_path,
) -> None:
    auth_file = tmp_path / "codex-auth.json"
    auth_file.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": _create_test_jwt(
                        {
                            "exp": 4_102_444_800,
                            "https://api.openai.com/auth": {
                                "chatgpt_account_id": "account-123",
                            },
                        },
                    ),
                    "refresh_token": "refresh-token",
                    "account_id": "account-123",
                },
            },
        ),
    )
    http_client = _FakeCodexHttpClient(
        stream_responses=[
            _FakeStreamResponse(
                status_code=200,
                lines=[
                    'data: {"type":"response.output_item.done","item":{"id":"rs_1","type":"reasoning","summary":[{"text":"Reasoning summary"}]}}',
                    'data: {"type":"response.output_item.done","item":{"id":"msg_1","type":"message","status":"completed","role":"assistant","content":[{"type":"output_text","text":"hello"}]}}',
                    'data: {"type":"response.completed","response":{"id":"resp_1","usage":{"input_tokens":10,"input_tokens_details":{"cached_tokens":2},"output_tokens":5,"output_tokens_details":{"reasoning_tokens":3},"total_tokens":15}}}',
                    "data: [DONE]",
                ],
            ),
        ],
    )
    provider = CodexChatProvider(
        auth_file=auth_file,
        prompt_cache_key="test-cache-key",
        http_client=http_client,
    )

    response = await provider.generate(
        ProviderRequest(
            model_id="gpt-5.4",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.SYSTEM,
                    content="System instructions",
                ),
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="hello",
                ),
            ],
            tools=[],
            settings={
                "reasoning_effort": "high",
                "max_tokens": 128,
                "prompt_cache_retention": "24h",
                "temperature": 0,
                "top_p": 1,
            },
        ),
    )

    assert response.provider_response_id == "resp_1"
    assert response.message.content == "hello"
    assert response.message.thinking == "Reasoning summary"
    assert response.message.reasoning_items == [
        ProviderReasoningItem(
            id="rs_1",
            summary="Reasoning summary",
            encrypted_content=None,
            status=None,
        ),
    ]
    assert response.usage.input_token_details == {
        "cached_tokens": 2,
    }
    assert response.usage.cache_read_input_tokens == 2
    assert response.usage.cache_creation_input_tokens == 0
    assert response.usage.output_token_details == {
        "reasoning_tokens": 3,
    }
    assert response.usage.estimated_cost_usd == pytest.approx(0.0000955)
    stream_call = http_client.stream_calls[0]
    assert stream_call["url"] == "https://chatgpt.com/backend-api/codex/responses"
    assert stream_call["headers"]["ChatGPT-Account-Id"] == "account-123"
    assert stream_call["json"] == {
        "model": "gpt-5.4",
        "instructions": "System instructions",
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": "hello",
            },
        ],
        "store": False,
        "stream": True,
        "prompt_cache_key": "test-cache-key",
        "reasoning": {
            "effort": "high",
        },
    }


@pytest.mark.asyncio
async def test_codex_provider_replays_full_history_without_previous_response_id(
    tmp_path,
) -> None:
    auth_file = tmp_path / "codex-auth.json"
    auth_file.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": _create_test_jwt(
                        {
                            "exp": 4_102_444_800,
                            "https://api.openai.com/auth": {
                                "chatgpt_account_id": "account-123",
                            },
                        },
                    ),
                    "refresh_token": "refresh-token",
                    "account_id": "account-123",
                },
            },
        ),
    )
    http_client = _FakeCodexHttpClient(
        stream_responses=[
            _FakeStreamResponse(
                status_code=200,
                lines=[
                    'data: {"type":"response.output_item.done","item":{"id":"msg_1","type":"message","status":"completed","role":"assistant","content":[{"type":"output_text","text":"Done."}]}}',
                    'data: {"type":"response.completed","response":{"id":"resp_2","usage":{"input_tokens":30,"input_tokens_details":{"cached_tokens":0},"output_tokens":4,"output_tokens_details":{"reasoning_tokens":0},"total_tokens":34}}}',
                    "data: [DONE]",
                ],
            ),
        ],
    )
    provider = CodexChatProvider(
        auth_file=auth_file,
        http_client=http_client,
    )

    await provider.generate(
        ProviderRequest(
            model_id="gpt-5.4",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.SYSTEM,
                    content="System instructions",
                ),
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="Navigate to Banana.",
                ),
                ProviderMessage(
                    role=ProviderMessageRole.ASSISTANT,
                    tool_calls=[
                        ProviderToolCall(
                            id="call_1",
                            name="navigate",
                            arguments={
                                "to_page_title": "Banana",
                            },
                        ),
                    ],
                ),
                ProviderMessage(
                    role=ProviderMessageRole.TOOL,
                    tool_call_id="call_1",
                    content="You are currently on Banana.",
                ),
            ],
            settings={
                "reasoning_effort": "low",
                "openai_use_previous_response_id": True,
            },
        ),
    )

    payload = http_client.stream_calls[0]["json"]
    assert "previous_response_id" not in payload
    assert payload["input"] == [
        {
            "type": "message",
            "role": "user",
            "content": "Navigate to Banana.",
        },
        {
            "type": "function_call",
            "id": "fc_1",
            "call_id": "call_1",
            "name": "navigate",
            "arguments": '{"to_page_title": "Banana"}',
            "status": "completed",
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "You are currently on Banana.",
            "status": "completed",
        },
    ]


@pytest.mark.asyncio
async def test_codex_provider_uses_stable_session_headers_and_turn_state(
    tmp_path,
) -> None:
    auth_file = tmp_path / "codex-auth.json"
    auth_file.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": _create_test_jwt(
                        {
                            "exp": 4_102_444_800,
                            "https://api.openai.com/auth": {
                                "chatgpt_account_id": "account-123",
                            },
                        },
                    ),
                    "refresh_token": "refresh-token",
                    "account_id": "account-123",
                },
            },
        ),
    )
    http_client = _FakeCodexHttpClient(
        stream_responses=[
            _FakeStreamResponse(
                status_code=200,
                headers={
                    "x-codex-turn-state": "turn-state-1",
                },
                lines=[
                    'data: {"type":"response.output_item.done","item":{"id":"msg_1","type":"message","status":"completed","role":"assistant","content":[{"type":"output_text","text":"OK"}]}}',
                    'data: {"type":"response.completed","response":{"id":"resp_1","usage":{"input_tokens":8,"input_tokens_details":{"cached_tokens":0},"output_tokens":2,"output_tokens_details":{"reasoning_tokens":0},"total_tokens":10}}}',
                    "data: [DONE]",
                ],
            ),
            _FakeStreamResponse(
                status_code=200,
                lines=[
                    'data: {"type":"response.output_item.done","item":{"id":"msg_2","type":"message","status":"completed","role":"assistant","content":[{"type":"output_text","text":"OK again"}]}}',
                    'data: {"type":"response.completed","response":{"id":"resp_2","usage":{"input_tokens":12,"input_tokens_details":{"cached_tokens":8},"output_tokens":2,"output_tokens_details":{"reasoning_tokens":0},"total_tokens":14}}}',
                    "data: [DONE]",
                ],
            ),
        ],
    )
    provider = CodexChatProvider(
        auth_file=auth_file,
        prompt_cache_key="test-cache-key",
        http_client=http_client,
    )
    request = ProviderRequest(
        model_id="gpt-5.4",
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.SYSTEM,
                content="System instructions",
            ),
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="hello",
            ),
        ],
    )

    await provider.generate(
        request,
    )
    await provider.generate(
        request,
    )

    first_headers = http_client.stream_calls[0]["headers"]
    second_headers = http_client.stream_calls[1]["headers"]
    expected_session_id = "test-cache-key"
    expected_window_id = f"{expected_session_id}:0"
    assert first_headers["session_id"] == expected_session_id
    assert second_headers["session_id"] == expected_session_id
    assert first_headers["x-client-request-id"] == expected_session_id
    assert second_headers["x-client-request-id"] == expected_session_id
    assert first_headers["x-codex-window-id"] == expected_window_id
    assert second_headers["x-codex-window-id"] == expected_window_id
    assert "x-codex-turn-state" not in first_headers
    assert second_headers["x-codex-turn-state"] == "turn-state-1"


@pytest.mark.asyncio
async def test_codex_provider_websocket_uses_incremental_previous_response_id(
    tmp_path,
) -> None:
    auth_file = tmp_path / "codex-auth.json"
    auth_file.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": _create_test_jwt(
                        {
                            "exp": 4_102_444_800,
                            "https://api.openai.com/auth": {
                                "chatgpt_account_id": "account-123",
                            },
                        },
                    ),
                    "refresh_token": "refresh-token",
                    "account_id": "account-123",
                },
            },
        ),
    )
    websocket = _FakeCodexWebSocket(
        response_headers={
            "x-codex-turn-state": "turn-state-1",
        },
        messages=[
            json.dumps(
                {
                    "type": "response.output_item.done",
                    "item": {
                        "id": "fc_1",
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "navigate",
                        "arguments": '{"to_page_title":"15.ai"}',
                        "status": "completed",
                    },
                },
            ),
            json.dumps(
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_1",
                        "usage": {
                            "input_tokens": 8,
                            "input_tokens_details": {
                                "cached_tokens": 0,
                            },
                            "output_tokens": 2,
                            "output_tokens_details": {
                                "reasoning_tokens": 0,
                            },
                            "total_tokens": 10,
                        },
                    },
                },
            ),
            json.dumps(
                {
                    "type": "response.output_item.done",
                    "item": {
                        "id": "fc_2",
                        "type": "function_call",
                        "call_id": "call_2",
                        "name": "navigate",
                        "arguments": '{"to_page_title":"Claude Shannon"}',
                        "status": "completed",
                    },
                },
            ),
            json.dumps(
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_2",
                        "usage": {
                            "input_tokens": 12,
                            "input_tokens_details": {
                                "cached_tokens": 8,
                            },
                            "output_tokens": 2,
                            "output_tokens_details": {
                                "reasoning_tokens": 0,
                            },
                            "total_tokens": 14,
                        },
                    },
                },
            ),
        ],
    )
    websocket_connector = _FakeCodexWebSocketConnector(
        websocket,
    )
    provider = CodexChatProvider(
        auth_file=auth_file,
        prompt_cache_key="test-cache-key",
        codex_transport="websocket",
        websocket_connect=websocket_connector,
    )
    first_request = ProviderRequest(
        model_id="gpt-5.4",
        messages=[
            ProviderMessage(
                role=ProviderMessageRole.SYSTEM,
                content="System instructions",
            ),
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content="hello",
            ),
        ],
    )

    first_response = await provider.generate(
        first_request,
    )
    second_response = await provider.generate(
        ProviderRequest(
            model_id="gpt-5.4",
            messages=[
                *first_request.messages,
                first_response.message,
                ProviderMessage(
                    role=ProviderMessageRole.TOOL,
                    tool_call_id="call_1",
                    content="You are currently on 15.ai.",
                ),
            ],
        ),
    )

    assert (
        len(
            websocket_connector.calls,
        )
        == 1
    )
    headers = websocket_connector.calls[0]["headers"]
    assert headers["session_id"] == "test-cache-key"
    assert headers["x-client-request-id"] == "test-cache-key"
    assert headers["x-codex-window-id"] == "test-cache-key:0"
    assert headers["OpenAI-Beta"] == "responses_websockets=2026-02-06"
    assert websocket.sent_messages[0]["type"] == "response.create"
    assert (
        websocket.sent_messages[0].get(
            "previous_response_id",
        )
        is None
    )
    assert websocket.sent_messages[1]["type"] == "response.create"
    assert websocket.sent_messages[1]["previous_response_id"] == "resp_1"
    assert websocket.sent_messages[1]["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "You are currently on 15.ai.",
            "status": "completed",
        },
    ]
    assert second_response.usage.cache_read_input_tokens == 8


@pytest.mark.asyncio
async def test_codex_provider_websocket_can_prewarm_with_generate_false(
    tmp_path,
) -> None:
    auth_file = tmp_path / "codex-auth.json"
    auth_file.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": _create_test_jwt(
                        {
                            "exp": 4_102_444_800,
                        },
                    ),
                    "refresh_token": "refresh-token",
                },
            },
        ),
    )
    websocket = _FakeCodexWebSocket(
        messages=[
            json.dumps(
                {
                    "type": "response.completed",
                    "response": {
                        "id": "warm_1",
                        "usage": {
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "total_tokens": 0,
                        },
                    },
                },
            ),
            json.dumps(
                {
                    "type": "response.output_item.done",
                    "item": {
                        "id": "fc_1",
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "navigate",
                        "arguments": '{"to_page_title":"15.ai"}',
                        "status": "completed",
                    },
                },
            ),
            json.dumps(
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_1",
                        "usage": {
                            "input_tokens": 8,
                            "input_tokens_details": {
                                "cached_tokens": 8,
                            },
                            "output_tokens": 2,
                            "output_tokens_details": {
                                "reasoning_tokens": 0,
                            },
                            "total_tokens": 10,
                        },
                    },
                },
            ),
        ],
    )
    provider = CodexChatProvider(
        auth_file=auth_file,
        prompt_cache_key="test-cache-key",
        codex_transport="websocket",
        websocket_connect=_FakeCodexWebSocketConnector(
            websocket,
        ),
        websocket_prewarm=True,
    )

    response = await provider.generate(
        ProviderRequest(
            model_id="gpt-5.4",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.SYSTEM,
                    content="System instructions",
                ),
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="hello",
                ),
            ],
        ),
    )

    assert websocket.sent_messages[0]["generate"] is False
    assert (
        websocket.sent_messages[0].get(
            "previous_response_id",
        )
        is None
    )
    assert websocket.sent_messages[1]["previous_response_id"] == "warm_1"
    assert websocket.sent_messages[1]["input"] == []
    assert response.usage.cache_read_input_tokens == 8


@pytest.mark.asyncio
async def test_codex_provider_websocket_upgrade_falls_back_to_http(
    tmp_path,
) -> None:
    auth_file = tmp_path / "codex-auth.json"
    auth_file.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": _create_test_jwt(
                        {
                            "exp": 4_102_444_800,
                        },
                    ),
                    "refresh_token": "refresh-token",
                },
            },
        ),
    )

    async def failing_websocket_connect(
        url: str,
        *,
        headers: dict[str, str],
        timeout_s: float | None,
    ) -> object:
        raise _CodexWebSocketFallbackToHttp(
            "upgrade unavailable",
        )

    http_client = _FakeCodexHttpClient(
        stream_responses=[
            _FakeStreamResponse(
                status_code=200,
                lines=[
                    'data: {"type":"response.output_item.done","item":{"id":"msg_1","type":"message","status":"completed","role":"assistant","content":[{"type":"output_text","text":"OK"}]}}',
                    'data: {"type":"response.completed","response":{"id":"resp_1","usage":{"input_tokens":8,"input_tokens_details":{"cached_tokens":0},"output_tokens":2,"output_tokens_details":{"reasoning_tokens":0},"total_tokens":10}}}',
                    "data: [DONE]",
                ],
            ),
        ],
    )
    provider = CodexChatProvider(
        auth_file=auth_file,
        prompt_cache_key="test-cache-key",
        http_client=http_client,
        codex_transport="websocket",
        websocket_connect=failing_websocket_connect,
    )

    await provider.generate(
        ProviderRequest(
            model_id="gpt-5.4",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.SYSTEM,
                    content="System instructions",
                ),
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="hello",
                ),
            ],
        ),
    )

    assert (
        len(
            http_client.stream_calls,
        )
        == 1
    )
    assert http_client.stream_calls[0]["headers"]["session_id"] == "test-cache-key"


@pytest.mark.asyncio
async def test_codex_provider_websocket_only_disables_http_fallback(
    tmp_path,
) -> None:
    auth_file = tmp_path / "codex-auth.json"
    auth_file.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": _create_test_jwt(
                        {
                            "exp": 4_102_444_800,
                        },
                    ),
                    "refresh_token": "refresh-token",
                },
            },
        ),
    )

    async def failing_websocket_connect(
        url: str,
        *,
        headers: dict[str, str],
        timeout_s: float | None,
    ) -> object:
        raise _CodexWebSocketFallbackToHttp(
            "upgrade unavailable",
        )

    http_client = _FakeCodexHttpClient()
    provider = CodexChatProvider(
        auth_file=auth_file,
        prompt_cache_key="test-cache-key",
        http_client=http_client,
        codex_transport="websocket_only",
        websocket_connect=failing_websocket_connect,
    )

    with pytest.raises(
        ProviderError,
        match="HTTP fallback is disabled",
    ):
        await provider.generate(
            ProviderRequest(
                model_id="gpt-5.4",
                messages=[
                    ProviderMessage(
                        role=ProviderMessageRole.USER,
                        content="hello",
                    ),
                ],
            ),
        )

    assert http_client.stream_calls == []


@pytest.mark.asyncio
async def test_codex_provider_supports_current_reasoning_summary_options(
    tmp_path,
) -> None:
    auth_file = tmp_path / "codex-auth.json"
    auth_file.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": _create_test_jwt(
                        {
                            "exp": 4_102_444_800,
                            "https://api.openai.com/auth": {
                                "chatgpt_account_id": "account-123",
                            },
                        },
                    ),
                    "refresh_token": "refresh-token",
                    "account_id": "account-123",
                },
            },
        ),
    )
    http_client = _FakeCodexHttpClient(
        stream_responses=[
            _FakeStreamResponse(
                status_code=200,
                lines=[
                    'data: {"type":"response.output_item.done","item":{"id":"msg_1","type":"message","status":"completed","role":"assistant","content":[{"type":"output_text","text":"OK"}]}}',
                    'data: {"type":"response.completed","response":{"id":"resp_3","usage":{"input_tokens":8,"input_tokens_details":{"cached_tokens":0},"output_tokens":2,"output_tokens_details":{"reasoning_tokens":0},"total_tokens":10}}}',
                    "data: [DONE]",
                ],
            ),
        ],
    )
    provider = CodexChatProvider(
        auth_file=auth_file,
        prompt_cache_key="test-cache-key",
        http_client=http_client,
    )

    await provider.generate(
        ProviderRequest(
            model_id="gpt-5.4",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="hello",
                ),
            ],
            settings={
                "reasoning_effort": "low",
                "openai_reasoning_summary": "auto",
                "openai_include_encrypted_reasoning": True,
                "include": ["reasoning.encrypted_content"],
            },
        ),
    )

    payload = http_client.stream_calls[0]["json"]
    assert payload["reasoning"] == {
        "effort": "low",
        "summary": "auto",
    }
    assert payload["include"] == [
        "reasoning.encrypted_content",
    ]


@pytest.mark.asyncio
async def test_codex_provider_rejects_unknown_settings_before_request(
    tmp_path,
) -> None:
    auth_file = tmp_path / "codex-auth.json"
    auth_file.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": _create_test_jwt(
                        {
                            "exp": 4_102_444_800,
                            "https://api.openai.com/auth": {
                                "chatgpt_account_id": "account-123",
                            },
                        },
                    ),
                    "refresh_token": "refresh-token",
                    "account_id": "account-123",
                },
            },
        ),
    )
    http_client = _FakeCodexHttpClient()
    provider = CodexChatProvider(
        auth_file=auth_file,
        http_client=http_client,
    )

    with pytest.raises(
        ProviderConfigurationError,
        match="Codex provider does not support settings: response_format",
    ):
        await provider.generate(
            ProviderRequest(
                model_id="gpt-5.4",
                messages=[
                    ProviderMessage(
                        role=ProviderMessageRole.USER,
                        content="hello",
                    ),
                ],
                settings={
                    "response_format": {
                        "type": "json_object",
                    },
                },
            ),
        )

    assert http_client.post_calls == []
    assert http_client.stream_calls == []


@pytest.mark.asyncio
async def test_codex_provider_rejects_priority_service_tier_before_request(
    tmp_path,
) -> None:
    auth_file = tmp_path / "codex-auth.json"
    auth_file.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": _create_test_jwt(
                        {
                            "exp": 1,
                            "https://api.openai.com/auth": {
                                "chatgpt_account_id": "account-123",
                            },
                        },
                    ),
                    "refresh_token": "refresh-token",
                    "account_id": "account-123",
                },
            },
        ),
    )
    http_client = _FakeCodexHttpClient()
    provider = CodexChatProvider(
        auth_file=auth_file,
        http_client=http_client,
    )

    with pytest.raises(
        ProviderConfigurationError,
        match="Codex provider priority service_tier is disabled",
    ):
        await provider.generate(
            ProviderRequest(
                model_id="gpt-5.4",
                messages=[
                    ProviderMessage(
                        role=ProviderMessageRole.USER,
                        content="hello",
                    ),
                ],
                settings={
                    "service_tier": "priority",
                },
            ),
        )

    assert http_client.post_calls == []
    assert http_client.stream_calls == []


@pytest.mark.asyncio
async def test_codex_provider_rejects_missing_pricing_before_request(
    tmp_path,
) -> None:
    http_client = _FakeCodexHttpClient()
    provider = CodexChatProvider(
        auth_file=tmp_path / "missing-codex-auth.json",
        http_client=http_client,
    )

    with pytest.raises(
        ProviderConfigurationError,
        match="Missing pricing for provider 'codex' model 'gpt-5.2'",
    ):
        await provider.generate(
            ProviderRequest(
                model_id="gpt-5.2",
                messages=[
                    ProviderMessage(
                        role=ProviderMessageRole.USER,
                        content="hello",
                    ),
                ],
            ),
        )

    assert http_client.post_calls == []
    assert http_client.stream_calls == []


@pytest.mark.asyncio
async def test_codex_provider_sends_empty_instructions_without_system_message(
    tmp_path,
) -> None:
    auth_file = tmp_path / "codex-auth.json"
    auth_file.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": _create_test_jwt(
                        {
                            "exp": 4_102_444_800,
                            "https://api.openai.com/auth": {
                                "chatgpt_account_id": "account-123",
                            },
                        },
                    ),
                    "refresh_token": "refresh-token",
                    "account_id": "account-123",
                },
            },
        ),
    )
    http_client = _FakeCodexHttpClient(
        stream_responses=[
            _FakeStreamResponse(
                status_code=200,
                lines=[
                    'data: {"type":"response.output_item.done","item":{"id":"msg_1","type":"message","status":"completed","role":"assistant","content":[{"type":"output_text","text":"OK"}]}}',
                    'data: {"type":"response.completed","response":{"id":"resp_2","usage":{"input_tokens":8,"input_tokens_details":{"cached_tokens":0},"output_tokens":2,"output_tokens_details":{"reasoning_tokens":0},"total_tokens":10}}}',
                    "data: [DONE]",
                ],
            ),
        ],
    )
    provider = CodexChatProvider(
        auth_file=auth_file,
        http_client=http_client,
    )

    await provider.generate(
        ProviderRequest(
            model_id="gpt-5.4",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="hello",
                ),
            ],
        ),
    )

    assert http_client.stream_calls[0]["json"]["instructions"] == ""


@pytest.mark.asyncio
async def test_codex_provider_refreshes_expired_access_token_before_request(
    tmp_path,
) -> None:
    expired_access_token = _create_test_jwt(
        {
            "exp": 1,
            "https://api.openai.com/auth": {
                "chatgpt_account_id": "account-old",
            },
        },
    )
    refreshed_access_token = _create_test_jwt(
        {
            "exp": 4_102_444_800,
            "https://api.openai.com/auth": {
                "chatgpt_account_id": "account-new",
            },
        },
    )
    auth_file = tmp_path / "codex-auth.json"
    auth_file.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": expired_access_token,
                    "refresh_token": "refresh-token-old",
                    "account_id": "account-old",
                },
            },
        ),
    )
    http_client = _FakeCodexHttpClient(
        post_responses=[
            _FakeResponse(
                status_code=200,
                json_body={
                    "access_token": refreshed_access_token,
                    "refresh_token": "refresh-token-new",
                    "id_token": _create_test_jwt(
                        {
                            "https://api.openai.com/auth": {
                                "chatgpt_account_id": "account-new",
                            },
                        },
                    ),
                    "expires_in": 3600,
                },
            ),
        ],
        stream_responses=[
            _FakeStreamResponse(
                status_code=200,
                lines=[
                    'data: {"type":"response.output_item.done","item":{"id":"msg_1","type":"message","status":"completed","role":"assistant","content":[{"type":"output_text","text":"OK"}]}}',
                    'data: {"type":"response.completed","response":{"id":"resp_3","usage":{"input_tokens":8,"input_tokens_details":{"cached_tokens":0},"output_tokens":2,"output_tokens_details":{"reasoning_tokens":0},"total_tokens":10}}}',
                    "data: [DONE]",
                ],
            ),
        ],
    )
    provider = CodexChatProvider(
        auth_file=auth_file,
        http_client=http_client,
    )

    await provider.generate(
        ProviderRequest(
            model_id="gpt-5.4",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.SYSTEM,
                    content="System instructions",
                ),
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="hello",
                ),
            ],
        ),
    )

    assert http_client.post_calls == [
        {
            "url": _CODEX_OAUTH_TOKEN_URL,
            "headers": {
                "Content-Type": "application/x-www-form-urlencoded",
            },
            "data": {
                "grant_type": "refresh_token",
                "refresh_token": "refresh-token-old",
                "client_id": _CODEX_OAUTH_CLIENT_ID,
            },
        },
    ]
    assert http_client.stream_calls[0]["headers"]["Authorization"] == (
        f"Bearer {refreshed_access_token}"
    )
    assert http_client.stream_calls[0]["headers"]["ChatGPT-Account-Id"] == (
        "account-new"
    )
    refreshed_auth = json.loads(
        auth_file.read_text(),
    )
    assert refreshed_auth["tokens"]["access_token"] == refreshed_access_token
    assert refreshed_auth["tokens"]["refresh_token"] == "refresh-token-new"
    assert refreshed_auth["tokens"]["account_id"] == "account-new"
    assert refreshed_auth["last_refresh"]


@pytest.mark.asyncio
async def test_openai_provider_error_preserves_sdk_message() -> None:
    provider = OpenAIChatProvider(
        api_key="test-key",
    )
    provider.client.chat.completions.create = AsyncMock(
        side_effect=OpenAIError(
            "401 invalid api key",
        ),
    )

    with pytest.raises(
        ProviderError,
        match="OpenAI provider request failed: 401 invalid api key",
    ):
        await provider.generate(
            ProviderRequest(
                model_id="gpt-5.4",
                messages=[
                    ProviderMessage(
                        role=ProviderMessageRole.USER,
                        content="hello",
                    ),
                ],
            ),
        )


@pytest.mark.asyncio
async def test_openai_provider_chat_completions_strips_internal_settings() -> None:
    provider = OpenAIChatProvider(
        api_key="test-key",
    )
    provider.client.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(
            id="chatcmpl-test",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="hello",
                        tool_calls=[],
                        reasoning=None,
                    ),
                ),
            ],
            usage=SimpleNamespace(
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
            ),
        ),
    )

    await provider.generate(
        ProviderRequest(
            model_id="gpt-5.4",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="hello",
                ),
            ],
            settings={
                "openai_api_mode": "chat_completions",
                "openai_use_previous_response_id": True,
                "output_config": {
                    "effort": "high",
                },
                "thinking": {
                    "type": "adaptive",
                },
            },
        ),
    )

    create_kwargs = provider.client.chat.completions.create.await_args.kwargs
    assert "openai_api_mode" not in create_kwargs
    assert "openai_use_previous_response_id" not in create_kwargs
    assert "output_config" not in create_kwargs
    assert "thinking" not in create_kwargs


@pytest.mark.asyncio
async def test_openai_provider_rejects_priority_service_tier() -> None:
    provider = OpenAIChatProvider(
        api_key="test-key",
        default_api_mode="responses",
    )
    provider.client.responses.create = AsyncMock()

    with pytest.raises(
        ProviderConfigurationError,
        match="OpenAI provider priority service_tier is disabled",
    ):
        await provider.generate(
            ProviderRequest(
                model_id="gpt-5.4",
                messages=[
                    ProviderMessage(
                        role=ProviderMessageRole.USER,
                        content="hello",
                    ),
                ],
                settings={
                    "service_tier": "priority",
                },
            ),
        )

    provider.client.responses.create.assert_not_called()


@pytest.mark.asyncio
async def test_openai_provider_rejects_missing_pricing_before_request() -> None:
    provider = OpenAIChatProvider(
        api_key="test-key",
    )
    provider.client.chat.completions.create = AsyncMock()

    with pytest.raises(
        ProviderConfigurationError,
        match="Missing pricing for provider 'openai' model 'gpt-5.2'",
    ):
        await provider.generate(
            ProviderRequest(
                model_id="gpt-5.2",
                messages=[
                    ProviderMessage(
                        role=ProviderMessageRole.USER,
                        content="hello",
                    ),
                ],
            ),
        )

    provider.client.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_openai_provider_allows_explicit_pricing_for_unknown_model() -> None:
    provider = OpenAIChatProvider(
        api_key="test-key",
    )
    provider.client.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(
            id="chatcmpl-test",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="hello",
                        tool_calls=[],
                        reasoning=None,
                    ),
                ),
            ],
            usage=SimpleNamespace(
                prompt_tokens=1_000,
                completion_tokens=500,
                total_tokens=1_500,
            ),
        ),
    )

    response = await provider.generate(
        ProviderRequest(
            model_id="gpt-test",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="hello",
                ),
            ],
            settings={
                "input_cost_per_1m_tokens": 3.0,
                "output_cost_per_1m_tokens": 15.0,
            },
        ),
    )

    create_kwargs = provider.client.chat.completions.create.await_args.kwargs
    assert "input_cost_per_1m_tokens" not in create_kwargs
    assert "output_cost_per_1m_tokens" not in create_kwargs
    assert response.usage.estimated_cost_usd == pytest.approx(0.0105)


@pytest.mark.asyncio
async def test_openai_provider_can_be_locked_to_responses_only() -> None:
    provider = OpenAIChatProvider(
        api_key="test-key",
        default_api_mode="responses",
        supported_api_modes={"responses"},
    )

    with pytest.raises(
        ProviderConfigurationError,
        match="Unsupported openai_api_mode 'chat_completions'",
    ):
        await provider.generate(
            ProviderRequest(
                model_id="gpt-5.4",
                messages=[
                    ProviderMessage(
                        role=ProviderMessageRole.USER,
                        content="hello",
                    ),
                ],
                settings={
                    "openai_api_mode": "chat_completions",
                },
            ),
        )


@pytest.mark.asyncio
async def test_openai_provider_records_chat_completion_token_breakdown() -> None:
    provider = OpenAIChatProvider(
        api_key="test-key",
    )
    provider.client.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(
            id="chatcmpl-test",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="hello",
                        tool_calls=[],
                        reasoning=None,
                    ),
                ),
            ],
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
                prompt_tokens_details=SimpleNamespace(
                    cached_tokens=80,
                ),
                completion_tokens_details=SimpleNamespace(
                    reasoning_tokens=15,
                    rejected_prediction_tokens=2,
                ),
            ),
        ),
    )

    response = await provider.generate(
        ProviderRequest(
            model_id="gpt-5.4",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="hello",
                ),
            ],
        ),
    )

    assert response.usage.cache_read_input_tokens == 80
    assert response.usage.input_token_details == {
        "cached_tokens": 80,
    }
    assert response.usage.output_token_details == {
        "reasoning_tokens": 15,
        "rejected_prediction_tokens": 2,
    }


@pytest.mark.asyncio
async def test_openai_provider_responses_api_returns_summary_and_encrypted_reasoning() -> (
    None
):
    provider = OpenAIChatProvider(
        api_key="test-key",
        prompt_cache_key="test-cache-key",
    )
    provider.client.responses.create = AsyncMock(
        return_value=SimpleNamespace(
            id="resp_1",
            output=[
                SimpleNamespace(
                    type="reasoning",
                    id="rs_1",
                    summary=[
                        SimpleNamespace(
                            text="Reasoning summary",
                        ),
                    ],
                    encrypted_content="encrypted-blob",
                    status="completed",
                ),
                SimpleNamespace(
                    type="function_call",
                    id="fc_item_1",
                    call_id="call_1",
                    name="navigate",
                    arguments='{"to_page_title":"Banana"}',
                    status="completed",
                ),
            ],
            usage=SimpleNamespace(
                input_tokens=120,
                output_tokens=60,
                total_tokens=180,
                input_tokens_details=SimpleNamespace(
                    cached_tokens=40,
                ),
                output_tokens_details=SimpleNamespace(
                    reasoning_tokens=33,
                ),
            ),
        ),
    )

    response = await provider.generate(
        ProviderRequest(
            model_id="gpt-5.4",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="hello",
                ),
            ],
            settings={
                "openai_api_mode": "responses",
                "openai_reasoning_summary": "auto",
                "openai_include_encrypted_reasoning": True,
            },
        ),
    )

    assert response.message.thinking == "Reasoning summary"
    assert response.message.reasoning_items == [
        ProviderReasoningItem(
            id="rs_1",
            summary="Reasoning summary",
            encrypted_content="encrypted-blob",
            status="completed",
        ),
    ]
    assert response.message.tool_calls[0].id == "call_1"
    assert response.usage.input_token_details == {
        "cached_tokens": 40,
    }
    assert response.usage.output_token_details == {
        "reasoning_tokens": 33,
    }
    create_kwargs = provider.client.responses.create.await_args.kwargs
    assert create_kwargs["prompt_cache_key"] == "test-cache-key"
    assert create_kwargs["include"] == ["reasoning.encrypted_content"]
    assert create_kwargs["reasoning"] == {
        "summary": "auto",
    }


@pytest.mark.asyncio
async def test_openai_provider_responses_api_uses_previous_response_id_for_follow_up() -> (
    None
):
    provider = OpenAIChatProvider(
        api_key="test-key",
    )
    provider.client.responses.create = AsyncMock(
        side_effect=[
            SimpleNamespace(
                id="resp_1",
                output=[
                    SimpleNamespace(
                        type="function_call",
                        id="fc_item_1",
                        call_id="call_1",
                        name="navigate",
                        arguments='{"to_page_title":"Banana"}',
                        status="completed",
                    ),
                ],
                usage=SimpleNamespace(
                    input_tokens=10,
                    output_tokens=2,
                    total_tokens=12,
                    input_tokens_details=SimpleNamespace(
                        cached_tokens=0,
                    ),
                    output_tokens_details=SimpleNamespace(
                        reasoning_tokens=0,
                    ),
                ),
            ),
            SimpleNamespace(
                id="resp_2",
                output=[],
                usage=SimpleNamespace(
                    input_tokens=5,
                    output_tokens=1,
                    total_tokens=6,
                    input_tokens_details=SimpleNamespace(
                        cached_tokens=0,
                    ),
                    output_tokens_details=SimpleNamespace(
                        reasoning_tokens=0,
                    ),
                ),
            ),
        ],
    )

    first_response = await provider.generate(
        ProviderRequest(
            model_id="gpt-5.4",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="hello",
                ),
            ],
            settings={
                "openai_api_mode": "responses",
                "openai_use_previous_response_id": True,
            },
        ),
    )
    await provider.generate(
        ProviderRequest(
            model_id="gpt-5.4",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="hello",
                ),
                first_response.message,
                ProviderMessage(
                    role=ProviderMessageRole.TOOL,
                    tool_call_id="call_1",
                    content="ok",
                ),
            ],
            settings={
                "openai_api_mode": "responses",
                "openai_use_previous_response_id": True,
            },
        ),
    )

    second_call_kwargs = provider.client.responses.create.await_args_list[1].kwargs
    assert second_call_kwargs["previous_response_id"] == "resp_1"
    assert second_call_kwargs["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "ok",
            "status": "completed",
        },
    ]


@pytest.mark.asyncio
async def test_openai_provider_responses_api_replays_encrypted_reasoning_without_previous_response_id() -> (
    None
):
    provider = OpenAIChatProvider(
        api_key="test-key",
    )
    provider.client.responses.create = AsyncMock(
        return_value=SimpleNamespace(
            id="resp_2",
            output=[],
            usage=SimpleNamespace(
                input_tokens=5,
                output_tokens=1,
                total_tokens=6,
                input_tokens_details=SimpleNamespace(
                    cached_tokens=0,
                ),
                output_tokens_details=SimpleNamespace(
                    reasoning_tokens=0,
                ),
            ),
        ),
    )

    await provider.generate(
        ProviderRequest(
            model_id="gpt-5.4",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="hello",
                ),
                ProviderMessage(
                    role=ProviderMessageRole.ASSISTANT,
                    reasoning_items=[
                        ProviderReasoningItem(
                            id="rs_1",
                            summary="Reasoning summary",
                            encrypted_content="encrypted-blob",
                            status="completed",
                        ),
                    ],
                    tool_calls=[
                        ProviderToolCall(
                            id="call_1",
                            name="navigate",
                            arguments={
                                "to_page_title": "Banana",
                            },
                        ),
                    ],
                ),
                ProviderMessage(
                    role=ProviderMessageRole.TOOL,
                    tool_call_id="call_1",
                    content="ok",
                ),
            ],
            settings={
                "openai_api_mode": "responses",
                "openai_include_encrypted_reasoning": True,
                "openai_use_previous_response_id": False,
            },
        ),
    )

    call_kwargs = provider.client.responses.create.await_args.kwargs
    assert "previous_response_id" not in call_kwargs
    assert call_kwargs["input"][1] == {
        "type": "reasoning",
        "id": "rs_1",
        "summary": [
            {
                "type": "summary_text",
                "text": "Reasoning summary",
            },
        ],
        "encrypted_content": "encrypted-blob",
    }
    assert call_kwargs["input"][2] == {
        "type": "function_call",
        "id": "fc_1",
        "call_id": "call_1",
        "name": "navigate",
        "arguments": '{"to_page_title": "Banana"}',
        "status": "completed",
    }
    assert call_kwargs["input"][3] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": "ok",
        "status": "completed",
    }


@pytest.mark.asyncio
async def test_anthropic_provider_sends_output_config_directly() -> None:
    provider = AnthropicChatProvider(
        api_key="test-key",
    )
    provider.client.messages.create = AsyncMock(
        return_value=SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="thinking",
                    thinking="Reasoning summary",
                ),
                SimpleNamespace(
                    type="text",
                    text="hello",
                ),
            ],
            usage=SimpleNamespace(
                input_tokens=12,
                output_tokens=6,
            ),
            stop_reason="end_turn",
        ),
    )

    response = await provider.generate(
        ProviderRequest(
            model_id="claude-sonnet-4-6",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="hello",
                ),
            ],
            settings={
                "thinking": {
                    "type": "adaptive",
                },
                "output_config": {
                    "effort": "high",
                },
            },
        ),
    )

    call_kwargs = provider.client.messages.create.await_args.kwargs
    assert call_kwargs["output_config"] == {
        "effort": "high",
    }
    assert call_kwargs["thinking"] == {
        "type": "adaptive",
    }
    assert "extra_body" not in call_kwargs
    assert "cache_control" not in call_kwargs
    assert response.message.thinking == "Reasoning summary"
    assert response.message.content == "hello"


@pytest.mark.asyncio
async def test_anthropic_provider_defaults_adaptive_thinking_max_tokens_high() -> None:
    provider = AnthropicChatProvider(
        api_key="test-key",
    )
    provider.client.messages.create = AsyncMock(
        return_value=SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="text",
                    text="hello",
                ),
            ],
            usage=SimpleNamespace(
                input_tokens=12,
                output_tokens=6,
            ),
            stop_reason="end_turn",
        ),
    )

    await provider.generate(
        ProviderRequest(
            model_id="claude-opus-4-6",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="hello",
                ),
            ],
            settings={
                "thinking": {
                    "type": "adaptive",
                },
                "output_config": {
                    "effort": "max",
                },
            },
        ),
    )

    call_kwargs = provider.client.messages.create.await_args.kwargs
    assert call_kwargs["max_tokens"] == 128_000


@pytest.mark.asyncio
async def test_anthropic_provider_sends_cache_control_directly_when_enabled() -> None:
    provider = AnthropicChatProvider(
        api_key="test-key",
    )
    provider.client.messages.create = AsyncMock(
        return_value=SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="text",
                    text="hello",
                ),
            ],
            usage=SimpleNamespace(
                input_tokens=12,
                output_tokens=6,
            ),
            stop_reason="end_turn",
        ),
    )

    await provider.generate(
        ProviderRequest(
            model_id="claude-sonnet-4-6",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="hello",
                ),
            ],
            settings={
                "anthropic_prompt_caching": True,
            },
        ),
    )

    call_kwargs = provider.client.messages.create.await_args.kwargs
    assert "cache_control" not in call_kwargs
    assert call_kwargs["messages"][-1]["content"][-1]["cache_control"] == {
        "type": "ephemeral",
        "ttl": "5m",
    }


@pytest.mark.asyncio
async def test_anthropic_provider_total_tokens_include_cache_usage() -> None:
    provider = AnthropicChatProvider(
        api_key="test-key",
    )
    provider.client.messages.create = AsyncMock(
        return_value=SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="text",
                    text="hello",
                ),
            ],
            usage=SimpleNamespace(
                input_tokens=1,
                output_tokens=6,
                cache_creation_input_tokens=20,
                cache_read_input_tokens=30,
            ),
            stop_reason="end_turn",
        ),
    )

    response = await provider.generate(
        ProviderRequest(
            model_id="claude-sonnet-4-6",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="hello",
                ),
            ],
        ),
    )

    assert response.usage.input_tokens == 1
    assert response.usage.output_tokens == 6
    assert response.usage.cache_creation_input_tokens == 20
    assert response.usage.cache_read_input_tokens == 30
    assert response.usage.total_tokens == 57


@pytest.mark.asyncio
async def test_anthropic_vertex_provider_uses_keymaker_and_forces_five_minute_cache(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "KM_APP_CONTEXT_FCIAGENT",
        "km-bootstrap-token",
    )
    http_client = _FakeAnthropicVertexHTTPClient()
    provider = AnthropicVertexChatProvider(
        config=_AnthropicVertexConfig(
            base_url="https://vertex.example.test",
            model_base_url="https://aiplatform.example.test",
            project="test-project",
            location="global",
            cosmos_app_id="test-app",
            cosmos_app_scope="dev",
            aiml_gateway_app_context_key_name="gateway-context",
            keymaker_base_url="https://keymaker.example.test",
            keymaker_app_context_env_var="KM_APP_CONTEXT_FCIAGENT",
            beta_headers=("context-1m-2025-08-07",),
        ),
        http_client=http_client,  # type: ignore[arg-type]
    )

    response = await provider.generate(
        ProviderRequest(
            model_id="claude-opus-4-6",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="Navigate from Claude Shannon to OpenAI.",
                ),
            ],
            settings={
                "thinking": {
                    "type": "adaptive",
                },
                "output_config": {
                    "effort": "max",
                },
                "anthropic_prompt_caching": False,
                "timeout_s": 180,
            },
        ),
    )

    keymaker_call = http_client.get_calls[0]
    assert (
        keymaker_call["url"] == "https://keymaker.example.test/kmsapi/v1/keyobject/all"
    )
    assert keymaker_call["headers"]["X-KM-APP-CONTEXT"] == "km-bootstrap-token"

    token_call = http_client.post_calls[0]
    assert token_call["headers"]["x-cosmos-application-context"] == "gateway-secret"
    assert token_call["json"] == {
        "gcp_project_name": "test-project",
        "cosmos_app_id": "test-app",
        "cosmos_app_scope": "dev",
    }

    raw_predict_call = http_client.stream_calls[0]
    assert raw_predict_call["method"] == "POST"
    assert raw_predict_call["url"].endswith(
        "/v1/projects/test-project/locations/global/publishers/anthropic/models/claude-opus-4-6:streamRawPredict",
    )
    assert raw_predict_call["headers"]["Authorization"] == "Bearer vertex-token"
    assert raw_predict_call["headers"]["x-cosmos-app-id"] == "test-app"
    assert raw_predict_call["headers"]["anthropic-beta"] == "context-1m-2025-08-07"
    assert raw_predict_call["timeout"] == 180
    payload = raw_predict_call["json"]
    assert payload["anthropic_version"] == "vertex-2023-10-16"
    assert payload["stream"] is True
    assert payload["max_tokens"] == 128_000
    assert payload["thinking"] == {
        "type": "adaptive",
    }
    assert payload["output_config"] == {
        "effort": "max",
    }
    assert payload["messages"][-1]["content"][-1]["cache_control"] == {
        "type": "ephemeral",
        "ttl": "5m",
    }
    assert response.message.thinking == "Reasoning summary"
    assert response.message.tool_calls[0].arguments == {
        "to_page_title": "OpenAI",
    }
    assert response.usage.total_tokens == 220


@pytest.mark.asyncio
async def test_anthropic_vertex_provider_does_not_retry_model_timeouts(
    monkeypatch,
) -> None:
    class _TimeoutRawPredictHTTPClient(_FakeAnthropicVertexHTTPClient):
        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, object],
            timeout: float | None = None,
        ) -> _FakeHTTPResponse:
            self.post_calls.append(
                {
                    "url": url,
                    "headers": headers,
                    "json": json,
                    "timeout": timeout,
                },
            )
            if url.endswith(
                "/gcpAuth/generateImpersonationAuthToken",
            ):
                return _FakeHTTPResponse(
                    {
                        "auth_token": "vertex-token",
                        "token_expiry_window_seconds": 1800,
                    },
                )
            raise httpx.ReadTimeout(
                "rawPredict timed out",
            )

    monkeypatch.setenv(
        "KM_APP_CONTEXT_FCIAGENT",
        "km-bootstrap-token",
    )
    http_client = _TimeoutRawPredictHTTPClient()
    provider = AnthropicVertexChatProvider(
        config=_AnthropicVertexConfig(
            base_url="https://vertex.example.test",
            model_base_url="https://aiplatform.example.test",
            project="test-project",
            location="global",
            cosmos_app_id="test-app",
            cosmos_app_scope="dev",
            aiml_gateway_app_context_key_name="gateway-context",
            keymaker_base_url="https://keymaker.example.test",
            keymaker_app_context_env_var="KM_APP_CONTEXT_FCIAGENT",
        ),
        http_client=http_client,  # type: ignore[arg-type]
    )

    with pytest.raises(
        ProviderTimeoutError,
        match="Anthropic Vertex timed out",
    ):
        await provider.generate(
            ProviderRequest(
                model_id="claude-opus-4-6",
                messages=[
                    ProviderMessage(
                        role=ProviderMessageRole.USER,
                        content="Navigate from Claude Shannon to OpenAI.",
                    ),
                ],
                settings={
                    "anthropic_prompt_caching": False,
                    "vertex_anthropic_streaming": False,
                    "timeout_s": 180,
                },
            ),
        )

    raw_predict_calls = [
        call
        for call in http_client.post_calls
        if str(
            call["url"],
        ).endswith(
            ":rawPredict",
        )
    ]
    assert len(
        raw_predict_calls,
    ) == 1
    assert raw_predict_calls[0]["timeout"] == 180


@pytest.mark.asyncio
async def test_anthropic_provider_rejects_missing_pricing_before_request() -> None:
    provider = AnthropicChatProvider(
        api_key="test-key",
    )
    provider.client.messages.create = AsyncMock()

    with pytest.raises(
        ProviderConfigurationError,
        match="Missing pricing for provider 'anthropic' model 'claude-test'",
    ):
        await provider.generate(
            ProviderRequest(
                model_id="claude-test",
                messages=[
                    ProviderMessage(
                        role=ProviderMessageRole.USER,
                        content="hello",
                    ),
                ],
            ),
        )

    provider.client.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_anthropic_provider_allows_explicit_pricing_for_unknown_model() -> None:
    provider = AnthropicChatProvider(
        api_key="test-key",
    )
    provider.client.messages.create = AsyncMock(
        return_value=SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="text",
                    text="hello",
                ),
            ],
            usage=SimpleNamespace(
                input_tokens=1_000,
                output_tokens=500,
            ),
            stop_reason="end_turn",
        ),
    )

    response = await provider.generate(
        ProviderRequest(
            model_id="claude-test",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="hello",
                ),
            ],
            settings={
                "input_cost_per_1m_tokens": 3.0,
                "output_cost_per_1m_tokens": 15.0,
            },
        ),
    )

    call_kwargs = provider.client.messages.create.await_args.kwargs
    assert "input_cost_per_1m_tokens" not in call_kwargs
    assert "output_cost_per_1m_tokens" not in call_kwargs
    assert response.usage.estimated_cost_usd == pytest.approx(0.0105)


@pytest.mark.asyncio
async def test_anthropic_provider_error_preserves_sdk_message() -> None:
    provider = AnthropicChatProvider(
        api_key="test-key",
    )
    provider.client.messages.create = AsyncMock(
        side_effect=AnthropicError(
            "403 invalid x-api-key",
        ),
    )

    with pytest.raises(
        ProviderError,
        match="Anthropic provider request failed: 403 invalid x-api-key",
    ):
        await provider.generate(
            ProviderRequest(
                model_id="claude-sonnet-4-6",
                messages=[
                    ProviderMessage(
                        role=ProviderMessageRole.USER,
                        content="hello",
                    ),
                ],
            ),
        )
