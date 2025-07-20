import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from wiki_arena.language_models.language_model import LanguageModel
from .config import OpenRouterModelConfig, OpenRouterModelsData, Pricing, TopProvider
from .model import OpenRouterLanguageModel

# Global cache for the models data, mapping model_id to its config.
_MODELS_CONFIG_CACHE: Optional[Dict[str, OpenRouterModelConfig]] = None


def _load_and_cache_models() -> Dict[str, OpenRouterModelConfig]:
    """Load and cache OpenRouter models configuration from JSON file."""
    global _MODELS_CONFIG_CACHE
    if _MODELS_CONFIG_CACHE:
        return _MODELS_CONFIG_CACHE

    # Correct path to openrouter_models.json at the project root
    models_path = Path(__file__).parent.parent.parent.parent / "openrouter_models.json"

    if not models_path.exists():
        raise FileNotFoundError(
            f"{models_path} not found. Please run the script to fetch the models first."
        )

    with open(models_path, "r") as f:
        data = json.load(f)
        
        # Filter for models that support tool use
        tool_supported_models = [
            m for m in data["data"] 
            if m.get("supported_parameters") and "tools" in m["supported_parameters"]
        ]
        
        validated_models = OpenRouterModelsData.model_validate({"data": tool_supported_models})
        
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
