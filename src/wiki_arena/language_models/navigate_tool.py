# Navigate Tool Definition
# Single source of truth for the navigate tool used across all providers

from typing import Dict, Any, List
from dataclasses import dataclass, field

@dataclass
class NavigateToolDefinition:
    """Standard definition of the navigate tool that can be converted to provider formats."""
    
    name: str = "navigate"
    description: str = "Navigate to a Wikipedia page and get all available links on that page."
    
    # Standard JSON schema for the tool parameters
    parameter_schema: Dict[str, Any] = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "page": {
                "type": "string",
                "description": "Wikipedia page title to navigate to"
            }
        },
        "required": ["page"]
    })
    
    def to_openai_format(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameter_schema
            }
        }
    
    def to_anthropic_format(self) -> Dict[str, Any]:
        """Convert to Anthropic tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameter_schema
        }
    
    def to_mcp_tool_format(self) -> Dict[str, Any]:
        """Convert to MCP Tool format for compatibility."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.parameter_schema
        }

# Global instance - single source of truth
NAVIGATE_TOOL = NavigateToolDefinition()