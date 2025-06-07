"""
Capability Registry

Discovers available MCP tools, maps them to capability adapters,
and provides capability instances to the game logic.
"""

from typing import Dict, List, Optional, Type, TypeVar, cast
import logging

from mcp.types import Tool

from wiki_arena.mcp_client.client import MCPClient
from wiki_arena.adapters.base import CapabilityAdapter
from wiki_arena.adapters.navigation import NavigationAdapter
from wiki_arena.capabilities.navigation import INavigationCapability

T = TypeVar('T')


class CapabilityRegistry:
    """
    Registry for discovering and providing capabilities based on available MCP tools.
    
    This is the main service that the game logic uses to get capabilities
    without knowing about specific tools or adapters.
    """
    
    def __init__(self, mcp_client: MCPClient):
        self.mcp_client = mcp_client
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Registry state
        self._available_tools: List[Tool] = []
        self._adapters: List[CapabilityAdapter] = []
        self._capabilities: Dict[Type, object] = {}
        self._is_initialized = False
        
        # Register default adapters
        self._register_default_adapters()
    
    def _register_default_adapters(self):
        """Register the default capability adapters."""
        self._adapters = [
            NavigationAdapter(self.mcp_client),
            # Future adapters go here:
            # ComputerUseNavigationAdapter(self.mcp_client),
        ]
        
        self.logger.info(f"Registered {len(self._adapters)} default adapters")
    
    async def initialize(self) -> bool:
        """
        Initialize the registry by discovering tools and capabilities.
        
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            # Discover available tools
            self.logger.info("Discovering available MCP tools...")
            list_tools_result = await self.mcp_client.list_tools()
            self._available_tools = list_tools_result.tools
            
            self.logger.info(f"Found {len(self._available_tools)} available tools")
            
            # Discover compatible tools for each adapter
            for adapter in self._adapters:
                compatible_tools = await adapter.discover_compatible_tools(self._available_tools)
                self.logger.info(
                    f"Adapter {adapter.__class__.__name__} found "
                    f"{len(compatible_tools)} compatible tools"
                )
            
            # Create capability instances
            await self._create_capability_instances()
            
            self._is_initialized = True
            self.logger.info("Capability registry initialization complete")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize capability registry: {e}", exc_info=True)
            return False
    
    async def _create_capability_instances(self):
        """Create instances of available capabilities."""
        for adapter in self._adapters:
            if adapter.is_available():
                try:
                    capability_instance = await adapter.create_capability_instance()
                    if capability_instance:
                        capability_type = adapter.capability_type
                        self._capabilities[capability_type] = capability_instance
                        self.logger.info(
                            f"Created capability instance for {capability_type.__name__}"
                        )
                except Exception as e:
                    self.logger.error(
                        f"Failed to create capability instance for "
                        f"{adapter.__class__.__name__}: {e}",
                        exc_info=True
                    )
    
    def get_capability(self, capability_type: Type[T]) -> Optional[T]:
        """
        Get a capability instance by type.
        
        Args:
            capability_type: The capability interface type to get
            
        Returns:
            Capability instance or None if not available
        """
        if not self._is_initialized:
            self.logger.warning("Registry not initialized - call initialize() first")
            return None
        
        capability = self._capabilities.get(capability_type)
        if capability:
            return cast(T, capability)
        
        self.logger.warning(f"Capability {capability_type.__name__} not available")
        return None
    
    def get_navigation_capability(self) -> Optional[INavigationCapability]:
        """Convenience method to get navigation capability."""
        return self.get_capability(INavigationCapability)
    
    def is_capability_available(self, capability_type: Type) -> bool:
        """Check if a capability is available."""
        return capability_type in self._capabilities
    
    def list_available_capabilities(self) -> List[str]:
        """List all available capability types."""
        return [cap_type.__name__ for cap_type in self._capabilities.keys()]
    
    async def get_capability_info(self) -> Dict[str, dict]:
        """Get information about all available capabilities."""
        info = {}
        for cap_type, cap_instance in self._capabilities.items():
            if hasattr(cap_instance, 'get_capability_info'):
                try:
                    info[cap_type.__name__] = await cap_instance.get_capability_info()
                except Exception as e:
                    info[cap_type.__name__] = {"error": str(e)}
            else:
                info[cap_type.__name__] = {"type": "unknown"}
        
        return info
    
    def get_registry_status(self) -> Dict[str, any]:
        """Get status information about the registry."""
        return {
            "initialized": self._is_initialized,
            "available_tools": len(self._available_tools),
            "registered_adapters": len(self._adapters),
            "available_capabilities": len(self._capabilities),
            "capability_types": list(self._capabilities.keys())
        } 