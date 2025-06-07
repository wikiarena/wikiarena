import asyncio
import sys
import json
import logging
from rich.logging import RichHandler
from datetime import datetime

from wiki_arena.config import load_config
from wiki_arena.mcp_client.client import MCPClient, create_server_params_from_config
from wiki_arena.game.game_manager import GameManager
from wiki_arena.data_models.game_models import GameConfig, ModelConfig, GameResult
from wiki_arena.data_models.game_models import GameStatus
from wiki_arena.wikipedia.page_selector import get_random_page_pair_async
from wiki_arena.storage import GameStorageService, StorageConfig
from wiki_arena.language_models import create_model

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

        # 4. Generate random page pair for the game with efficient validation
        logging.info("Generating random Wikipedia page pair...")
        
        # Use new page selector with validation enabled by default
        page_pair = await get_random_page_pair_async()
        
        if not page_pair:
            logging.error("Failed to generate random page pair. Exiting.")
            sys.exit(1)
        
        logging.info(f"Selected page pair: '{page_pair.start_page}' -> '{page_pair.target_page}'")

        # 5. Create game configuration with the selected pages
        # model_key = "claude-3-haiku-20240307"  # Use the new full model name
        # model_key = "gpt-4o-mini-2024-07-18"  # OpenAI's affordable model
        model_key = "random"                   # Random baseline
        
        # Create model using simplified system (no config needed!)
        model = create_model(model_key)
        
        # You can also override settings if needed:
        # model = create_model(model_key, max_tokens=2048, temperature=0.1)
        
        logging.info(f"Using model: {model.model_config.model_name} ({model.model_config.provider})")
        logging.info(f"Model pricing: ${model.model_config.input_cost_per_1m_tokens}/1M input, ${model.model_config.output_cost_per_1m_tokens}/1M output tokens")

        game_config = GameConfig(
            start_page_title=page_pair.start_page,
            target_page_title=page_pair.target_page,
            max_steps=30,
            model=model.model_config  # Use the model config
        )

        # 5.5. Initialize game storage service
        storage_config = StorageConfig()  # Use default configuration for now
        storage_service = GameStorageService(storage_config)
        logging.info(f"Game storage configured: {storage_config.get_storage_path()}")

        # 6. Create and start game
        game_manager = GameManager(mcp_client)
        initial_state = await game_manager.start_game(game_config)
        logging.info(f"Game started: {initial_state.game_id}")
        logging.info(f"Current page: {initial_state.current_page.title}")
        logging.info(f"Available links: {len(initial_state.current_page.links)}")

        # 7. Play game loop
        while True:
            game_over = await game_manager.play_turn()
            if game_over:
                # Game is over, access state directly for details
                game_state = game_manager.state
                logging.info(f"\nGame Over!")
                logging.info(f"Status: {game_state.status.value}")
                logging.info(f"Steps taken: {game_state.steps}")
                
                # Simplified path construction
                path_taken = []
                if not game_state.move_history:
                    # Game ended on the start page (e.g., 0-step win, or error before first move)
                    path_taken.append(game_state.config.start_page_title)
                else:
                    for move in game_state.move_history:
                        path_taken.append(move.from_page_title)
                    
                    # If the game was won, the final page in the path is the target page.
                    if game_state.status == GameStatus.WON:
                        path_taken.append(game_state.config.target_page_title)

                logging.info(f"Path: {' -> '.join(path_taken)}")

                # Calculate duration
                end_time = datetime.now()
                duration = (end_time - game_state.start_timestamp).total_seconds()
                logging.info(f"Duration: {duration:.2f}s")
                
                if game_state.error_message:
                    # Error_message now directly stores outcome or error
                    if game_state.status == GameStatus.ERROR or game_state.status == GameStatus.LOST_INVALID_MOVE or game_state.status == GameStatus.LOST_MAX_STEPS:
                        logging.error(f"Outcome: {game_state.error_message}")
                    else: # e.g. WON status, error_message contains success message
                        logging.info(f"Outcome: {game_state.error_message}")
                
                # 7.5. Store game result
                try:
                    game_result = GameResult.from_game_state(game_state)
                    storage_success = storage_service.store_game(game_result)
                    
                    if storage_success:
                        logging.info(f"Game result stored successfully")
                    else:
                        logging.warning(f"Failed to store game result")
                        
                except Exception as e:
                    logging.error(f"Error storing game result: {e}", exc_info=True)
                
                break

            # Game continues
            current_page = game_manager.state.current_page
            logging.info(f"Step {game_manager.state.steps}")
            logging.info(f"Current page: {current_page.title}")
            logging.info(f"Available links: {len(current_page.links)}")

    except Exception as e:
        logging.critical(f"An unexpected error occurred during application runtime: {e}", exc_info=True)

    finally:
        # 8. Ensure the client disconnects when the application finishes
        await mcp_client.disconnect()
        logging.info("Application shutting down.")

if __name__ == "__main__":
    asyncio.run(main())