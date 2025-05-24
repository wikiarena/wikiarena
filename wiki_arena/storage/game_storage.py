import json
import csv
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from wiki_arena.data_models.game_models import GameResult, GameStatus, ErrorType
from .storage_config import StorageConfig


class GameStorageService:
    """Service for storing game results in various formats."""
    
    def __init__(self, config: Optional[StorageConfig] = None):
        self.config = config or StorageConfig()
        self.logger = logging.getLogger(__name__)
        
    def should_store_game(self, game_result: GameResult) -> bool:
        """Determine if a game should be stored based on configuration."""
        if self.config.store_all_games:
            return True
            
        # Check specific game outcomes
        if game_result.status == GameStatus.WON and self.config.store_won_games:
            return True
        elif game_result.status == GameStatus.LOST_MAX_STEPS and self.config.store_lost_games:
            return True
        elif game_result.status in [GameStatus.ERROR, GameStatus.LOST_INVALID_MOVE] and self.config.store_error_games:
            # Check for excluded error types
            if game_result.moves:
                game_error_types = {move.error.type for move in game_result.moves if move.error}
                excluded_types = set(self.config.excluded_error_types)
                if game_error_types.intersection(excluded_types):
                    return False
            return True
            
        return False
    
    def _ensure_storage_directory(self):
        """Create storage directory if it doesn't exist."""
        storage_path = self.config.get_storage_path()
        storage_path.mkdir(parents=True, exist_ok=True)
        
    def store_game_jsonl(self, game_result: GameResult) -> bool:
        """Store complete game result as a JSONL line."""
        if not self.config.enable_jsonl:
            return True
            
        try:
            self._ensure_storage_directory()
            jsonl_path = self.config.get_jsonl_path()
            
            # Convert to JSON and append to file
            json_line = game_result.model_dump_json()
            
            with open(jsonl_path, 'a', encoding='utf-8') as f:
                f.write(json_line + '\n')
                
            self.logger.debug(f"Stored game {game_result.game_id} to JSONL: {jsonl_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to store game {game_result.game_id} to JSONL: {e}")
            return False
    
    def store_game_csv_summary(self, game_result: GameResult) -> bool:
        """Store game summary as CSV row."""
        if not self.config.enable_summary_csv:
            return True
            
        try:
            self._ensure_storage_directory()
            csv_path = self.config.get_csv_path()
            
            # Check if file exists to determine if we need headers
            file_exists = csv_path.exists()
            
            # Prepare summary data
            summary_data = {
                'game_id': game_result.game_id,
                'start_timestamp': game_result.start_timestamp.isoformat(),
                'end_timestamp': game_result.end_timestamp.isoformat(),
                'duration_seconds': game_result.duration,
                'status': game_result.status.value,
                'steps': game_result.steps,
                'model_provider': game_result.config.model.provider,
                'model_name': game_result.config.model.model_name,
                'start_page': game_result.config.start_page_title,
                'target_page': game_result.config.target_page_title,
                'max_steps': game_result.config.max_steps,
                'path_length': len(game_result.path_taken),
                'successful_moves': game_result.metadata.get('successful_moves', 0),
                'failed_moves': game_result.metadata.get('failed_moves', 0),
                'target_reached': game_result.metadata.get('target_reached', False),
                'error_message': game_result.error_message or '',
                'error_types': ','.join(game_result.metadata.get('error_types', [])),
                'final_page_links': game_result.metadata.get('links_on_final_page', 0),
                'path_taken': ' -> '.join(game_result.path_taken)
            }
            
            with open(csv_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=summary_data.keys())
                
                # Write header if file is new
                if not file_exists:
                    writer.writeheader()
                    
                writer.writerow(summary_data)
                
            self.logger.debug(f"Stored game {game_result.game_id} summary to CSV: {csv_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to store game {game_result.game_id} summary to CSV: {e}")
            return False
    
    def store_game(self, game_result: GameResult) -> bool:
        """Store a game result using all enabled formats."""
        if not self.should_store_game(game_result):
            self.logger.debug(f"Game {game_result.game_id} filtered out by storage configuration")
            return True
            
        jsonl_success = self.store_game_jsonl(game_result)
        csv_success = self.store_game_csv_summary(game_result)
        
        success = jsonl_success and csv_success
        
        if success:
            self.logger.info(f"Successfully stored game {game_result.game_id} ({game_result.status.value})")
        else:
            self.logger.warning(f"Partial storage failure for game {game_result.game_id}")
            
        return success 