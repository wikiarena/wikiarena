from typing import List
from pathlib import Path
from pydantic import BaseModel, Field
import os

from wiki_arena.types import ErrorType

class StorageConfig(BaseModel):
    """Configuration for game result storage."""
    storage_dir: str = Field(
        default_factory=lambda: os.environ.get(
            "WIKI_ARENA_STORAGE_DIR",
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 
                "game_results"
            )
        ),
        description="Directory to store game results"
    )

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
    
    @property
    def storage_path(self) -> Path:
        """Get the storage directory as a Path object."""
        return Path(self.storage_dir)

    @property
    def jsonl_path(self) -> Path:
        """Get the full path to the JSONL file."""
        return self.storage_path / self.jsonl_filename

    @property
    def csv_path(self) -> Path:
        """Get the full path to the summary CSV file."""
        return self.storage_path / self.csv_filename 