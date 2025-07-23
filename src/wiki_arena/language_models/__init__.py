# Simplified language model creation
import json
import os
from pathlib import Path
from typing import Dict, Type, Any, Optional
from .language_model import (
    LanguageModel,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from .random_model import RandomModel
from .anthropic_model import AnthropicModel
from .openai_model import OpenAIModel
from wiki_arena.types import ModelConfig

# Simple provider mapping
PROVIDERS: Dict[str, Type[LanguageModel]] = {
    "anthropic": AnthropicModel,
    "openai": OpenAIModel,
    "random": RandomModel
}

def _load_models_config() -> Dict[str, Any]:
    """Load models configuration from models.json file."""
    # Try current directory first, then project root
    possible_paths = [
        Path("models.json"),
        Path(__file__).parent.parent.parent / "models.json"
    ]
    
    for models_path in possible_paths:
        if models_path.exists():
            with open(models_path, 'r') as f:
                return json.load(f)
    
    raise FileNotFoundError(
        "models.json not found. Please ensure models.json exists in the project root."
    )

def create_model(model_key: str, **overrides) -> LanguageModel:
    """
    Create a language model instance from models.json.
    
    Args:
        model_key: Key in models.json (e.g., "claude-3-5-haiku-20241022")
        **overrides: Optional setting overrides (e.g., max_tokens=2048)
    
    Returns:
        Configured LanguageModel instance
    
    Example:
        model = create_model("claude-3-5-haiku-20241022")
        model = create_model("gpt-4o-mini-2024-07-18", max_tokens=2048)
    """
    models_config = _load_models_config()
    
    if model_key not in models_config:
        available = list(models_config.keys())
        raise ValueError(f"Model '{model_key}' not found. Available: {available}")
    
    model_def = models_config[model_key]
    provider = model_def["provider"]
    
    if provider not in PROVIDERS:
        available_providers = list(PROVIDERS.keys())
        raise ValueError(f"Unknown provider '{provider}'. Available: {available_providers}")
    
    # Merge default settings with overrides
    settings = model_def["default_settings"].copy()
    settings.update(overrides)
    
    # Create ModelConfig - use the key as the model_name
    model_config = ModelConfig(
        provider=provider,
        model_name=model_key,  # Use the key as the model name
        input_cost_per_1m_tokens=model_def["input_cost_per_1m_tokens"],
        output_cost_per_1m_tokens=model_def["output_cost_per_1m_tokens"],
        settings=settings
    )
    
    # Create and return model instance
    provider_class = PROVIDERS[provider]
    return provider_class(model_config)

def list_available_models() -> Dict[str, Dict[str, Any]]:
    """List all available models from models.json."""
    return _load_models_config()

def get_model_info(model_key: str) -> Dict[str, Any]:
    """Get display information for a specific model."""
    models_config = _load_models_config()
    
    if model_key not in models_config:
        return {"error": f"Model '{model_key}' not found"}
    
    model_def = models_config[model_key]
    return {
        "key": model_key,
        "display_name": model_def.get("display_name", model_key),
        "provider": model_def["provider"],
        "description": model_def.get("description", "No description"),
        "input_cost": f"${model_def['input_cost_per_1m_tokens']}/1M tokens",
        "output_cost": f"${model_def['output_cost_per_1m_tokens']}/1M tokens",
        "default_settings": model_def["default_settings"]
    }

__all__ = [
    "LanguageModel",
    "LLMProviderError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "RandomModel",
    "AnthropicModel", 
    "OpenAIModel",
    "create_model",
    "list_available_models",
    "get_model_info",
    "PROVIDERS"
]
