"""
Tests for capability registry functionality.
"""

import pytest
from unittest.mock import AsyncMock, Mock
from mcp.types import Tool, ListToolsResult

from wiki_arena.services.capability_registry import CapabilityRegistry
from wiki_arena.capabilities.navigation import INavigationCapability


class TestCapabilityRegistry:
    """Test capability registry functionality."""
    
    @pytest.fixture
    def mock_mcp_client(self):
        client = Mock()
        client.list_tools = AsyncMock()
        return client
    
    @pytest.fixture
    def registry(self, mock_mcp_client):
        return CapabilityRegistry(mock_mcp_client)
    
    @pytest.fixture
    def sample_tools(self):
        return [
            Tool(
                name="navigate",
                description="Navigate to page",
                inputSchema={"properties": {"page": {"type": "string"}}}
            ),
            Tool(
                name="search",
                description="Search content",
                inputSchema={"properties": {"query": {"type": "string"}}}
            ),
            Tool(
                name="wiki_page",
                description="Get wiki page",
                inputSchema={"properties": {"title": {"type": "string"}}}
            )
        ]
    
    def test_initialization(self, registry):
        """Test registry initialization."""
        assert not registry._is_initialized
        assert len(registry._adapters) > 0  # Should have default adapters
        assert len(registry._capabilities) == 0
    
    @pytest.mark.asyncio
    async def test_successful_initialization(self, registry, mock_mcp_client, sample_tools):
        """Test successful registry initialization."""
        # Mock tool discovery
        mock_mcp_client.list_tools.return_value = ListToolsResult(tools=sample_tools)
        
        success = await registry.initialize()
        
        assert success
        assert registry._is_initialized
        assert len(registry._available_tools) == 3
        
        # Should have created navigation capability
        assert registry.is_capability_available(INavigationCapability)
    
    @pytest.mark.asyncio
    async def test_initialization_failure(self, registry, mock_mcp_client):
        """Test registry initialization failure."""
        # Mock tool discovery failure
        mock_mcp_client.list_tools.side_effect = Exception("Connection failed")
        
        success = await registry.initialize()
        
        assert not success
        assert not registry._is_initialized
    
    @pytest.mark.asyncio
    async def test_get_capability_before_init(self, registry):
        """Test getting capability before initialization."""
        capability = registry.get_capability(INavigationCapability)
        assert capability is None
    
    @pytest.mark.asyncio
    async def test_get_navigation_capability(self, registry, mock_mcp_client, sample_tools):
        """Test getting navigation capability."""
        mock_mcp_client.list_tools.return_value = ListToolsResult(tools=sample_tools)
        
        await registry.initialize()
        
        nav_capability = registry.get_navigation_capability()
        assert nav_capability is not None
        assert isinstance(nav_capability, INavigationCapability)
    
    @pytest.mark.asyncio
    async def test_get_capability_generic(self, registry, mock_mcp_client, sample_tools):
        """Test generic capability retrieval."""
        mock_mcp_client.list_tools.return_value = ListToolsResult(tools=sample_tools)
        
        await registry.initialize()
        
        nav_capability = registry.get_capability(INavigationCapability)
        assert nav_capability is not None
        assert isinstance(nav_capability, INavigationCapability)
    
    @pytest.mark.asyncio
    async def test_list_available_capabilities(self, registry, mock_mcp_client, sample_tools):
        """Test listing available capabilities."""
        mock_mcp_client.list_tools.return_value = ListToolsResult(tools=sample_tools)
        
        await registry.initialize()
        
        capabilities = registry.list_available_capabilities()
        assert "INavigationCapability" in capabilities
    
    @pytest.mark.asyncio
    async def test_capability_info(self, registry, mock_mcp_client, sample_tools):
        """Test getting capability information."""
        mock_mcp_client.list_tools.return_value = ListToolsResult(tools=sample_tools)
        
        await registry.initialize()
        
        info = await registry.get_capability_info()
        assert "INavigationCapability" in info
        assert isinstance(info["INavigationCapability"], dict)
    
    def test_registry_status(self, registry):
        """Test getting registry status."""
        status = registry.get_registry_status()
        
        assert "initialized" in status
        assert "available_tools" in status
        assert "registered_adapters" in status
        assert "available_capabilities" in status
        assert "capability_types" in status
        
        assert not status["initialized"]
        assert status["available_tools"] == 0
        assert status["registered_adapters"] > 0
        assert status["available_capabilities"] == 0
    
    @pytest.mark.asyncio
    async def test_no_compatible_tools(self, registry, mock_mcp_client):
        """Test initialization with no compatible tools."""
        # Only incompatible tools
        incompatible_tools = [
            Tool(
                name="search",
                description="Search",
                inputSchema={"properties": {"query": {"type": "string"}}}
            )
        ]
        
        mock_mcp_client.list_tools.return_value = ListToolsResult(tools=incompatible_tools)
        
        success = await registry.initialize()
        
        # Should still succeed initialization
        assert success
        assert registry._is_initialized
        
        # But no navigation capability should be available
        assert not registry.is_capability_available(INavigationCapability)
        nav_capability = registry.get_navigation_capability()
        assert nav_capability is None 