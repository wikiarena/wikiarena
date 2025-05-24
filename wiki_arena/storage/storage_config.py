from typing import List
from pathlib import Path
from pydantic import BaseModel, Field

from wiki_arena.data_models.game_models import ErrorType


class StorageConfig(BaseModel):
    """Configuration for game result storage."""
    storage_dir: str = Field("./game_results", description="Directory to store game results")
    store_all_games: bool = Field(True, description="Whether to store all games regardless of outcome")
    
    # When store_all_games=False, specify what to keep
    store_won_games: bool = Field(True, description="Store games that reached the target")
    store_lost_games: bool = Field(True, description="Store games that failed due to max steps")
    store_error_games: bool = Field(True, description="Store games that failed due to errors")
    
    # Fine-grained error filtering (when store_error_games=True)
    excluded_error_types: List[ErrorType] = Field(default_factory=list, description="Error types to exclude from storage")
    
    # Output formats
    enable_jsonl: bool = Field(True, description="Store complete game data as JSONL")
    enable_summary_csv: bool = Field(True, description="Generate summary CSV for quick analysis")
    
    # File naming
    jsonl_filename: str = Field("games.jsonl", description="Name of the JSONL file")
    csv_filename: str = Field("games_summary.csv", description="Name of the summary CSV file")
    
    def get_storage_path(self) -> Path:
        """Get the storage directory as a Path object."""
        return Path(self.storage_dir)
    
    def get_jsonl_path(self) -> Path:
        """Get the full path to the JSONL file."""
        return self.get_storage_path() / self.jsonl_filename
    
    def get_csv_path(self) -> Path:
        """Get the full path to the summary CSV file."""
        return self.get_storage_path() / self.csv_filename 