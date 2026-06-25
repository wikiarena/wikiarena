from __future__ import annotations

import json
from pathlib import Path

import pytest

from wikiarena.providers.claude_code import ClaudeCodeProvider, _mcp_config
from wikiarena.providers.types import (
    ProviderMessage,
    ProviderMessageRole,
    ProviderRequest,
    ProviderTool,
)


def test_claude_code_provider_writes_forged_session(
    tmp_path: Path,
) -> None:
    provider = ClaudeCodeProvider(
        claude_bin="/bin/echo",
        oauth_token="sk-ant-oat01-test",
        config_root=tmp_path / "config",
        workspace_root=tmp_path / "workspace",
    )

    session = provider._write_session(
        ProviderRequest(
            model_id="claude-opus-4-7",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.SYSTEM,
                    content="system",
                ),
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="Navigate from 'Start' to 'Target'.",
                ),
                ProviderMessage(
                    role=ProviderMessageRole.ASSISTANT,
                    tool_calls=[],
                ),
            ],
        ),
        config_dir=tmp_path / "config",
        workspace_dir=tmp_path / "workspace",
    )

    session_path = next(
        (tmp_path / "config" / "projects").glob(f"*/{session}.jsonl"),
    )
    rows = [
        json.loads(
            line,
        )
        for line in session_path.read_text().splitlines()
    ]

    assert rows[0]["type"] == "user"
    assert rows[0]["message"]["content"] == "Navigate from 'Start' to 'Target'."
    assert rows[-1] == {
        "type": "last-prompt",
        "lastPrompt": "Navigate from 'Start' to 'Target'.",
        "sessionId": session,
    }


def test_claude_code_mcp_config_uses_request_tool_schema() -> None:
    config = _mcp_config(
        ProviderRequest(
            model_id="claude-opus-4-7",
            tools=[
                ProviderTool(
                    name="navigate",
                    description="Canonical navigate schema",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "to_page_title": {
                                "type": "string",
                            },
                        },
                        "required": [
                            "to_page_title",
                        ],
                    },
                ),
            ],
        ),
    )

    raw_tools = config["mcpServers"]["wikiarena"]["env"][
        "WIKIARENA_CLAUDE_CODE_MCP_TOOLS"
    ]
    assert json.loads(
        raw_tools,
    ) == [
        {
            "name": "navigate",
            "description": "Canonical navigate schema",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "to_page_title": {
                        "type": "string",
                    },
                },
                "required": [
                    "to_page_title",
                ],
            },
        },
    ]


@pytest.mark.asyncio
async def test_claude_code_provider_returns_first_stream_tool_call(
    tmp_path: Path,
) -> None:
    fake_claude = tmp_path / "fake-claude.py"
    fake_claude.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json",
                "print(json.dumps({'type':'assistant','message':{"
                "'id':'msg_1','role':'assistant','content':[{'type':'tool_use',"
                "'id':'toolu_1','name':'mcp__wikiarena__navigate',"
                "'input':{'to_page_title':'Target'}}],"
                "'usage':{'input_tokens':7,'output_tokens':3,"
                "'cache_creation_input_tokens':2,"
                "'cache_read_input_tokens':4}}}))",
                "print(json.dumps({'type':'result',"
                "'usage':{'input_tokens':11,'output_tokens':5,"
                "'cache_creation_input_tokens':13,"
                "'cache_read_input_tokens':17}}))",
                "print(json.dumps({'type':'user','message':{'role':'user'}}))",
            ],
        ),
    )
    fake_claude.chmod(
        0o755,
    )
    provider = ClaudeCodeProvider(
        claude_bin=str(
            fake_claude,
        ),
        oauth_token="sk-ant-oat01-test",
        config_root=tmp_path / "config",
        workspace_root=tmp_path / "workspace",
    )

    response = await provider.generate(
        ProviderRequest(
            model_id="claude-opus-4-7",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.SYSTEM,
                    content="system",
                ),
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="Navigate from 'Start' to 'Target'.",
                ),
            ],
            tools=[
                ProviderTool(
                    name="navigate",
                    description="Navigate",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "to_page_title": {
                                "type": "string",
                            },
                        },
                    },
                ),
            ],
        ),
    )

    assert response.provider_response_id == "msg_1"
    assert response.usage.input_tokens == 11
    assert response.usage.output_tokens == 5
    assert response.usage.cache_creation_input_tokens == 13
    assert response.usage.cache_read_input_tokens == 17
    assert response.usage.total_tokens == 46
    assert response.message.tool_calls[0].id == "toolu_1"
    assert response.message.tool_calls[0].name == "navigate"
    assert response.message.tool_calls[0].arguments == {
        "to_page_title": "Target",
    }


@pytest.mark.asyncio
async def test_claude_code_provider_accepts_max_turns_exit_with_tool_call(
    tmp_path: Path,
) -> None:
    fake_claude = tmp_path / "fake-claude.py"
    fake_claude.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "print(json.dumps({'type':'assistant','message':{"
                "'id':'msg_1','role':'assistant','content':[{'type':'tool_use',"
                "'id':'toolu_1','name':'mcp__wikiarena__navigate',"
                "'input':{'to_page_title':'Target'}}],"
                "'usage':{'input_tokens':7,'output_tokens':3}}}))",
                "sys.exit(1)",
            ],
        ),
    )
    fake_claude.chmod(
        0o755,
    )
    provider = ClaudeCodeProvider(
        claude_bin=str(
            fake_claude,
        ),
        oauth_token="sk-ant-oat01-test",
        config_root=tmp_path / "config",
        workspace_root=tmp_path / "workspace",
    )

    response = await provider.generate(
        ProviderRequest(
            model_id="claude-opus-4-7",
            messages=[
                ProviderMessage(
                    role=ProviderMessageRole.USER,
                    content="Navigate from 'Start' to 'Target'.",
                ),
            ],
        ),
    )

    assert response.message.tool_calls[0].arguments == {
        "to_page_title": "Target",
    }


@pytest.mark.asyncio
async def test_claude_code_provider_raises_on_missing_tool_call(
    tmp_path: Path,
) -> None:
    fake_claude = tmp_path / "fake-claude.py"
    fake_claude.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json",
                "print(json.dumps({'type':'assistant','message':{"
                "'id':'msg_1','role':'assistant','content':[{'type':'text',"
                "'text':'no tool'}]}}))",
            ],
        ),
    )
    fake_claude.chmod(
        0o755,
    )
    provider = ClaudeCodeProvider(
        claude_bin=str(
            fake_claude,
        ),
        oauth_token="sk-ant-oat01-test",
        config_root=tmp_path / "config",
        workspace_root=tmp_path / "workspace",
    )

    with pytest.raises(
        Exception,
        match="did not return a tool call",
    ):
        await provider.generate(
            ProviderRequest(
                model_id="claude-opus-4-7",
                messages=[
                    ProviderMessage(
                        role=ProviderMessageRole.USER,
                        content="continue",
                    ),
                ],
            ),
        )
