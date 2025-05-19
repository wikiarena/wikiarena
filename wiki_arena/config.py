import json
import os
from typing import Dict, Any

def load_config(filepath: str = "config.json") -> Dict[str, Any]:
    """Loads configuration from a JSON file."""
    # Construct absolute path relative to the project root
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, filepath)

    if not os.path.exists(config_path):
        # Handle cases where config might be elsewhere in deployment
        print(f"Warning: Config file not found at {config_path}. Trying current directory.")
        config_path = filepath # Try current directory

    if not os.path.exists(config_path):
         raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, 'r') as f:
        return json.load(f)
