import json
import logging
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any

from wiki_arena.types import (
    GameResult, GameConfig, ModelConfig, GameStatus, Task
)
from wiki_arena.storage import StorageConfig, GameRepository
from wiki_arena.ratings import LeaderboardGenerator

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# Define a temporary directory for test data
TEMP_TEST_DIR = Path("./temp_leaderboard_test_data")

MODEL_ALPHA = "model_alpha"
MODEL_BETA = "model_beta"
MODEL_GAMMA = "model_gamma"

def create_mock_game_result(
    game_id: str,
    start_page: str,
    target_page: str,
    model_provider: str,
    model_name: str,
    status: GameStatus,
    steps: int,
    start_time: datetime,
    end_time: datetime
) -> Dict[str, Any]:
    """Helper to create a GameResult-like dictionary for JSON serialization."""
    
    mock_game_config = GameConfig(
        start_page_title=start_page,
        target_page_title=target_page,
        max_steps=30
    )

    mock_model_config = ModelConfig(
        provider=model_provider,
        model_name=model_name,
        input_cost_per_1m_tokens=0.25, # Dummy value
        output_cost_per_1m_tokens=1.25 # Dummy value
    )

    # Create a Task to verify its ID if needed for debugging, not directly stored in GameResult dict
    # task_for_id_check = Task(start_page_title=start_page, target_page_title=target_page)
    # logger.debug(f"Task ID for {start_page}->{target_page}: {task_for_id_check.task_id}")

    result_dict = {
        "game_id": game_id,
        "config": mock_game_config.model_dump(mode='json'), # Serialize GameConfig
        "model": mock_model_config.model_dump(mode='json'), # Serialize ModelConfig
        "status": status.value,
        "steps": steps,
        "path_taken": [start_page, "...", target_page if status == GameStatus.WON else "some_other_page"],
        "moves": [], # Empty for simplicity
        "start_timestamp": start_time.isoformat(),
        "end_timestamp": end_time.isoformat(),
        "error_message": None if status == GameStatus.WON else "Max steps reached",
        "total_input_tokens": steps * 10, # Dummy value
        "total_output_tokens": steps * 5,  # Dummy value
        "total_tokens": steps * 15,      # Dummy value
        "total_estimated_cost_usd": steps * 0.0001, # Dummy value
        "total_api_time_ms": steps * 100.0, # Dummy value
        "average_response_time_ms": 100.0,  # Dummy value
        "api_call_count": steps,
        "metadata": {
            "model_name": model_name,
            "model_provider": model_provider,
            # ... other metadata GameResult.from_game_state might generate
        }
    }
    # To be fully compliant if GameResult.model_validate_json expects these from GameState conversion:
    # We are constructing something that GameResult.model_validate_json can parse.
    # The metadata part is what GameResult.from_game_state normally populates.
    # For this direct construction, we ensure model_key is there.
    return result_dict

def setup_mock_data_file(file_path: Path):
    """Creates a mock games.jsonl file."""
    mock_games_data = []
    now = datetime.now(timezone.utc)

    # Task 1: Apple to Banana
    mock_games_data.append(create_mock_game_result(
        "game1_alpha_T1", "Apple", "Banana", "test_provider", MODEL_ALPHA, 
        GameStatus.WON, 5, now, now
    ))
    mock_games_data.append(create_mock_game_result(
        "game2_beta_T1", "Apple", "Banana", "test_provider", MODEL_BETA,
        GameStatus.WON, 10, now, now
    ))
    mock_games_data.append(create_mock_game_result(
        "game3_gamma_T1", "Apple", "Banana", "test_provider", MODEL_GAMMA,
        GameStatus.LOST_MAX_STEPS, 30, now, now
    ))

    # Task 2: Cat to Dog
    mock_games_data.append(create_mock_game_result(
        "game4_alpha_T2", "Cat", "Dog", "test_provider", MODEL_ALPHA,
        GameStatus.WON, 3, now, now
    ))
    mock_games_data.append(create_mock_game_result(
        "game5_beta_T2", "Cat", "Dog", "test_provider", MODEL_BETA,
        GameStatus.WON, 3, now, now # Tie with Alpha on this task
    ))
    mock_games_data.append(create_mock_game_result(
        "game6_gamma_T2", "Cat", "Dog", "test_provider", MODEL_GAMMA,
        GameStatus.WON, 8, now, now
    ))
    
    # Task 3: Unrelated, played by one model to ensure it appears
    mock_games_data.append(create_mock_game_result(
        "game7_alpha_T3", "Xylophone", "Zebra", "test_provider", MODEL_ALPHA,
        GameStatus.WON, 2, now, now
    ))

    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        for game_data in mock_games_data:
            # Validate that GameResult can parse this dict to catch issues early
            try:
                _ = GameResult.model_validate(game_data) # Use model_validate for dicts
            except Exception as e:
                logger.error(f"Mock data validation failed for {game_data.get('game_id')}: {e}")
                logger.error(f"Data: {game_data}")
                raise
            f.write(json.dumps(game_data) + '\n')
    logger.info(f"Mock data written to {file_path}")

