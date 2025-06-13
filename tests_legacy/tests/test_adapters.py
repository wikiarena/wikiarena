"""
Tests for adapter classes and tool mapping functionality.
"""

import pytest
from unittest.mock import AsyncMock, Mock
from mcp.types import Tool

from wiki_arena.adapters.base import ToolSignature
from wiki_arena.adapters.navigation import NavigationAdapter
from wiki_arena.capabilities.navigation import INavigationCapability


class TestToolSignature:
    """Test utility functions for tool signature checking."""
    
    def test_has_required_parameters_success(self):
        """Test successful parameter checking."""
        tool = Tool(
            name="test_tool",
            description="Test",
            inputSchema={
                "properties": {
                    "page": {"type": "string"},
                    "limit": {"type": "integer"}
                }
            }
        )
        
        assert ToolSignature.has_required_parameters(tool, ["page"])
        assert ToolSignature.has_required_parameters(tool, ["page", "limit"])
        assert not ToolSignature.has_required_parameters(tool, ["page", "missing"])
    
    def test_has_required_parameters_no_schema(self):
        """Test parameter checking with missing schema."""
        tool = Tool(
            name="test_tool", 
            description="Test",
            inputSchema={}  # Empty schema
        )
        
        assert not ToolSignature.has_required_parameters(tool, ["page"])
    
    def test_matches_name_pattern(self):
        """Test tool name pattern matching."""
        tool = Tool(
            name="navigate_to_page", 
            description="Test",
            inputSchema={}
        )
        
        assert ToolSignature.matches_name_pattern(tool, ["navigate"])
        assert ToolSignature.matches_name_pattern(tool, ["nav", "page"])
        assert not ToolSignature.matches_name_pattern(tool, ["search", "find"])
    
    def test_matches_name_pattern_case_insensitive(self):
        """Test case-insensitive pattern matching."""
        tool = Tool(
            name="Navigate_To_Page", 
            description="Test",
            inputSchema={}
        )
        
        assert ToolSignature.matches_name_pattern(tool, ["navigate"])
        assert ToolSignature.matches_name_pattern(tool, ["NAVIGATE"])


class TestNavigationAdapter:
    """Test navigation adapter functionality."""
    
    @pytest.fixture
    def mock_mcp_client(self):
        return Mock()
    
    @pytest.fixture
    def navigation_adapter(self, mock_mcp_client):
        return NavigationAdapter(mock_mcp_client)
    
    def test_capability_type(self, navigation_adapter):
        """Test capability type property."""
        assert navigation_adapter.capability_type == INavigationCapability
    
    def test_required_tool_patterns(self, navigation_adapter):
        """Test required tool patterns."""
        patterns = navigation_adapter.required_tool_patterns
        assert "navigate" in patterns
        assert "nav" in patterns
        assert "page" in patterns
        assert "wiki" in patterns
    
    def test_compatible_tool_detection(self, navigation_adapter):
        """Test detection of compatible tools."""
        # Compatible tool
        compatible_tool = Tool(
            name="navigate",
            description="Navigate to page",
            inputSchema={
                "properties": {
                    "page": {"type": "string"}
                }
            }
        )
        
        # Incompatible tool (wrong name)
        wrong_name_tool = Tool(
            name="search",
            description="Search",
            inputSchema={
                "properties": {
                    "query": {"type": "string"}
                }
            }
        )
        
        # Incompatible tool (no string parameters)
        no_string_tool = Tool(
            name="navigate",
            description="Navigate",
            inputSchema={
                "properties": {
                    "count": {"type": "integer"}
                }
            }
        )
        
        assert navigation_adapter.is_tool_compatible(compatible_tool)
        assert not navigation_adapter.is_tool_compatible(wrong_name_tool)
        assert not navigation_adapter.is_tool_compatible(no_string_tool)
    
    @pytest.mark.asyncio
    async def test_discover_compatible_tools(self, navigation_adapter):
        """Test discovery of compatible tools."""
        tools = [
            Tool(
                name="navigate",
                description="Navigate",
                inputSchema={"properties": {"page": {"type": "string"}}}
            ),
            Tool(
                name="search",
                description="Search",
                inputSchema={"properties": {"query": {"type": "string"}}}
            ),
            Tool(
                name="wiki_page",
                description="Get wiki page",
                inputSchema={"properties": {"title": {"type": "string"}}}
            )
        ]
        
        compatible = await navigation_adapter.discover_compatible_tools(tools)
        
        # Should find navigate and wiki_page tools
        assert len(compatible) == 2
        compatible_names = [tool.name for tool in compatible]
        assert "navigate" in compatible_names
        assert "wiki_page" in compatible_names
        assert "search" not in compatible_names
    
    def test_is_available(self, navigation_adapter):
        """Test availability checking."""
        # Initially no tools
        assert not navigation_adapter.is_available()
        
        # Add compatible tool
        navigation_adapter._compatible_tools = [
            Tool(
                name="navigate", 
                description="Test",
                inputSchema={"properties": {"page": {"type": "string"}}}
            )
        ]
        assert navigation_adapter.is_available()
    
    def test_get_primary_tool(self, navigation_adapter):
        """Test getting primary tool."""
        # No tools
        assert navigation_adapter.get_primary_tool() is None
        
        # With tools
        tool1 = Tool(
            name="navigate", 
            description="Test1",
            inputSchema={"properties": {"page": {"type": "string"}}}
        )
        tool2 = Tool(
            name="wiki_page", 
            description="Test2",
            inputSchema={"properties": {"title": {"type": "string"}}}
        )
        navigation_adapter._compatible_tools = [tool1, tool2]
        
        assert navigation_adapter.get_primary_tool() == tool1
    
    @pytest.mark.asyncio
    async def test_create_capability_instance_no_tools(self, navigation_adapter):
        """Test capability creation with no compatible tools."""
        capability = await navigation_adapter.create_capability_instance()
        assert capability is None
    
    @pytest.mark.asyncio
    async def test_create_capability_instance_with_tools(self, navigation_adapter):
        """Test capability creation with compatible tools."""
        tool = Tool(
            name="navigate",
            description="Navigate",
            inputSchema={"properties": {"page": {"type": "string"}}}
        )
        navigation_adapter._compatible_tools = [tool]
        
        capability = await navigation_adapter.create_capability_instance()
        assert capability is not None
        assert isinstance(capability, INavigationCapability) 