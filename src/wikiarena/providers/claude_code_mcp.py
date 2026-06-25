from __future__ import annotations

import json
import os
import sys
from typing import Any


def main() -> None:
    for line in sys.stdin:
        try:
            request = json.loads(
                line,
            )
        except json.JSONDecodeError:
            continue
        response = _handle_request(
            request,
        )
        if response is None:
            continue
        sys.stdout.write(
            json.dumps(
                response,
                separators=(",", ":"),
            )
            + "\n",
        )
        sys.stdout.flush()


def _handle_request(
    request: dict[str, Any],
) -> dict[str, Any] | None:
    method = request.get(
        "method",
    )
    request_id = request.get(
        "id",
    )
    if request_id is None:
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                },
                "serverInfo": {
                    "name": "wikiarena",
                    "version": "0.1.0",
                },
            },
        }
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": _tools_from_env(),
            },
        }
    if method == "tools/call":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "Tool call captured by Wikiarena harness.",
                    },
                ],
                "isError": False,
            },
        }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": -32601,
            "message": f"Unsupported method: {method}",
        },
    }


def _tools_from_env() -> list[dict[str, Any]]:
    raw_tools = os.environ.get(
        "WIKIARENA_CLAUDE_CODE_MCP_TOOLS",
    )
    if not raw_tools:
        return []
    tools = json.loads(
        raw_tools,
    )
    if not isinstance(
        tools,
        list,
    ):
        return []
    return [
        tool
        for tool in tools
        if isinstance(
            tool,
            dict,
        )
    ]


if __name__ == "__main__":
    main()
