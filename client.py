from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
import asyncio
import json

# Configuration for the MCP server
# Assuming the server is started with a command like `python main.py` or similar
# and is located in the 'wikipedia-mcp-server' directory.
# Adjust the command and path as necessary.
SERVER_COMMAND = "python"
SERVER_ARGS = ["server.py"]  # Or the relevant script name in wikipedia-mcp-server
SERVER_CWD = "../wikipedia-mcp-server" # Relative path to the server repo

async def run_client():
    """Initializes the MCP client and connects to the server."""
    server_params = StdioServerParameters(
        command=SERVER_COMMAND,
        args=SERVER_ARGS,
        cwd=SERVER_CWD, # Specify the working directory for the server process
        env=None,
    )

    try:
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                # Initialize the connection
                init_response = await session.initialize()
                print(f"Server initialized: {init_response.serverInfo.name} v{init_response.serverInfo.version}")

        
                tools_result = await session.list_tools()
                print("\n--- Available Tools ---")
                if tools_result.tools:
                    for tool in tools_result.tools:
                        print(f"  Name: {tool.name}")
                        if tool.description:
                            print(f"  Description: {tool.description}")
                        if tool.inputSchema:
                            print(f"  Input Schema: {json.dumps(tool.inputSchema, indent=2)}")
                        print("  ---")
                else:
                    print("  No tools available.")
                print("-----------------------\n")

                try:
                    tool_result = await session.call_tool("extract_all_wikipedia_links", {"page_title": "Python (Programming Language)"})
                    print("\n--- Tool Result ---")
                    print(f"  Is Error: {tool_result.isError}")
                    if tool_result.content:
                        print("  Content:")
                        for item in tool_result.content:
                            if isinstance(item, types.TextContent):
                                print(f"    Type: {item.type}")
                                print(f"    Text: {item.text}")
                            elif isinstance(item, types.ImageContent):
                                print(f"    Type: {item.type}")
                                print(f"    MIME Type: {item.mimeType}")
                                print("    Data: <Image Data>") # Avoid printing base64 string
                            elif isinstance(item, types.EmbeddedResource):
                                print(f"    Type: {item.type}")
                                if hasattr(item.resource, 'uri'):
                                     print(f"      Resource URI: {item.resource.uri}")
                                if hasattr(item.resource, 'mimeType'):
                                     print(f"      Resource MIME Type: {item.resource.mimeType}")
                                if isinstance(item.resource, types.TextResourceContents):
                                    print(f"      Resource Text: {item.resource.text}")
                                elif isinstance(item.resource, types.BlobResourceContents):
                                    print("      Resource Blob: <Binary Data>") # Avoid printing base64 string
                            if item.annotations:
                                print(f"    Annotations: {json.dumps(item.annotations.model_dump(), indent=2)}") # pretty print annotations
                            print("    ---")
                    else:
                        print("  No content in result.")
                    print("--------------------\n")
                except Exception as e:
                    print(f"Error calling tool: {e}")

                print("Client session finished.")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc() # Print the full traceback
        # If using Python 3.11+ and 'e' might be an ExceptionGroup
        if hasattr(e, 'exceptions'):
            print("\n--- Sub-exceptions ---")
            for i, sub_ex in enumerate(e.exceptions):
                print(f"Sub-exception {i+1}/{len(e.exceptions)}:")
                traceback.print_exception(type(sub_ex), sub_ex, sub_ex.__traceback__)
                print("---")

if __name__ == "__main__":
    asyncio.run(run_client()) 