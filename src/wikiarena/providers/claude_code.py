from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from wikiarena.providers.types import (
    ProviderMessage,
    ProviderMessageRole,
    ProviderRequest,
    ProviderResponse,
    ProviderToolCall,
    ProviderUsage,
)

from .client import ProviderConfigurationError, ProviderError, ProviderTimeoutError

_DEFAULT_CONTINUATION_PROMPT = "continue"
_DEFAULT_CLAUDE_PATH = "claude"
_CLAUDE_TOOL_PREFIX = "mcp__wikiarena__"


class ClaudeCodeProvider:
    def __init__(
        self,
        *,
        claude_bin: str | None = None,
        oauth_token: str | None = None,
        config_root: Path | None = None,
        workspace_root: Path | None = None,
        timeout_s: float | None = None,
    ) -> None:
        self.claude_bin = claude_bin or shutil.which(
            _DEFAULT_CLAUDE_PATH,
        )
        if not self.claude_bin:
            raise ProviderConfigurationError(
                "Missing claude binary for provider 'claude-code'",
            )
        self.oauth_token = oauth_token or os.getenv(
            "CLAUDE_CODE_OAUTH_TOKEN",
        )
        if not self.oauth_token:
            raise ProviderConfigurationError(
                "Missing required oauth_token for provider 'claude-code'",
            )
        self.config_root = config_root
        self.workspace_root = workspace_root
        self.timeout_s = timeout_s

    async def generate(
        self,
        request: ProviderRequest,
    ) -> ProviderResponse:
        start = time.perf_counter()
        with tempfile.TemporaryDirectory(
            prefix="wikiarena-claude-code-",
        ) as tmp_dir_name:
            tmp_dir = Path(
                tmp_dir_name,
            )
            config_dir = self.config_root or tmp_dir / "config"
            workspace_dir = self.workspace_root or tmp_dir / "workspace"
            home_dir = tmp_dir / "home"
            config_dir.mkdir(
                parents=True,
                exist_ok=True,
            )
            workspace_dir.mkdir(
                parents=True,
                exist_ok=True,
            )
            home_dir.mkdir(
                parents=True,
                exist_ok=True,
            )
            session_id = self._write_session(
                request,
                config_dir=config_dir,
                workspace_dir=workspace_dir,
            )
            system_prompt_path = tmp_dir / "system.md"
            system_prompt_path.write_text(
                _system_prompt_from_request(
                    request,
                ),
            )
            mcp_config_path = tmp_dir / "mcp.json"
            mcp_config_path.write_text(
                json.dumps(
                    _mcp_config(
                        request,
                    ),
                    separators=(",", ":"),
                ),
            )
            proc = await asyncio.create_subprocess_exec(
                *self._build_command(
                    request=request,
                    session_id=session_id,
                    system_prompt_path=system_prompt_path,
                    mcp_config_path=mcp_config_path,
                ),
                cwd=workspace_dir,
                env=self._build_env(
                    config_dir=config_dir,
                    home_dir=home_dir,
                    request=request,
                ),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.timeout_s,
                )
            except TimeoutError as timeout_error:
                proc.kill()
                await proc.wait()
                raise ProviderTimeoutError(
                    "Claude Code provider timed out",
                ) from timeout_error
            stdout = stdout_bytes.decode(
                errors="replace",
            )
            stderr = stderr_bytes.decode(
                errors="replace",
            )
            response = _response_from_stdout(
                stdout,
                response_time_ms=(time.perf_counter() - start) * 1000.0,
            )
            if proc.returncode != 0 and response.message.tool_calls:
                return response
            if proc.returncode != 0:
                raise ProviderError(
                    "Claude Code provider failed: "
                    f"exit={proc.returncode} stderr={stderr[-2000:]}",
                )
            if not response.message.tool_calls:
                raise ProviderError(
                    "Claude Code provider did not return a tool call",
                )
            return response

    def _write_session(
        self,
        request: ProviderRequest,
        *,
        config_dir: Path,
        workspace_dir: Path,
    ) -> str:
        session_id = str(
            uuid.uuid4(),
        )
        project_dir = config_dir / "projects" / _project_dir_for(
            workspace_dir,
        )
        project_dir.mkdir(
            parents=True,
            exist_ok=True,
        )
        prompt_id = str(
            uuid.uuid4(),
        )
        rows = _session_rows_from_messages(
            request.messages,
            session_id=session_id,
            prompt_id=prompt_id,
            cwd=workspace_dir.resolve(),
            model_id=request.model_id,
        )
        rows.append(
            {
                "type": "last-prompt",
                "lastPrompt": _first_user_prompt(
                    request.messages,
                ),
                "sessionId": session_id,
            },
        )
        path = project_dir / f"{session_id}.jsonl"
        path.write_text(
            "\n".join(
                json.dumps(
                    row,
                    separators=(",", ":"),
                )
                for row in rows
            )
            + "\n",
        )
        return session_id

    def _build_command(
        self,
        *,
        request: ProviderRequest,
        session_id: str,
        system_prompt_path: Path,
        mcp_config_path: Path,
    ) -> list[str]:
        return [
            self.claude_bin or _DEFAULT_CLAUDE_PATH,
            "-p",
            _DEFAULT_CONTINUATION_PROMPT,
            "--resume",
            session_id,
            "--model",
            request.model_id,
            "--system-prompt-file",
            str(
                system_prompt_path,
            ),
            "--tools",
            "",
            "--allowedTools",
            "mcp__wikiarena__navigate",
            "--strict-mcp-config",
            "--mcp-config",
            str(
                mcp_config_path,
            ),
            "--disable-slash-commands",
            "--setting-sources",
            "",
            "--output-format",
            "stream-json",
            "--max-turns",
            "1",
            "--verbose",
        ]

    def _build_env(
        self,
        *,
        config_dir: Path,
        home_dir: Path,
        request: ProviderRequest,
    ) -> dict[str, str]:
        env = {
            "PATH": os.getenv(
                "PATH",
                "",
            ),
            "HOME": str(
                home_dir,
            ),
            "CLAUDE_CONFIG_DIR": str(
                config_dir,
            ),
            "CLAUDE_CODE_OAUTH_TOKEN": self.oauth_token or "",
            "DISABLE_AUTOUPDATER": "1",
            "DISABLE_NON_ESSENTIAL_MODEL_CALLS": "1",
            "DISABLE_TELEMETRY": "1",
            "DISABLE_ERROR_REPORTING": "1",
            "TERM": "dumb",
        }
        base_url = request.settings.get(
            "base_url",
        ) or os.getenv(
            "ANTHROPIC_BASE_URL",
        )
        if base_url:
            env["ANTHROPIC_BASE_URL"] = str(
                base_url,
            )
        for name in (
            "NODE_EXTRA_CA_CERTS",
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
            "REQUESTS_CA_BUNDLE",
            "CURL_CA_BUNDLE",
        ):
            value = os.getenv(
                name,
            )
            if value:
                env[name] = value
        return env


