from mcp.server.fastmcp import FastMCP
from mcp import types
import httpx
import json
import urllib.parse
from typing import List, Union

mcp = FastMCP("wiki-arena")

async def fetch_page_with_all_links(page_title: str, include_all_namespaces: bool = True) -> dict:
    """
    Fetch ALL links from a Wikipedia page using pagination.
    Returns raw links exactly as they appear, with no filtering or processing.
    """
    base_url = "https://en.wikipedia.org/w/api.php"
    
    all_links = []
    plcontinue = None
    page_info = None
    
    while True:
        params = {
            "action": "query",
            "format": "json",
            "prop": "info|links",
            "titles": page_title,
            "pllimit": "500",  # Wikipedia API maximum per request
            "inprop": "url",
            "redirects": "1",
            "formatversion": "2"
        }
        
        # Only filter namespaces if explicitly requested
        if not include_all_namespaces:
            params["plnamespace"] = "0"  # Main namespace only
            
        if plcontinue:
            params["plcontinue"] = plcontinue
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()
        
        if "error" in data:
            raise ValueError(f"Wikipedia API error: {data['error']['info']}")
            
        pages = data.get("query", {}).get("pages", [])
        if not pages:
            raise ValueError(f"Page not found: {page_title}")
            
        page = pages[0]
        if "missing" in page:
            raise ValueError(f"Page does not exist: {page_title}")
        
        # Store page info on first iteration
        if page_info is None:
            page_info = {
                "title": page["title"],
                "pageid": page.get("pageid"),
                "url": page.get("fullurl", f"https://en.wikipedia.org/wiki/{urllib.parse.quote(page['title'])}")
            }
        
        # Add links from this batch - preserve exact order, no deduplication
        links_batch = page.get("links", [])
        for link in links_batch:
            all_links.append(link["title"])
        
        # Check for more links
        continue_data = data.get("continue", {})
        if "plcontinue" in continue_data:
            plcontinue = continue_data["plcontinue"]
        else:
            break
    
    return {
        "title": page_info["title"],
        "url": page_info["url"],
        "pageid": page_info["pageid"],
        "links": all_links,
        "total_links": len(all_links)
    }

@mcp.tool()
async def navigate(page: str) -> List[Union[types.TextContent, types.EmbeddedResource]]:
    """
    Navigate to a Wikipedia page and get ALL available links.
    
    This tool is designed for the Wikipedia game where you navigate from page to page
    by clicking links. It returns every clickable link exactly as it appears on the page.
    
    Args:
        page: Wikipedia page title to navigate to
        include_all_namespaces: If True, include ALL links (default). If False, only main articles
    
    Returns:
        Text summary and structured data with all links
    """
    try:
        result = await fetch_page_with_all_links(page, include_all_namespaces=True)
        
        # Format links for display - preserve exact order
        if result["links"]:
            links_display = "\n".join(result["links"])
            summary = f"""🎯 Current Page: {result['title']}
🔗 Total Links: {result['total_links']}

Available Links:
{links_display}"""
        else:
            summary = f"🎯 Current Page: {result['title']}\n🔗 No links found on this page."
        
        return [
            types.TextContent(type="text", text=summary),
            types.EmbeddedResource(
                type="resource",
                resource=types.TextResourceContents(
                    uri=f"wikipedia://{urllib.parse.quote(result['title'])}",
                    mimeType="application/json",
                    text=json.dumps(result, ensure_ascii=False, indent=2)
                )
            )
        ]
        
    except Exception as e:
        return [types.TextContent(type="text", text=f"❌ Navigation Error: {str(e)}")]

if __name__ == "__main__":
    print("Starting simplified Wiki Arena MCP server...")
    mcp.run()
