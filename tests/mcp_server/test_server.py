import pytest
import pytest_asyncio
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
import asyncio

# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(scope="function")
async def session():
    """
    Test client for the MCP server running over STDIO.
    This runs the server as a subprocess and connects to it,
    setting PYTHONPATH to make the `src` directory importable.
    """
    # Parameters to run the server script.
    # We set PYTHONPATH to `src` so that the subprocess can find
    # the `wiki_arena` package correctly.
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "mcp_server"],
        env={"PYTHONPATH": "src"},
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as s:
            # Initialize with timeout
            try:
                await asyncio.wait_for(s.initialize(), timeout=10.0)
                yield s
            except asyncio.TimeoutError:
                raise RuntimeError("Failed to initialize MCP session within 10 seconds")


@pytest.mark.asyncio
async def test_navigate_tool_success(session: ClientSession):
    """
    Tests a successful call to the 'navigate' tool over stdio.
    """
    page_to_navigate = "Python (programming language)"
    
    # Add timeout to the tool call
    try:
        result = await asyncio.wait_for(
            session.call_tool("navigate", {"page": page_to_navigate}), 
            timeout=30.0
        )
    except asyncio.TimeoutError:
        pytest.fail("Tool call timed out after 30 seconds")

    # The result should be a CallToolResult with content
    assert result is not None
    assert isinstance(result, types.ToolCallResult)
    assert hasattr(result, 'content')
    assert isinstance(result.content, list)
    assert len(result.content) == 2

    text_content = result.content[0]
    assert isinstance(text_content, types.TextContent)
    assert f"Current Page: {page_to_navigate}" in text_content.text
    assert "Total Links:" in text_content.text

    resource_content = result.content[1]
    assert isinstance(resource_content, types.EmbeddedResource)
    # Convert AnyUrl to string and check the base URI pattern
    uri_str = str(resource_content.resource.uri)
    assert uri_str.startswith("wikipedia://")
    assert "Python" in uri_str
    assert "programming" in uri_str
    assert "language" in uri_str


@pytest.mark.asyncio
async def test_navigate_tool_page_not_found(session: ClientSession):
    """
    Tests the 'navigate' tool's error handling for a non-existent page.
    """
    page_to_navigate = "PageThatAbsolutelyDoesNotExist_XYZ123"
    
    # Add timeout to the tool call
    try:
        result = await asyncio.wait_for(
            session.call_tool("navigate", {"page": page_to_navigate}), 
            timeout=30.0
        )
    except asyncio.TimeoutError:
        pytest.fail("Tool call timed out after 30 seconds")

    # The result should be a CallToolResult with isError=True
    assert result is not None
    assert isinstance(result, types.ToolCallResult)
    assert hasattr(result, 'content')
    assert hasattr(result, 'isError')
    assert result.isError is True  # This indicates an actual error occurred
    assert isinstance(result.content, list)
    assert len(result.content) == 1

    error_content = result.content[0]
    assert isinstance(error_content, types.TextContent)
    # The error message should contain information about the page not being found
    assert "does not exist" in error_content.text


@pytest.mark.asyncio 
async def test_server_initialization(session: ClientSession):
    """
    Tests that we can connect to and initialize the MCP server.
    """
    # Test listing tools
    try:
        tools_result = await asyncio.wait_for(session.list_tools(), timeout=10.0)
        assert tools_result.tools
        
        # Find the navigate tool
        navigate_tool = next((tool for tool in tools_result.tools if tool.name == "navigate"), None)
        assert navigate_tool is not None
        assert navigate_tool.description is not None
        assert "page" in str(navigate_tool.inputSchema)
        
    except asyncio.TimeoutError:
        pytest.fail("Failed to list tools within 10 seconds") 