def _session_rows_from_messages(
    messages: list[ProviderMessage],
    *,
    session_id: str,
    prompt_id: str,
    cwd: Path,
    model_id: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    parent_uuid: str | None = None
    common = {
        "isSidechain": False,
        "userType": "external",
        "entrypoint": "sdk-cli",
        "cwd": str(
            cwd,
        ),
        "sessionId": session_id,
        "version": "2.1.119",
        "gitBranch": "HEAD",
    }
    for message in messages:
        if message.role == ProviderMessageRole.SYSTEM:
            continue
        row_uuid = str(
            uuid.uuid4(),
        )
        row = _session_row_from_message(
            message,
            parent_uuid=parent_uuid,
            row_uuid=row_uuid,
            prompt_id=prompt_id,
            model_id=model_id,
            common=common,
        )
        if row is not None:
            rows.append(
                row,
            )
            parent_uuid = row_uuid
    return rows


def _session_row_from_message(
    message: ProviderMessage,
    *,
    parent_uuid: str | None,
    row_uuid: str,
    prompt_id: str,
    model_id: str,
    common: dict[str, Any],
) -> dict[str, Any] | None:
    timestamp = "2026-01-01T00:00:00.000Z"
    if message.role == ProviderMessageRole.USER:
        return {
            "parentUuid": parent_uuid,
            "promptId": prompt_id,
            "type": "user",
            "message": {
                "role": "user",
                "content": message.content or "",
            },
            "uuid": row_uuid,
            "timestamp": timestamp,
            "permissionMode": "default",
            **common,
        }
    if message.role == ProviderMessageRole.ASSISTANT:
        content = []
        if message.content:
            content.append(
                {
                    "type": "text",
                    "text": message.content,
                },
            )
        for tool_call in message.tool_calls:
            content.append(
                {
                    "type": "tool_use",
                    "id": tool_call.id,
                    "name": _claude_tool_name(
                        tool_call.name,
                    ),
                    "input": tool_call.arguments,
                },
            )
        return {
            "parentUuid": parent_uuid,
            "message": {
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "role": "assistant",
                "model": model_id,
                "content": content,
                "stop_reason": "tool_use" if message.tool_calls else "end_turn",
                "stop_sequence": None,
                "usage": _empty_claude_usage(),
            },
            "type": "assistant",
            "uuid": row_uuid,
            "timestamp": timestamp,
            **common,
        }
    if message.role == ProviderMessageRole.TOOL:
        return {
            "parentUuid": parent_uuid,
            "promptId": prompt_id,
            "type": "user",
            "message": {
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
            "uuid": row_uuid,
            "timestamp": timestamp,
            "toolUseResult": {
                "content": [
                    {
                        "type": "text",
                        "text": message.content or "",
                    },
                ],
                "isError": message.is_error,
            },
            "sourceToolUseID": message.tool_call_id,
            **common,
        }
    return None


def _response_from_stdout(
    stdout: str,
    *,
    response_time_ms: float,
) -> ProviderResponse:
    last_usage: dict[str, Any] = {}
    first_tool_response: ProviderResponse | None = None
    for line in stdout.splitlines():
        try:
            event = json.loads(
                line,
            )
        except json.JSONDecodeError:
            continue
        if event.get(
            "type",
        ) == "result":
            usage = event.get(
                "usage",
                {},
            )
            if isinstance(
                usage,
                dict,
            ):
                last_usage = usage
            continue
        if event.get(
            "type",
        ) != "assistant":
            continue
        message = event.get(
            "message",
        )
        if not isinstance(
            message,
            dict,
        ):
            continue
        last_usage = message.get(
            "usage",
            {},
        )
        tool_calls = _tool_calls_from_claude_message(
            message,
        )
        if not tool_calls:
            continue
        if first_tool_response is not None:
            continue
        first_tool_response = ProviderResponse(
            provider_response_id=message.get(
                "id",
            ),
            message=ProviderMessage(
                role=ProviderMessageRole.ASSISTANT,
                content=_text_from_claude_message(
                    message,
                ),
                tool_calls=tool_calls,
            ),
            usage=_usage_from_claude_usage(
                last_usage,
                response_time_ms=response_time_ms,
            ),
        )
    if first_tool_response is not None:
        first_tool_response.usage = _usage_from_claude_usage(
            last_usage,
            response_time_ms=response_time_ms,
        )
        return first_tool_response
    return ProviderResponse(
        message=ProviderMessage(
            role=ProviderMessageRole.ASSISTANT,
        ),
        usage=_usage_from_claude_usage(
            last_usage,
            response_time_ms=response_time_ms,
        ),
    )


def _tool_calls_from_claude_message(
    message: dict[str, Any],
) -> list[ProviderToolCall]:
    tool_calls: list[ProviderToolCall] = []
    content = message.get(
        "content",
        [],
    )
    if not isinstance(
        content,
        list,
    ):
        return tool_calls
    for block in content:
        if not isinstance(
            block,
            dict,
        ) or block.get(
            "type",
        ) != "tool_use":
            continue
        tool_calls.append(
            ProviderToolCall(
                id=str(
                    block.get(
                        "id",
                        "",
                    ),
                ),
                name=_wikiarena_tool_name(
                    str(
                        block.get(
                            "name",
                            "",
                        ),
                    ),
                ),
                arguments=dict(
                    block.get(
                        "input",
                        {},
                    )
                    or {},
                ),
            ),
        )
    return tool_calls


def _text_from_claude_message(
    message: dict[str, Any],
) -> str | None:
    parts: list[str] = []
    for block in message.get(
        "content",
        [],
    ):
        if isinstance(
            block,
            dict,
        ) and block.get(
            "type",
        ) == "text":
            parts.append(
                str(
                    block.get(
                        "text",
                        "",
                    ),
                ),
            )
    return "".join(
        parts,
    ) or None


def _usage_from_claude_usage(
    usage: dict[str, Any],
    *,
    response_time_ms: float,
) -> ProviderUsage:
    input_tokens = int(
        usage.get(
            "input_tokens",
            0,
        )
        or 0,
    )
    output_tokens = int(
        usage.get(
            "output_tokens",
            0,
        )
        or 0,
    )
    cache_creation_input_tokens = int(
        usage.get(
            "cache_creation_input_tokens",
            0,
        )
        or 0,
    )
    cache_read_input_tokens = int(
        usage.get(
            "cache_read_input_tokens",
            0,
        )
        or 0,
    )
    return ProviderUsage(
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
        response_time_ms=response_time_ms,
    )


def _system_prompt_from_request(
    request: ProviderRequest,
) -> str:
    return "\n\n".join(
        message.content or ""
        for message in request.messages
        if message.role == ProviderMessageRole.SYSTEM and message.content
    )


def _first_user_prompt(
    messages: list[ProviderMessage],
) -> str:
    for message in messages:
        if message.role == ProviderMessageRole.USER:
            return message.content or ""
    return ""


def _project_dir_for(
    cwd: Path,
) -> str:
    return str(
        cwd.resolve(),
    ).replace(
        "/",
        "-",
    )


def _mcp_config(
    request: ProviderRequest,
) -> dict[str, Any]:
    return {
        "mcpServers": {
            "wikiarena": {
                "command": sys.executable,
                "args": [
                    "-m",
                    "wikiarena.providers.claude_code_mcp",
                ],
                "env": {
                    "WIKIARENA_CLAUDE_CODE_MCP_TOOLS": json.dumps(
                        [
                            {
                                "name": tool.name,
                                "description": tool.description,
                                "inputSchema": tool.input_schema,
                            }
                            for tool in request.tools
                        ],
                        separators=(",", ":"),
                    ),
                },
            },
        },
    }


def _claude_tool_name(
    tool_name: str,
) -> str:
    if tool_name.startswith(
        _CLAUDE_TOOL_PREFIX,
    ):
        return tool_name
    return f"{_CLAUDE_TOOL_PREFIX}{tool_name}"


def _wikiarena_tool_name(
    tool_name: str,
) -> str:
    if tool_name.startswith(
        _CLAUDE_TOOL_PREFIX,
    ):
        return tool_name.removeprefix(
            _CLAUDE_TOOL_PREFIX,
        )
    return tool_name


def _empty_claude_usage() -> dict[str, Any]:
    return {
        "input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "output_tokens": 0,
        "server_tool_use": {
            "web_search_requests": 0,
            "web_fetch_requests": 0,
        },
        "service_tier": "standard",
    }
