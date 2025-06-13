from mcp.server.fastmcp import FastMCP
from mcp import types
import json
import urllib.parse
from typing import List, Union
import sys

from wiki_arena.wikipedia import LiveWikiService
from wiki_arena.logging_config import setup_logging

# Configure unified logging to match the main application
setup_logging(level="INFO")

# Configure the server for stateless HTTP to enable testing
mcp = FastMCP("wiki-arena")

@mcp.tool()
async def navigate(page: str) -> List[Union[types.TextContent, types.EmbeddedResource]]:
    """
    Navigate to a Wikipedia page and get ALL available links.
    
    This tool is designed for the Wikipedia game where you navigate from page to page
    by clicking links. It returns every clickable link exactly as it appears on the page.
    
    Args:
        page: Wikipedia page title to navigate to
    
    Returns:
        All available links on the page
    """
    # Use the centralized service to fetch page data
    wiki_service = LiveWikiService(language="en")
    page_data = await wiki_service.get_page(page, include_all_namespaces=True)
    
    # Format links for display - preserve exact order
    if page_data.links:
        links_display = "\n".join(page_data.links)
        summary = f"""Current Page: {page_data.title}
Total Links: {len(page_data.links)}

Available Links:
{links_display}"""
    else:
        summary = f"Current Page: {page_data.title}\nNo links found on this page."
    
    # Prepare structured data for embedding
    resource_data = {
        "title": page_data.title,
        "url": page_data.url,
        "links": page_data.links,
        "total_links": len(page_data.links)
    }

    return [
        types.TextContent(type="text", text=summary),
        types.EmbeddedResource(
            type="resource",
            resource=types.TextResourceContents(
                uri=f"wikipedia://{urllib.parse.quote(page_data.title)}",
                mimeType="application/json",
                text=json.dumps(resource_data, ensure_ascii=False, indent=2)
            )
        )
    ]

if __name__ == "__main__":
    # All logging/debug prints should go to stderr to keep stdout clean for the protocol.
    print("Starting simplified Wiki Arena MCP server...", file=sys.stderr)
    mcp.run()
