from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from anthropic import AnthropicError
from openai import OpenAIError

from wikiarena.providers.client import _build_anthropic_cache_control
from wikiarena.providers.client import _anthropic_prompt_caching_enabled
from wikiarena.providers.client import _CODEX_OAUTH_CLIENT_ID
from wikiarena.providers.client import _CODEX_OAUTH_TOKEN_URL
from wikiarena.providers.client import _estimate_token_cost_usd
from wikiarena.providers.client import _format_messages_for_anthropic
from wikiarena.providers.client import _format_messages_for_openai_responses
from wikiarena.providers.client import AnthropicChatProvider
from wikiarena.providers.client import CodexChatProvider
from wikiarena.providers.client import OpenAIChatProvider
from wikiarena.providers.client import ProviderConfigurationError
from wikiarena.providers.client import ProviderError
from wikiarena.providers.types import ProviderMessage
from wikiarena.providers.types import ProviderMessageRole
from wikiarena.providers.types import ProviderReasoningItem
from wikiarena.providers.types import ProviderRequest
from wikiarena.providers.types import ProviderToolCall


def _create_test_jwt(
    payload: dict[str, object],
) -> str:
    header = base64.urlsafe_b64encode(
        b'{"alg":"none"}',
    ).decode().rstrip("=")
    body = base64.urlsafe_b64encode(
        json.dumps(
            payload,
        ).encode(),
    ).decode().rstrip("=")
    return f"{header}.{body}.sig"


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
    ) -> None:
        self.status_code = status_code
        self._lines = list(
            lines or [],
        )
        self._text = text or ""

    async def aiter_lines(
        self,
    ):
        for line in self._lines:
            yield line

    async def aread(
        self,
    ) -> bytes:
        return self._text.encode()


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


def test_format_messages_for_anthropic_applies_cache_marker_to_last_user_block() -> None:
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


def test_format_messages_for_openai_responses_normalizes_synthetic_tool_call_ids() -> None:
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
    assert response.usage.output_token_details == {
        "reasoning_tokens": 3,
    }
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
        "max_output_tokens": 128,
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
                model_id="gpt-test",
                messages=[
                    ProviderMessage(
                        role=ProviderMessageRole.USER,
                        content="hello",
                    ),
                ],
            ),
        )


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
                model_id="gpt-test",
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
            model_id="gpt-test",
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
async def test_openai_provider_responses_api_returns_summary_and_encrypted_reasoning() -> None:
    provider = OpenAIChatProvider(
        api_key="test-key",
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
            model_id="gpt-test",
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
    assert create_kwargs["include"] == ["reasoning.encrypted_content"]
    assert create_kwargs["reasoning"] == {
        "summary": "auto",
    }


@pytest.mark.asyncio
async def test_openai_provider_responses_api_uses_previous_response_id_for_follow_up() -> None:
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
            model_id="gpt-test",
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
            model_id="gpt-test",
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
async def test_openai_provider_responses_api_replays_encrypted_reasoning_without_previous_response_id() -> None:
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
            model_id="gpt-test",
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
            model_id="claude-test",
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
            model_id="claude-test",
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
                model_id="claude-test",
                messages=[
                    ProviderMessage(
                        role=ProviderMessageRole.USER,
                        content="hello",
                    ),
                ],
            ),
        )
