import pytest
import pytest_asyncio
import asyncio
from typing import Dict, Any, List

from mcp import types
from mcp.client.stdio import StdioServerParameters
from wiki_arena.mcp_client.client import MCPClient, SSEServerParameters

# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration

class TestMCPClientConnection:
    """Test MCP client connection management."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create a fresh MCP client for each test."""
        client = MCPClient()
        yield client
        # Clean up in fixture to avoid task issues
        if client._is_connected:
            try:
                await client.disconnect()
            except Exception:
                # Ignore cleanup errors - common with asyncio teardown
                pass

    @pytest.mark.asyncio
    async def test_stdio_connection_success(self, client):
        """Test successful connection to stdio MCP server."""
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "mcp_server.server"],
            env={"PYTHONPATH": "src"}
        )

        await client.connect(server_params)
        assert client._is_connected is True
        assert client._session is not None

        # Test basic functionality
        tools_result = await client.list_tools()
        assert tools_result.tools
        assert len(tools_result.tools) > 0

        await client.disconnect()
        assert client._is_connected is False

    @pytest.mark.asyncio
    async def test_stdio_connection_invalid_command(self, client):
        """Test connection failure with invalid command."""
        server_params = StdioServerParameters(
            command="nonexistent_command",
            args=[],
            env={}
        )

        with pytest.raises(Exception):
            await asyncio.wait_for(client.connect(server_params), timeout=5.0)
        
        assert client._is_connected is False

    @pytest.mark.asyncio
    async def test_stdio_connection_invalid_script(self, client):
        """Test connection failure with non-existent script."""
        server_params = StdioServerParameters(
            command="python",
            args=["non_existent_script.py"],
            env={}
        )

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(client.connect(server_params), timeout=5.0)
        
        assert client._is_connected is False

    @pytest.mark.asyncio
    async def test_double_connection_handling(self, client):
        """Test that connecting twice doesn't break anything."""
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "mcp_server.server"],
            env={"PYTHONPATH": "src"}
        )

        # First connection
        await client.connect(server_params)
        assert client._is_connected is True

        # Second connection should be harmless
        await client.connect(server_params)
        assert client._is_connected is True

        # Should still work
        tools_result = await client.list_tools()
        assert tools_result.tools

    @pytest.mark.asyncio
    async def test_operations_without_connection(self, client):
        """Test that operations fail gracefully when not connected."""
        with pytest.raises(ConnectionError, match="Not connected to server"):
            await client.list_tools()

        with pytest.raises(ConnectionError, match="Not connected to server"):
            await client.call_tool("navigate", {"page": "test"})


class TestMCPClientToolDiscovery:
    """Test MCP client tool discovery capabilities."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create a fresh MCP client for each test."""
        client = MCPClient()
        yield client
        # Clean up in fixture to avoid task issues
        if client._is_connected:
            try:
                await client.disconnect()
            except Exception:
                # Ignore cleanup errors - common with asyncio teardown
                pass

    @pytest.mark.asyncio
    async def test_list_tools_basic(self, client):
        """Test basic tool listing functionality."""
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "mcp_server.server"],
            env={"PYTHONPATH": "src"}
        )

        await client.connect(server_params)
        tools_result = await client.list_tools()
        
        assert tools_result is not None
        assert hasattr(tools_result, 'tools')
        assert isinstance(tools_result.tools, list)
        assert len(tools_result.tools) > 0

    @pytest.mark.asyncio
    async def test_navigate_tool_available(self, client):
        """Test that navigate tool is properly discovered."""
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "mcp_server.server"],
            env={"PYTHONPATH": "src"}
        )
        await client.connect(server_params)
        tools_result = await client.list_tools()
        
        # Find navigate tool
        navigate_tool = next((tool for tool in tools_result.tools if tool.name == "navigate"), None)
        assert navigate_tool is not None
        assert navigate_tool.description is not None
        assert "page" in str(navigate_tool.inputSchema)

    @pytest.mark.asyncio
    async def test_tool_schema_validation(self, client):
        """Test that tool schemas are properly structured."""
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "mcp_server.server"],
            env={"PYTHONPATH": "src"}
        )
        await client.connect(server_params)
        tools_result = await client.list_tools()
        
        for tool in tools_result.tools:
            # Each tool should have required fields
            assert hasattr(tool, 'name')
            assert hasattr(tool, 'description')
            assert hasattr(tool, 'inputSchema')
            assert tool.name is not None
            assert tool.description is not None
            assert tool.inputSchema is not None

    @pytest.mark.asyncio
    async def test_multiple_tool_listings(self, client):
        """Test that multiple tool listings return consistent results."""
        # Get tools multiple times
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "mcp_server.server"],
            env={"PYTHONPATH": "src"}
        )
        await client.connect(server_params)
        tools_result1 = await client.list_tools()
        tools_result2 = await client.list_tools()
        tools_result3 = await client.list_tools()

        # Should have same number of tools
        assert len(tools_result1.tools) == len(tools_result2.tools)
        assert len(tools_result2.tools) == len(tools_result3.tools)

        # Should have same tool names
        names1 = {tool.name for tool in tools_result1.tools}
        names2 = {tool.name for tool in tools_result2.tools}
        names3 = {tool.name for tool in tools_result3.tools}
        
        assert names1 == names2 == names3


