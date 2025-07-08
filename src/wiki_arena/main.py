import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

import typer

from wiki_arena.game import Game
from wiki_arena.models import GameConfig, GameResult
from wiki_arena.storage import GameStorageService, StorageConfig
from wiki_arena.tools import get_tools
from wiki_arena.language_models import create_model
from wiki_arena.wikipedia import LiveWikiService
from wiki_arena.wikipedia.task_selector import get_random_task_async


app = typer.Typer()


@app.command()
def main(
    model_key: str = typer.Option(
        "random",
        "--model-key",
        "-m",
        help="The model key to use for the game.",
    ),
    max_steps: int = typer.Option(
        30,
        "--max-steps",
        "-s",
        help="The maximum number of steps allowed in the game.",
    ),
):
    """
    Run a Wiki Arena game from the command line.
    """
    asyncio.run(run_game_async(model_key=model_key, max_steps=max_steps))


async def run_game_async(model_key: str, max_steps: int):
    # Configure unified logging
    from wiki_arena.logging_config import setup_logging

    setup_logging(level="INFO")
    logger = logging.getLogger(__name__)

    # 2. Instantiate the wiki service
    wiki_service = LiveWikiService()
    logger.info("LiveWikiService created.")

    try:
        # 4. Select a random task
        task = await get_random_task_async()
        if not task:
            logger.error("Could not retrieve a valid task. Exiting.")
            return

        # 5. Create game configuration from the task
        # Create model using simplified system (no config needed!)
        model = create_model(model_key)

        logger.info(
            f"Using model: {model.model_config.model_name} ({model.model_config.provider})"
        )

        game_config = GameConfig(
            start_page_title=task.start_page_title,
            target_page_title=task.target_page_title,
            max_steps=max_steps,
            model=model.model_config,  # Use the model config
        )

        # 5.5. Initialize game storage service
        storage_config = StorageConfig()  # Use default configuration for now
        storage_service = GameStorageService(storage_config)
        logger.info(f"Game storage configured: {storage_config.storage_path}")

        # Fetch the start page and tools needed to initialize the game
        start_page = await wiki_service.get_page(game_config.start_page_title)
        tools = get_tools()

        # 6. Create and start game
        game = Game(
            config=game_config,
            wiki_service=wiki_service,
            language_model=model,
            start_page=start_page,
            tools=tools,
            event_bus=None,
        )
        initial_state = game.state
        logger.info(f"Game initialized: {initial_state.game_id}")
        logger.info(f"Current page: {initial_state.current_page.title}")
        logger.info(f"Available links: {len(initial_state.current_page.links)}")

        # Run the game until it's over
        logger.info("Starting game...")
        await game.run()
        final_state = game.state
        # Store game result
        try:
            game_result = GameResult.from_game_state(final_state)
            storage_success = storage_service.store_game(game_result)

            if storage_success:
                logger.info(f"Game result stored successfully")
            else:
                logger.warning(f"Failed to store game result")
        except Exception as e:
            logger.error(f"Error storing game result: {e}", exc_info=True)

        logger.info(json.dumps([msg.model_dump(mode="json") for msg in game.state.context], indent=2))

        # Print results
        logger.info("Game finished.")
        logger.info(f"Status: {final_state.status.value}")
        logger.info(f"Message: {final_state.error_message}")
        logger.info(f"Steps: {final_state.steps}")

        # Simplified path construction
        path = " -> ".join(
            [move.from_page_title for move in final_state.move_history]
            + [final_state.current_page.title]
        )
        logger.info(f"Path: {path}")

        # Calculate duration
        end_time = datetime.now()
        duration = (end_time - final_state.start_timestamp).total_seconds()
        logger.info(f"Duration: {duration:.2f}s")

    except Exception as e:
        logger.critical(
            f"An unexpected error occurred during application runtime: {e}",
            exc_info=True,
        )

    finally:
        # 8. Application shutdown
        logger.info("Application shutting down.")


if __name__ == "__main__":
    app() 