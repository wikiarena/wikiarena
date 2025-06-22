import asyncio
import sys
import json
import logging
from rich.logging import RichHandler
from datetime import datetime

from wiki_arena.config import load_config
from wiki_arena.mcp_client.client import MCPClient, create_server_params_from_config
from wiki_arena.game.game_manager import GameManager
from wiki_arena.models import GameConfig, ModelConfig, GameResult
from wiki_arena.models import GameStatus
from wiki_arena.wikipedia.task_selector import get_random_task_async
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

    # Configure unified logging
    from wiki_arena.logging_config import setup_logging
    
    log_level_str = app_config.get("app_settings", {}).get("log_level", "INFO").upper()
    setup_logging(level=log_level_str)
    
    logging.debug("Unified logging configured.")

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

        # 4. Select a random task
        task = await get_random_task_async()
        if not task:
            print("Could not retrieve a valid task. Exiting.")
            return

        # 5. Create game configuration from the task
        model_key = "random"                   # Random baseline
        
        # Create model using simplified system (no config needed!)
        model = create_model(model_key)
        
        # You can also override settings if needed:
        # model = create_model(model_key, max_tokens=2048, temperature=0.1)
        
        logging.info(f"Using model: {model.model_config.model_name} ({model.model_config.provider})")
        logging.info(f"Model pricing: ${model.model_config.input_cost_per_1m_tokens}/1M input, ${model.model_config.output_cost_per_1m_tokens}/1M output tokens")

        game_config = GameConfig(
            start_page_title=task.start_page_title,
            target_page_title=task.target_page_title,
            max_steps=30,
            model=model.model_config  # Use the model config
        )

        # 5.5. Initialize game storage service
        storage_config = StorageConfig()  # Use default configuration for now
        storage_service = GameStorageService(storage_config)
        logging.info(f"Game storage configured: {storage_config.storage_path}")

        # 6. Create and start game
        game_manager = GameManager(mcp_client)
        initial_state = await game_manager.initialize_game(game_config)
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