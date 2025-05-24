"""
Base Adapter Classes

Defines the base interfaces and utilities for creating tool adapters that map
between MCP tools and capability interfaces.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Type
import logging

from mcp.types import Tool
from wiki_arena.mcp_client.client import MCPClient


class CapabilityAdapter(ABC):
    """
    Base class for adapters that provide capabilities using MCP tools.
    
    Adapters are responsible for:
    1. Discovering compatible MCP tools
    2. Mapping capability operations to tool calls
    3. Parsing tool responses into capability results
    """
    
    def __init__(self, mcp_client: MCPClient):
        self.mcp_client = mcp_client
        self._available_tools: List[Tool] = []
        self._compatible_tools: List[Tool] = []
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @property
    @abstractmethod
    def capability_type(self) -> Type:
        """The capability interface this adapter provides."""
        pass
    
    @property
    @abstractmethod
    def required_tool_patterns(self) -> List[str]:
        """
        Tool name patterns this adapter can work with.
        
        Examples: ["navigate", "navigate_to_page", "wiki_navigate"]
        """
        pass
    
    @abstractmethod
    def is_tool_compatible(self, tool: Tool) -> bool:
        """
        Check if a specific tool is compatible with this adapter.
        
        Args:
            tool: The MCP tool to check
            
        Returns:
            True if this adapter can use the tool
        """
        pass
    
    @abstractmethod
    async def create_capability_instance(self) -> Any:
        """
        Create an instance of the capability this adapter provides.
        
        Returns:
            An instance implementing the capability interface
        """
        pass
    
    async def discover_compatible_tools(self, available_tools: List[Tool]) -> List[Tool]:
        """
        Discover tools compatible with this adapter.
        
        Args:
            available_tools: List of available MCP tools
            
        Returns:
            List of compatible tools
        """
        self._available_tools = available_tools
        self._compatible_tools = [
            tool for tool in available_tools 
            if self.is_tool_compatible(tool)
        ]
        
        self.logger.info(
            f"Found {len(self._compatible_tools)} compatible tools "
            f"out of {len(available_tools)} available tools"
        )
        
        return self._compatible_tools
    
    def get_primary_tool(self) -> Optional[Tool]:
        """Get the primary tool to use (first compatible tool found)."""
        return self._compatible_tools[0] if self._compatible_tools else None
    
    def is_available(self) -> bool:
        """Check if this adapter has compatible tools available."""
        return len(self._compatible_tools) > 0


class ToolSignature:
    """
    Utility class for checking tool compatibility based on signatures.
    """
    
    @staticmethod
    def has_required_parameters(tool: Tool, required_params: List[str]) -> bool:
        """Check if tool has all required parameters."""
        if not tool.inputSchema or not tool.inputSchema.get("properties"):
            return False
        
        properties = tool.inputSchema["properties"]
        return all(param in properties for param in required_params)
    
    @staticmethod
    def matches_name_pattern(tool: Tool, patterns: List[str]) -> bool:
        """Check if tool name matches any of the given patterns."""
        tool_name = tool.name.lower()
        return any(pattern.lower() in tool_name for pattern in patterns) 