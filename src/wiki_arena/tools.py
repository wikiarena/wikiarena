# Game Tools Definition
# Defines all tools available to language models in WikiArena

from typing import Dict, Any, List

# Navigate tool definition in MCP format
NAVIGATE_TOOL = {
    "name": "navigate",
    "description": "Navigate to a Wikipedia page and get all available links on that page.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "to_page_title": {
                "type": "string",
                "description": "Wikipedia page title to navigate to"
            }
        },
        "required": ["to_page_title"]
    }
}

def get_tools() -> List[Dict[str, Any]]:
    """
    Get all tools available for the WikiArena game.
    
    Returns:
        List of tool definitions in MCP format
    """
    return [NAVIGATE_TOOL]

def get_tool_by_name(name: str) -> Dict[str, Any]:
    """
    Get a specific tool by name.
    
    Args:
        name: Tool name to retrieve
        
    Returns:
        Tool definition in MCP format
        
    Raises:
        ValueError: If tool not found
    """
    tools = get_tools()
    for tool in tools:
        if tool["name"] == name:
            return tool
    raise ValueError(f"Tool '{name}' not found") 