import asyncio
from typing import Optional, Dict, Any, Union
import logging

from pydantic import BaseModel, Field

from mcp.types import ListToolsResult, CallToolResult
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.sse import sse_client
from contextlib import AsyncExitStack

class SSEServerParameters(BaseModel):
    url: str
    headers: Optional[Dict[str, Any]] = Field(default_factory=dict)
    timeout: float = 5.0
    sse_read_timeout: float = 300.0 # 60 * 5

# Define a union type for server parameters for clarity
ServerParams = Union[StdioServerParameters, SSEServerParameters]

class MCPClient:
    def __init__(self):
        self._session: Optional[ClientSession] = None
        self._exit_stack: Optional[AsyncExitStack] = None
        self._is_connected = False
        self._server_params: Optional[ServerParams] = None

    async def connect(self, server_params: ServerParams):
        """Establishes a connection to the MCP server."""
        if self._is_connected:
            logging.info("Already connected.")
            return

        self._server_params = server_params # Store parameters for potential reconnects
        self._exit_stack = AsyncExitStack()

        try:
            logging.info(f"Connecting to server...")
            if isinstance(server_params, StdioServerParameters):
                transport = stdio_client(server_params)
            elif isinstance(server_params, SSEServerParameters):
                transport = sse_client(
                    url=server_params.url,
                    headers=server_params.headers,
                    timeout=server_params.timeout,
                    sse_read_timeout=server_params.sse_read_timeout
                )
            else:
                raise ValueError("Unsupported server parameter type")
            read, write = await self._exit_stack.enter_async_context(transport)

            self._session = await self._exit_stack.enter_async_context(ClientSession(read, write))
            await self._session.initialize()
            self._is_connected = True
            logging.info("Successfully connected and initialized MCP session.")

        except Exception as e:
            logging.error(f"Failed to connect or initialize MCP session: {e}")
            # Reset state and clean up on connection failure
            self._session = None
            if self._exit_stack:
                try:
                    await self._exit_stack.aclose()
                except Exception:
                    pass  # Ignore cleanup errors during failed connection
                self._exit_stack = None
            self._is_connected = False
            self._server_params = None
            raise

    async def disconnect(self):
        """Closes the connection to the MCP server."""
        if not self._is_connected:
            return

        logging.info("Disconnecting from MCP server...")
        
        # Reset state first to prevent partial cleanup issues
        self._session = None
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception as e:
                # Log but don't re-raise cleanup errors
                logging.debug(f"Error during exit stack cleanup: {e}")
        self._is_connected = False
        self._server_params = None
        
        logging.info("Disconnected.")

    async def list_tools(self) -> ListToolsResult:
        """Lists tools available on the connected server."""
        if not self._session:
            logging.warning("Attempted to list tools while not connected.")
            raise ConnectionError("Not connected to server.")
        logging.debug("Listing tools...")
        # TODO(llm): Add error handling here for communication issues after connecting
        return await self._session.list_tools()

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> CallToolResult:
        """Calls a specific tool on the connected server."""
        if not self._session:
            logging.warning(f"Attempted to call tool '{tool_name}' while not connected.")
            raise ConnectionError("Not connected to server.")
        logging.debug(f"Calling tool: {tool_name} with arguments: {arguments}")
        # TODO(llm): Add error handling here
        return await self._session.call_tool(tool_name, arguments)


def create_server_params_from_config(config: Dict[str, Any]) -> ServerParams:
    """Creates SDK server parameter objects from a dictionary config."""
    transport_type = config.get("type")
    if transport_type == "stdio":
        command = config.get("command")
        args = config.get("args", [])
        if not command:
            raise ValueError("Stdio server config missing 'command'.")
        return StdioServerParameters(command=command, args=args)
    elif transport_type == "sse":
        url = config.get("url")
        if not url:
             raise ValueError("SSE server config missing 'url'.")

        # Prepare kwargs for SSEServerParameters, only including keys present in config
        sse_kwargs: Dict[str, Any] = {"url": url}

        if "headers" in config:
            sse_kwargs["headers"] = config["headers"]
        if "timeout" in config:
            sse_kwargs["timeout"] = config["timeout"]
        if "sse_read_timeout" in config:
            sse_kwargs["sse_read_timeout"] = config["sse_read_timeout"]

        return SSEServerParameters(**sse_kwargs)
    else:
        raise ValueError(f"Unknown transport type: {transport_type}")