class TestMCPClientToolExecution:
    """Test MCP client tool execution capabilities."""

    @pytest.mark.asyncio
    async def test_successful_tool_execution(self, client):
        """Test successful tool execution."""
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "mcp_server.server"],
            env={"PYTHONPATH": "src"}
        )
        await client.connect(server_params)
        result = await client.call_tool("navigate", {"page": "Python (programming language)"})
        
        assert result is not None
        assert hasattr(result, 'content')
        assert hasattr(result, 'isError')
        assert result.isError is False
        assert isinstance(result.content, list)
        assert len(result.content) > 0

    @pytest.mark.asyncio
    async def test_tool_execution_with_error(self, client):
        """Test tool execution that returns an error."""
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "mcp_server.server"],
            env={"PYTHONPATH": "src"}
        )
        await client.connect(server_params)
        result = await client.call_tool("navigate", {"page": "NonExistentPageXYZ123"})
        
        assert result is not None
        assert hasattr(result, 'isError')
        assert result.isError is True
        assert isinstance(result.content, list)
        assert len(result.content) > 0
        
        # Error content should be text
        error_content = result.content[0]
        assert isinstance(error_content, types.TextContent)

    @pytest.mark.asyncio
    async def test_tool_execution_invalid_tool_name(self, client):
        """Test tool execution with non-existent tool."""
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "mcp_server.server"],
            env={"PYTHONPATH": "src"}
        )
        await client.connect(server_params)
        result = await client.call_tool("nonexistent_tool", {"arg": "value"})
        
        # MCP returns error results, not exceptions
        assert result is not None
        assert hasattr(result, 'isError')
        assert result.isError is True
        assert isinstance(result.content, list)
        assert len(result.content) > 0
        
        error_content = result.content[0]
        assert isinstance(error_content, types.TextContent)
        assert "Unknown tool" in error_content.text

    @pytest.mark.asyncio
    async def test_tool_execution_invalid_arguments(self, client):
        """Test tool execution with invalid arguments."""
        # Missing required parameter
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "mcp_server.server"],
            env={"PYTHONPATH": "src"}
        )
        await client.connect(server_params)
        result = await client.call_tool("navigate", {})
        
        # MCP returns error results, not exceptions  
        assert result is not None
        assert hasattr(result, 'isError')
        assert result.isError is True
        assert isinstance(result.content, list)
        assert len(result.content) > 0
        
        error_content = result.content[0]
        assert isinstance(error_content, types.TextContent)
        assert "validation error" in error_content.text.lower()

    @pytest.mark.asyncio
    async def test_tool_execution_timeout(self, client):
        """Test tool execution with timeout handling."""
        try:
            result = await asyncio.wait_for(
                client.call_tool("navigate", {"page": "Python (programming language)"}),
                timeout=30.0
            )
            # If we get here, the tool executed within timeout
            assert result is not None
        except asyncio.TimeoutError:
            pytest.fail("Tool execution timed out")

    @pytest.mark.asyncio
    async def test_multiple_concurrent_tool_calls(self, client):
        """Test multiple concurrent tool executions."""
        pages = ["Python (programming language)", "JavaScript", "TypeScript"]
        
        # Execute multiple tools concurrently
        tasks = [
            client.call_tool("navigate", {"page": page})
            for page in pages
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should succeed or fail gracefully
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                pytest.fail(f"Tool call {i} raised exception: {result}")
            assert result is not None
            assert hasattr(result, 'content')


class TestMCPClientErrorHandling:
    """Test MCP client error handling and resilience."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create a fresh MCP client for each test."""
        client = MCPClient()
        yield client
        # Clean up in fixture
        try:
            await client.disconnect()
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_server_parameter_validation(self):
        """Test server parameter creation and validation."""
        from wiki_arena.mcp_client.client import create_server_params_from_config
        
        # Valid stdio config
        stdio_config = {
            "type": "stdio",
            "command": "python",
            "args": ["-m", "server"]
        }
        params = create_server_params_from_config(stdio_config)
        assert isinstance(params, StdioServerParameters)
        assert params.command == "python"
        assert params.args == ["-m", "server"]

        # Valid SSE config
        sse_config = {
            "type": "sse",
            "url": "http://localhost:3000/sse",
            "timeout": 10.0
        }
        params = create_server_params_from_config(sse_config)
        assert isinstance(params, SSEServerParameters)
        assert params.url == "http://localhost:3000/sse"
        assert params.timeout == 10.0

        # Invalid config - missing type
        with pytest.raises(ValueError):
            create_server_params_from_config({})

        # Invalid config - unknown type
        with pytest.raises(ValueError):
            create_server_params_from_config({"type": "unknown"})

        # Invalid config - missing required fields
        with pytest.raises(ValueError):
            create_server_params_from_config({"type": "stdio"})  # Missing command

        with pytest.raises(ValueError):
            create_server_params_from_config({"type": "sse"})  # Missing url

    @pytest.mark.asyncio
    async def test_client_cleanup_on_connection_failure(self, client):
        """Test that client cleans up properly on connection failure."""
        server_params = StdioServerParameters(
            command="nonexistent_command",
            args=[],
            env={}
        )

        # Add timeout to prevent hanging during failed connection attempts
        with pytest.raises(Exception):
            await asyncio.wait_for(client.connect(server_params), timeout=2.0)
        
        # Client should be properly cleaned up
        assert client._is_connected is False
        assert client._session is None
        # Note: _exit_stack might still exist but be in a cleaned state

    @pytest.mark.asyncio
    async def test_multiple_disconnections(self, client):
        """Test that multiple disconnections don't cause errors."""
        # Disconnect without connecting first
        await client.disconnect()  # Should not raise
        
        # Connect then disconnect multiple times
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "mcp_server.server"],
            env={"PYTHONPATH": "src"}
        )

        await client.connect(server_params)
        await client.disconnect()
        await client.disconnect()  # Second disconnect should be safe
        
        assert client._is_connected is False


