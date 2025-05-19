from mcp.server.fastmcp import FastMCP
from typing import List
import wikipediaapi

# Create an MCP server
mcp = FastMCP("wiki-arena-mcp-server")

# Create a global Wikipedia API session with descriptive user agent
wiki_session = wikipediaapi.Wikipedia(
    language="en",
    user_agent="WikiArenaMCP/1.0" # TODO(hunter): build this from config
)

@mcp.tool(
    annotations={
        "title": "Get Wikipedia Page Text",
        "readOnlyHint": True,
        "openWorldHint": True,
    }
)
async def get_wikipedia_page_text(page_title: str) -> str:
    """
    Fetches the text content of a Wikipedia page using the Wikipedia API.
    
    Args:
        page_title: The title of the Wikipedia page to fetch
        
    Returns:
        The text content of the page.
    Raises:
        ValueError: If the page is not found.
    """
    page = wiki_session.page(page_title)
    
    if page.exists():
        return page.text
    raise ValueError(f"Page '{page_title}' not found")

@mcp.tool(
    annotations={
        "title": "Get Wikipedia Page Link Titles",
        "readOnlyHint": True,
        "openWorldHint": True,
    }
)
async def get_wikipedia_page_links_titles(page_title: str) -> str:
    """
    Fetches titles of all linked pages from a Wikipedia page using the Wikipedia API.
    
    Args:
        page_title: The title of the Wikipedia page to fetch links from
        
    Returns:
        A newline-separated string of linked page titles.
    Raises:
        ValueError: If the page is not found.
    """
    page = wiki_session.page(page_title)
    
    if page.exists():
        links: List[str] = [link for link in page.links.keys()]
        return "\\n".join(links)
    raise ValueError(f"Page '{page_title}' not found")

@mcp.tool(
    annotations={
        "title": "Get Wikipedia Page Link URLs",
        "readOnlyHint": True,
        "openWorldHint": True,
    }
)
async def get_wikipedia_page_links_urls(page_title: str) -> str:
    """
    Fetches URLs of all linked pages from a Wikipedia page using the Wikipedia API.
    
    Args:
        page_title: The title of the Wikipedia page to fetch links from
        
    Returns:
        A newline-separated string of linked page URLs.
    Raises:
        ValueError: If the page is not found.
    """
    page = wiki_session.page(page_title)
    
    if page.exists():
        links: List[str] = [f"https://en.wikipedia.org/wiki/{link}" for link in page.links.keys()]
        return "\\n".join(links)
    raise ValueError(f"Page '{page_title}' not found")

if __name__ == "__main__":
    # This allows running the server directly using "python server.py"
    # For development, "mcp dev server.py" is usually preferred.
    print(f"running server")
    mcp.run()
