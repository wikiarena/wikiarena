from __future__ import annotations

import json

import pytest

from wikiarena.providers import (
    AnthropicChatProvider,
    CodexChatProvider,
    OpenAIChatProvider,
    ProviderConfigurationError,
    create_provider_client,
)


def test_create_openai_client_uses_openai_environment_settings(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_BASE_URL",
        "https://openai-compatible.example.com",
    )
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider_client = create_provider_client(
        "openai",
    )

    assert isinstance(
        provider_client,
        OpenAIChatProvider,
    )
    assert provider_client.base_url == "https://openai-compatible.example.com"
    assert provider_client.default_api_mode == "responses"
    assert provider_client.supported_api_modes == frozenset({"responses"})
    assert provider_client.prompt_cache_key.startswith("wikiarena-")


def test_create_openai_compatible_client_keeps_chat_completions_compatibility(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_BASE_URL",
        "https://openai-compatible.example.com",
    )
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-key",
    )

    provider_client = create_provider_client(
        "openai_compatible",
    )

    assert isinstance(
        provider_client,
        OpenAIChatProvider,
    )
    assert provider_client.default_api_mode == "chat_completions"
    assert provider_client.supported_api_modes == frozenset(
        {"chat_completions", "responses"},
    )
    assert provider_client.prompt_cache_key is None


def test_create_anthropic_client_uses_standard_environment_settings(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "ANTHROPIC_API_KEY",
        "test-api-key",
    )

    provider_client = create_provider_client(
        "anthropic",
    )

    assert isinstance(
        provider_client,
        AnthropicChatProvider,
    )


def test_create_codex_client_uses_codex_auth_file_environment_settings(
    monkeypatch,
    tmp_path,
) -> None:
    auth_file = tmp_path / "codex-auth.json"
    auth_file.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": "header.payload.signature",
                    "refresh_token": "refresh-token",
                    "account_id": "account-123",
                },
            },
        ),
    )
    monkeypatch.setenv(
        "CODEX_AUTH_FILE",
        str(auth_file),
    )

    provider_client = create_provider_client(
        "codex",
    )

    assert isinstance(
        provider_client,
        CodexChatProvider,
    )
    assert provider_client.auth_file == auth_file
    assert provider_client.base_url == "https://chatgpt.com/backend-api/codex/responses"
    assert provider_client.prompt_cache_key.startswith("wikiarena-")


def test_create_provider_client_fails_without_required_api_key(
    monkeypatch,
) -> None:
    monkeypatch.delenv(
        "OPENROUTER_API_KEY",
        raising=False,
    )

    with pytest.raises(
        ProviderConfigurationError,
        match="Missing required api_key",
    ):
        create_provider_client(
            "openrouter",
        )
