from typing import Dict, Type, List
from wiki_arena.data_models.game_models import ModelConfig
from .language_model import LanguageModel


class ModelRegistry:
    """Central registry for model providers and validation."""
    
    def __init__(self):
        self._providers: Dict[str, Type[LanguageModel]] = {}
    
    def register_provider(self, provider_name: str, model_class: Type[LanguageModel]):
        """Register a language model provider."""
        self._providers[provider_name] = model_class
    
    def create_model(self, config: ModelConfig) -> LanguageModel:
        """Create a language model instance from configuration."""
        if config.provider not in self._providers:
            raise ValueError(f"Unknown provider: {config.provider}. Available: {list(self._providers.keys())}")
        
        model_class = self._providers[config.provider]
        return model_class(config.settings)
    
    def get_providers(self) -> List[str]:
        """Get list of registered provider names."""
        return list(self._providers.keys())
    
    def is_provider_registered(self, provider_name: str) -> bool:
        """Check if a provider is registered."""
        return provider_name in self._providers


# Global registry instance
model_registry = ModelRegistry()

def get_model_registry() -> ModelRegistry:
    """Get the global model registry instance."""
    return model_registry 