import asyncio
import sys
import json
import logging
from rich.logging import RichHandler

from wiki_arena.config import load_config
from wiki_arena.mcp_client.client import MCPClient, create_server_params_from_config

async def main():
    # 1. Load configuration
    try:
        app_config = load_config()
    except FileNotFoundError as e:
        print(f"CRITICAL: Error loading configuration: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"CRITICAL: Error parsing configuration file: {e}", file=sys.stderr)
        sys.exit(1)

    # Configure logging using RichHandler
    log_level_str = app_config.get("app_settings", {}).get("log_level", "INFO").upper()
    numeric_log_level = getattr(logging, log_level_str, logging.INFO)

    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_log_level)

    # Remove any existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create RichHandler
    rich_handler = RichHandler(
        level=numeric_log_level,
        show_time=True,
        show_level=True,
        show_path=True,
        enable_link_path=True,
        rich_tracebacks=True,
        markup=True,
        log_time_format="[%m/%d/%y %H:%M:%S]"
    )

    # Create a formatter to include the logger name with the message, similar to your example
    log_format_string = "%(name)s: %(message)s"
    formatter = logging.Formatter(log_format_string)
    rich_handler.setFormatter(formatter)

    # Add the RichHandler to the root logger
    root_logger.addHandler(rich_handler)

    logging.debug("Rich logging configured.")

    # 2. Get the configuration for the specific server we want to use
    # TODO(hunter): make this a sysarg or config arg for default server
    mcp_server_config_name = "stdio_mcp_server"
    try:
        server_config = app_config['mcp_servers'][mcp_server_config_name]
        server_params = create_server_params_from_config(server_config.get("transport", {}))
    except (ValueError, TypeError, KeyError) as e:
        logging.error(f"Error in server configuration for '{mcp_server_config_name}': {e}", exc_info=True)
        sys.exit(1)

    # 3. Instantiate and connect the MCP client
    mcp_client = MCPClient()

    try:
        await mcp_client.connect(server_params)

        # 4. Now the client is connected. You can pass the mcp_client
        #    instance to your core application logic or use it directly here.
        #    For a simple app, you might use it directly:

        logging.info(f"Connected to {mcp_server_config_name}. Available actions:")

        # Example: List tools and call one
        tools_response = await mcp_client.list_tools()
        if tools_response and tools_response.tools:
            logging.info("Available Tools:")
            for tool in tools_response.tools:
                logging.info(f"- {tool.name}: {tool.description}")

            # Example: Call a specific tool if it exists
            tool_to_call = "get_wikipedia_page_links_titles" # Replace with a tool your server actually has
            if any(tool.name == tool_to_call for tool in tools_response.tools):
                 try:
                     result = await mcp_client.call_tool(tool_to_call, {"page_title": "Python (programming language)"})
                     logging.info(f"\nResult of '{tool_to_call}': {result.content[0].text}")
                 except Exception as e:
                     logging.error(f"Error calling tool '{tool_to_call}': {e}", exc_info=True)
            else:
                logging.warning(f"\nTool '{tool_to_call}' not found on server.")

        else:
            logging.info("No tools available on this server.")


    except Exception as e:
        logging.critical(f"An unexpected error occurred during application runtime: {e}", exc_info=True)

    finally:
        # 5. Ensure the client disconnects when the application finishes or an error occurs
        await mcp_client.disconnect()
        logging.info("Application shutting down.")


if __name__ == "__main__":
    asyncio.run(main())