class TestMCPClientMultiServer:
    """Test MCP client behavior with multiple servers."""

    @pytest.mark.asyncio
    async def test_multiple_sequential_client_instances(self):
        """Test that multiple client instances can work independently (sequentially)."""
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "mcp_server.server"],
            env={"PYTHONPATH": "src"}
        )

        # Test first client
        client1 = MCPClient()
        try:
            await client1.connect(server_params)
            assert client1._is_connected is True
            
            tools1 = await client1.list_tools()
            assert len(tools1.tools) > 0
            
            result1 = await client1.call_tool("navigate", {"page": "Python (programming language)"})
            assert result1.isError is False
            
        finally:
            try:
                await client1.disconnect()
            except Exception:
                pass
        
        # Ensure first client is fully cleaned up
        assert client1._is_connected is False
        
        # Test second client independently 
        client2 = MCPClient()
        try:
            await client2.connect(server_params)
            assert client2._is_connected is True
            
            tools2 = await client2.list_tools()
            assert len(tools2.tools) > 0
            
            result2 = await client2.call_tool("navigate", {"page": "JavaScript"})
            assert result2.isError is False
            
        finally:
            try:
                await client2.disconnect()
            except Exception:
                pass
        
        # Both clients should be independent and work correctly
        assert client2._is_connected is False 