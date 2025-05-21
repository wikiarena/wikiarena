import asyncio
import sys
import json
import logging
from rich.logging import RichHandler

from wiki_arena.config import load_config
from wiki_arena.mcp_client.client import MCPClient, create_server_params_from_config
from wiki_arena.game.game_manager import GameManager
from wiki_arena.data_models.game_models import GameConfig

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
        logging.info(f"Connected to {mcp_server_config_name}")

        # 4. Create game configuration
        game_config = GameConfig(
            start_page_title="Python (programming language)",
            target_page_title="Philosophy",
            max_steps=30,
            model_provider="random",  # We're using random selection instead of AI
            # model_provider="anthropic", # Example: uncomment to use Anthropic
            model_settings={
                # "model_name": "claude-3-haiku-20240307" # Example for Anthropic
                # "max_tokens": 1000
            }
        )

        # 5. Create and start game
        game_manager = GameManager(mcp_client)
        initial_state = await game_manager.start_game(game_config)
        logging.info(f"Game started: {initial_state.game_id}")
        logging.info(f"Current page: {initial_state.current_page.title}")
        logging.info(f"Available links: {len(initial_state.current_page.links)}")

        # 6. Play game loop
        while True:
            result = await game_manager.play_turn()
            if result:
                # Game is over
                logging.info(f"\nGame Over!")
                logging.info(f"Status: {result.status.value}")
                logging.info(f"Steps taken: {result.steps}")
                logging.info(f"Path: {' -> '.join(result.path_taken)}")
                logging.info(f"Duration: {result.duration:.2f}s")
                if result.error_message:
                    logging.error(f"Error: {result.error_message}")
                break

            # Game continues
            current_page = game_manager.state.current_page
            logging.info(f"Step {game_manager.state.steps}")
            logging.info(f"Current page: {current_page.title}")
            logging.info(f"Available links: {len(current_page.links)}")

    except Exception as e:
        logging.critical(f"An unexpected error occurred during application runtime: {e}", exc_info=True)

    finally:
        # 7. Ensure the client disconnects when the application finishes
        await mcp_client.disconnect()
        logging.info("Application shutting down.")

if __name__ == "__main__":
    asyncio.run(main())