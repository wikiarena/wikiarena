import asyncio
from typing import Optional, Dict, Any, Union
import logging

from mcp.types import ListToolsResult, CallToolResult
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from contextlib import AsyncExitStack

class MCPClient:
    def __init__(self):
        self._session: Optional[ClientSession] = None
        self._exit_stack: Optional[AsyncExitStack] = None
        self._is_connected = False
        self._server_params: Optional[StdioServerParameters] = None

    async def connect(self, server_params: StdioServerParameters):
        """Establishes a connection to the MCP server."""
        if self._is_connected:
            logging.info("Already connected.")
            return

        self._server_params = server_params # Store parameters for potential reconnects
        self._exit_stack = AsyncExitStack()

        try:
            logging.info(f"Connecting to server...")
            transport = stdio_client(server_params)
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
        return await self._session.list_tools()

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> CallToolResult:
        """Calls a specific tool on the connected server."""
        if not self._session:
            logging.warning(f"Attempted to call tool '{tool_name}' while not connected.")
            raise ConnectionError("Not connected to server.")
        logging.debug(f"Calling tool: {tool_name} with arguments: {arguments}")
        return await self._session.call_tool(tool_name, arguments)
