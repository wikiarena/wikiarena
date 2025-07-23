import json
import logging
from pathlib import Path
from typing import List, Dict, Optional

from wiki_arena.types import GameResult, Task
from .storage_config import StorageConfig

class GameRepository:
    """Handles retrieving and caching game results from storage."""

    def __init__(self, storage_config: StorageConfig):
        self.storage_config = storage_config
        self.logger = logging.getLogger(__name__)
        self._cache: Dict[str, GameResult] = {}
        self._load_cache()

    def _load_cache(self):
        """Load all games from the JSONL file into the in-memory cache."""
        jsonl_file = self.storage_config.jsonl_path
        if not jsonl_file.exists():
            self.logger.info(f"Game data file not found: {jsonl_file}. Cache will be empty.")
            return

        try:
            with open(jsonl_file, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    try:
                        game = GameResult.model_validate_json(line)
                        self._cache[game.game_id] = game
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Error decoding JSON on line {i+1} in {jsonl_file}: {e} - Line: '{line.strip()}'")
                    except Exception as e: # Catch Pydantic validation errors or other issues
                        self.logger.error(f"Error processing game data on line {i+1} in {jsonl_file}: {e} - Line: '{line.strip()}'")
            self.logger.info(f"Successfully loaded {len(self._cache)} games into cache from {jsonl_file}.")
        except Exception as e:
            self.logger.error(f"Failed to load game data from {jsonl_file}: {e}")

    def get_all_games(self) -> List[GameResult]:
        """Get all stored games from the cache."""
        return list(self._cache.values())

    def get_game_by_id(self, game_id: str) -> Optional[GameResult]:
        """Get a specific game by its ID from the cache."""
        return self._cache.get(game_id)

    def get_games_by_task_id(self, task_id: str) -> List[GameResult]:
        """Get all games for a specific task ID from the cache."""
        matching_games = []
        for game in self._cache.values():
            # Create a Task object from the game's config to get its task_id
            current_task = Task(
                start_page_title=game.config.start_page_title,
                target_page_title=game.config.target_page_title
            )
            if current_task.task_id == task_id:
                matching_games.append(game)
        return matching_games
    
    def refresh_cache(self):
        """Clears and reloads the cache from the storage file."""
        self.logger.info("Refreshing game cache...")
        self._cache.clear()
        self._load_cache()
