# Game Tools Definition
# Defines all tools available to language models in WikiArena

from typing import Dict, Any, List

from wiki_arena.wikipedia import LiveWikiService

# Tool Implementation
async def navigate(to_page_title: str, wiki_service: LiveWikiService) -> str:
    """
    The actual implementation of the navigate tool.
    It fetches a page from Wikipedia.
    """
    # The core logic is to use the wiki_service to get the page.
    # We will handle the page object and potential errors in the game loop.
    page = await wiki_service.get_page(to_page_title, include_all_namespaces=False)
    return page

# Tool Schema
NAVIGATE_TOOL_SCHEMA = {
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

# Tool Registry
# This maps tool names to their schema and implementation
TOOL_REGISTRY = {
    "navigate": {
        "schema": NAVIGATE_TOOL_SCHEMA,
        "implementation": navigate,
    }
}


def get_tools() -> List[Dict[str, Any]]:
    """
    Get all tool schemas available for the WikiArena game.
    
    Returns:
        List of tool definitions in MCP format
    """
    return [t["schema"] for t in TOOL_REGISTRY.values()]


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
    if name in TOOL_REGISTRY:
        return TOOL_REGISTRY[name]
    raise ValueError(f"Tool '{name}' not found") 