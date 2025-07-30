import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from wiki_arena.language_models.language_model import LanguageModel
from .config import OpenRouterModelConfig, OpenRouterModelsData, Pricing, TopProvider
from .model import OpenRouterLanguageModel

# Global cache for the models data, mapping model_id to its config.
_MODELS_CONFIG_CACHE: Optional[Dict[str, OpenRouterModelConfig]] = None


def _get_cache_path() -> Path:
    """Intelligent cache path resolution for different environments."""
    # Priority order for cache locations:
    cache_locations = [
        # 1. Project root (relative to this file)
        Path(__file__).parent.parent.parent.parent / "openrouter_models.json",
        # 2. EB deployment directory (if running in EB)
        Path("/var/app/current/openrouter_models.json"),
        # 3. System temp directory (fallback)
        Path("/tmp/openrouter_models.json"),
    ]
    
    # Return the first location that exists, or the most appropriate one
    for location in cache_locations:
        if location.exists():
            return location
    
    # If none exist, prefer project root for development, temp for production
    if os.getenv("AWS_EXECUTION_ENV"):  # Running in AWS
        return Path("/tmp/openrouter_models.json")
    else:
        return Path(__file__).parent.parent.parent.parent / "openrouter_models.json"


def _load_and_cache_models() -> Dict[str, OpenRouterModelConfig]:
    """Load and cache OpenRouter models configuration from JSON file or API."""
    global _MODELS_CONFIG_CACHE
    if _MODELS_CONFIG_CACHE:
        return _MODELS_CONFIG_CACHE

    cache_path = _get_cache_path()
    
    # Try to load from cache file first
    if cache_path.exists():
        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
            print(f"Loaded OpenRouter models from cache: {cache_path}")
        except (json.JSONDecodeError, IOError) as e:
            print(f"Failed to load cache from {cache_path}: {e}")
            data = None
    else:
        data = None
    
    # If cache doesn't exist or is invalid, fetch from API
    if not data:
        try:
            import requests
            print("Fetching OpenRouter models from API...")
            response = requests.get("https://openrouter.ai/api/v1/models?supported_parameters=tools")
            response.raise_for_status()
            data = response.json()
            
            # Cache for next time (ensure directory exists)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w") as f:
                json.dump(data, f, indent=2)
            print(f"Cached OpenRouter models to: {cache_path}")
            
        except Exception as e:
            raise RuntimeError(f"Failed to fetch OpenRouter models: {e}")
    
    # API already filtered for supported_parameters=tools, so we can use all returned models
    validated_models = OpenRouterModelsData.model_validate(data)
    
    models_dict = {model.id: model for model in validated_models.data}
    
    # Add the special-cased random model
    random_config = _get_random_model_config()
    models_dict[random_config.id] = random_config
    
    _MODELS_CONFIG_CACHE = models_dict
    return _MODELS_CONFIG_CACHE


def _get_random_model_config() -> OpenRouterModelConfig:
    """Helper to create the config for the special-cased random model."""
    return OpenRouterModelConfig(
        id="wikiarena/random",
        name="Randomly Choose Links",
        created=0, # easter egg: last on model selector list
        description="A model that selects links randomly.",
        # A Python string of length ~8 * 1024**3 bytes (8 GiB) would be about 8,589,934,592 characters,
        # since each character in a Python 3 str is at least 1 byte (UTF-8, ASCII), but can be more.
        context_length=8_589_934_592,
        pricing=Pricing(prompt=0.0, completion=0.0, request=0.0, image=0.0),
        top_provider=TopProvider(is_moderated=False),
    )


def create_openrouter_model(
    model_id: str, settings_override: Optional[Dict[str, Any]] = None
) -> LanguageModel:
    """
    Factory function to create a language model instance.

    Handles special cases like the 'random' model, otherwise loads
    configuration from the OpenRouter models file.
    """
    from wiki_arena.language_models.random_model import RandomModel # internal to prevent circular import
    
    # The random model is not in the JSON file, so it's handled separately
    # but its config is still available via get_openrouter_model_config
    if model_id == "wikiarena/random":
        random_config = get_openrouter_model_config(model_id)
        if not random_config:
            # This should not happen if the caching is working correctly
            raise ValueError("Could not find configuration for random model.")
        if settings_override:
            # Create a copy to avoid modifying the cached version
            random_config = random_config.model_copy(deep=True)
            random_config.settings.update(settings_override)
        return RandomModel(config=random_config)

    model_config_data = get_openrouter_model_config(model_id)

    if not model_config_data:
        raise ValueError(f"Model with id '{model_id}' not found in openrouter_models.json")

    # Create a copy to avoid modifying the cached version
    config = model_config_data.model_copy(deep=True)
    
    # Apply any runtime overrides
    if settings_override:
        config.settings.update(settings_override)

    return OpenRouterLanguageModel(config=config)

def get_openrouter_model_config(model_id: str) -> Optional[OpenRouterModelConfig]:
    """Returns the configuration for a single OpenRouter model."""
    all_models = _load_and_cache_models()
    return all_models.get(model_id)

def list_openrouter_models() -> List[OpenRouterModelConfig]:
    """
    Returns a list of all available OpenRouter model configurations,
    including our special-cased 'random' model.
    """
    all_models = _load_and_cache_models()
    return list(all_models.values())

__all__ = ["create_openrouter_model", "list_openrouter_models", "get_openrouter_model_config", "OpenRouterLanguageModel", "OpenRouterModelConfig"] 