def run_leaderboard_test():
    logger.info("Starting leaderboard integration test...")
    jsonl_file_path = TEMP_TEST_DIR / "mock_games.jsonl"

    try:
        # 1. Setup mock data
        setup_mock_data_file(jsonl_file_path)

        # 2. Setup StorageConfig and GameRepository
        class TestStorageConfig(StorageConfig):
            storage_dir: str = str(TEMP_TEST_DIR)
            jsonl_filename: str = "mock_games.jsonl"
            # Disable other storage types for this test if they try to write
            enable_summary_csv: bool = False 

        test_storage_config = TestStorageConfig()
        game_repo = GameRepository(storage_config=test_storage_config)

        # Verify repository loading
        loaded_games = game_repo.get_all_games()
        logger.info(f"GameRepository loaded {len(loaded_games)} games.")
        assert len(loaded_games) == 7, f"Expected 7 games, loaded {len(loaded_games)}"

        # 3. Initialize LeaderboardGenerator
        leaderboard_gen = LeaderboardGenerator(game_repo)

        # 4. Generate Elo Ratings
        logger.info("Generating Elo ratings...")
        elo_ratings = leaderboard_gen.generate_elo_ratings()

        logger.info("--- Calculated Elo Ratings ---")
        if elo_ratings:
            for model_key, elo in sorted(elo_ratings.items(), key=lambda item: item[1], reverse=True):
                logger.info(f"  {model_key}: {elo}")
        else:
            logger.warning("No Elo ratings generated.")

        logger.info("--- Win Matrix ---")
        win_matrix = leaderboard_gen.get_current_win_matrix()
        for model, opponents in win_matrix.items():
            logger.info(f"  Model {model}:")
            for opponent, wins in opponents.items():
                logger.info(f"    vs {opponent}: {wins} wins")
        
        # Basic Assertions (adapt based on expected outcomes)
        assert MODEL_ALPHA in elo_ratings
        assert MODEL_BETA in elo_ratings
        assert MODEL_GAMMA in elo_ratings
        
        if elo_ratings.get(MODEL_ALPHA) and elo_ratings.get(MODEL_BETA) and elo_ratings.get(MODEL_GAMMA):
            assert elo_ratings[MODEL_ALPHA] > elo_ratings[MODEL_BETA], "Alpha should beat Beta"
            assert elo_ratings[MODEL_BETA] > elo_ratings[MODEL_GAMMA], "Beta should beat Gamma"
        else:
            logger.warning("Could not perform all Elo assertions due to missing models in ratings.")

        logger.info("Leaderboard integration test completed successfully.")

    except Exception as e:
        logger.error(f"An error occurred during the leaderboard test: {e}", exc_info=True)
    finally:
        # 5. Cleanup
        if TEMP_TEST_DIR.exists():
            logger.info(f"Cleaning up temporary test directory: {TEMP_TEST_DIR}")
            # shutil.rmtree(TEMP_TEST_DIR) # Use with caution or if in a CI environment
            pass # For manual inspection, leave the files; otherwise, uncomment rmtree

if __name__ == "__main__":
    run_leaderboard_test() 