"""
Navigation Adapter

Maps between navigation capability interface and MCP navigation tools.
Handles discovery, parameter mapping, and response parsing for navigation operations.
"""

from typing import List, Type, Optional, Dict, Any
import json
import urllib.parse

from mcp.types import Tool, CallToolResult, TextContent, EmbeddedResource

from wiki_arena.adapters.base import CapabilityAdapter, ToolSignature
from wiki_arena.capabilities.navigation import INavigationCapability, NavigationResult
from wiki_arena.models import Page


class NavigationCapabilityImpl(INavigationCapability):
    """
    Implementation of navigation capability using MCP tools.
    """
    
    def __init__(self, adapter: 'NavigationAdapter', primary_tool: Tool):
        self.adapter = adapter
        self.primary_tool = primary_tool
        self.logger = adapter.logger
    
    async def navigate_to_page(self, page_title: str) -> NavigationResult:
        """Navigate to a page using the MCP tool."""
        try:
            # Map capability parameters to tool parameters
            tool_args = self._map_navigation_parameters(page_title)
            
            # Call the MCP tool
            tool_result = await self.adapter.mcp_client.call_tool(
                tool_name=self.primary_tool.name,
                arguments=tool_args
            )
            
            # Parse the response
            return await self._parse_navigation_response(tool_result, page_title)
            
        except Exception as e:
            self.logger.error(f"Navigation failed: {e}", exc_info=True)
            return NavigationResult(
                success=False,
                error_message=f"Navigation error: {str(e)}"
            )
    
    def _map_navigation_parameters(self, page_title: str) -> Dict[str, Any]:
        """Map navigation parameters to tool-specific format."""
        # Check what parameter name the tool expects
        if not self.primary_tool.inputSchema or not self.primary_tool.inputSchema.get("properties"):
            return {"page": page_title}  # Fallback
        
        properties = self.primary_tool.inputSchema["properties"]
        
        # Try common parameter names
        if "page" in properties:
            return {"page": page_title}
        elif "page_title" in properties:
            return {"page_title": page_title}
        elif "title" in properties:
            return {"title": page_title}
        else:
            # Use the first string parameter found
            for param_name, param_def in properties.items():
                if param_def.get("type") == "string":
                    return {param_name: page_title}
            
            # Last resort
            return {"page": page_title}
    
    async def _parse_navigation_response(self, tool_result: CallToolResult, requested_title: str) -> NavigationResult:
        """Parse MCP tool response into NavigationResult."""
        if tool_result.isError:
            error_msg = "Unknown error"
            if tool_result.content and isinstance(tool_result.content[0], TextContent):
                error_msg = tool_result.content[0].text
            
            return NavigationResult(
                success=False,
                error_message=f"Tool error: {error_msg}"
            )
        
        if not tool_result.content:
            return NavigationResult(
                success=False,
                error_message="No content returned from navigation tool"
            )
        
        # Parse response content
        text_content = None
        structured_data = None
        
        for content_item in tool_result.content:
            if isinstance(content_item, TextContent):
                text_content = content_item.text
            elif isinstance(content_item, EmbeddedResource):
                try:
                    if hasattr(content_item.resource, 'text'):
                        structured_data = json.loads(content_item.resource.text)
                except (json.JSONDecodeError, AttributeError) as e:
                    self.logger.warning(f"Failed to parse structured data: {e}")
        
        # Extract page information
        page = self._extract_page_from_response(
            text_content, structured_data, requested_title
        )
        
        if page:
            return NavigationResult(success=True, page=page)
        else:
            return NavigationResult(
                success=False,
                error_message="Could not extract page information from tool response"
            )
    
    def _extract_page_from_response(
        self, 
        text_content: Optional[str], 
        structured_data: Optional[Dict], 
        requested_title: str
    ) -> Optional[Page]:
        """Extract Page object from tool response."""
        
        # Prefer structured data if available
        if structured_data:
            title = structured_data.get("title", requested_title)
            links = structured_data.get("links", [])
            url = structured_data.get("url", f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}")
            
            self.logger.info(f"Extracted page '{title}' with {len(links)} links from structured data")
            
            return Page(
                title=title,
                url=url,
                text=text_content or "",
                links=links
            )
        
        # Fallback to text parsing
        elif text_content:
            return self._parse_page_from_text(text_content, requested_title)
        
        return None
    
    def _parse_page_from_text(self, text_content: str, requested_title: str) -> Optional[Page]:
        """Parse page information from text content."""
        # This is a fallback parser for text-only responses
        # Implementation depends on the specific format of your MCP server
        
        lines = text_content.split("\\n")
        title = requested_title
        links = []
        
        in_links_section = False
        for line in lines:
            line = line.strip()
            
            if line.startswith("Current Page:") or line.startswith("Page:"):
                # Extract title
                title_part = line.split(":", 1)[1].strip()
                if title_part:
                    title = title_part
            elif "Available Links:" in line or "Links:" in line:
                in_links_section = True
            elif in_links_section and line:
                # Simple link extraction - adapt based on your format
                links.append(line)
        
        url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
        
        self.logger.info(f"Parsed page '{title}' with {len(links)} links from text")
        
        return Page(
            title=title,
            url=url,
            text=text_content,
            links=links
        )
    
    async def get_capability_info(self) -> Dict[str, Any]:
        """Get information about this navigation capability."""
        return {
            "type": "text_navigation",
            "tool_name": self.primary_tool.name,
            "tool_description": self.primary_tool.description,
            "features": ["page_navigation", "link_extraction"]
        }
    
    def is_available(self) -> bool:
        """Check if navigation capability is available."""
        return self.adapter.is_available()


class NavigationAdapter(CapabilityAdapter):
    """
    Adapter that provides navigation capability using MCP navigation tools.
    """
    
    @property
    def capability_type(self) -> Type:
        return INavigationCapability
    
    @property
    def required_tool_patterns(self) -> List[str]:
        return ["navigate", "nav", "page", "wiki"]
    
    def is_tool_compatible(self, tool: Tool) -> bool:
        """Check if a tool is compatible with navigation capability."""
        # Check tool name patterns
        if not ToolSignature.matches_name_pattern(tool, self.required_tool_patterns):
            return False
        
        # Check for required parameters (at least one string parameter)
        if not tool.inputSchema or not tool.inputSchema.get("properties"):
            return False
        
        properties = tool.inputSchema["properties"]
        has_string_param = any(
            param.get("type") == "string" 
            for param in properties.values()
        )
        
        if not has_string_param:
            return False
        
        self.logger.debug(f"Tool '{tool.name}' is compatible with navigation capability")
        return True
    
    async def create_capability_instance(self) -> Optional[INavigationCapability]:
        """Create a navigation capability instance."""
        primary_tool = self.get_primary_tool()
        if not primary_tool:
            self.logger.error("No compatible navigation tools available")
            return None
        
        self.logger.info(f"Creating navigation capability using tool '{primary_tool.name}'")
        return NavigationCapabilityImpl(self, primary_tool) 