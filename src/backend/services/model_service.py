import logging
from typing import List, Dict, Optional
from backend.models.api_models import ModelInfoResponse
from wiki_arena.openrouter import list_openrouter_models, OpenRouterModelConfig, get_openrouter_model_config
from backend.config import MODEL_ALLOW_SET

logger = logging.getLogger(__name__)

# Only specify overrides. The default is the provider name itself.
PROVIDER_SLUG_OVERRIDES = {
    "anthropic": "claude",
    "google": "gemini",
    "mistralai": "mistral",
    "meta-llama": "meta",
    "moonshotai": "moonshot",
    "amazon": "nova",
    "x-ai": "grok",
    "wikiarena": "dice",
}

def _get_icon_slug(provider: str) -> str:
    """Gets the LobeHub icon slug for a given provider name, with specific overrides."""
    provider_lower = provider.lower()
    # Use the override if it exists, otherwise, use the provider name itself.
    return PROVIDER_SLUG_OVERRIDES.get(provider_lower, provider_lower)


class ModelService:
    """
    A centralized service for managing and providing information about available models.
    
    This service acts as a single source of truth for model metadata, enriching
    the core model configuration with frontend-specific details like icon slugs.
    """
    
    def __init__(self):
        all_models: List[OpenRouterModelConfig] = list_openrouter_models()
        self._models = [m for m in all_models if m.id in MODEL_ALLOW_SET]

        logger.info(f"ModelService initialized with {len(self._models)} allowed models.")
        logger.debug(f"Allowed models: {MODEL_ALLOW_SET}")
    
    def get_models(self) -> List[ModelInfoResponse]:
        """Returns a list of all models, enriched with frontend-specific info."""
        response_models = []
        for model_config in self._models:
            provider_name = model_config.id.split('/')[0]
            
            response_models.append(
                ModelInfoResponse(
                    id=model_config.id,
                    name=model_config.name,
                    provider=provider_name,
                    icon_slug=_get_icon_slug(provider_name),
                    created=model_config.created,
                    input_cost_per_1m_tokens=(
                        model_config.pricing.prompt * 1_000_000
                        if model_config.pricing.prompt
                        else 0.0
                    ),
                    output_cost_per_1m_tokens=(
                        model_config.pricing.completion * 1_000_000
                        if model_config.pricing.completion
                        else 0.0
                    ),
                )
            )
        
        # Sort by creation date, newest first. The random model will be last.
        response_models.sort(key=lambda m: m.created, reverse=True)
        return response_models

    def get_model_info(self, model_id: str) -> Optional[ModelInfoResponse]:
        """
        Retrieves enriched information for a single model by its ID.
        
        Returns None if the model is not found.
        """
        model_config = get_openrouter_model_config(model_id)
        if not model_config:
            return None
        
        provider_name = model_config.id.split('/')[0]
        
        return ModelInfoResponse(
            id=model_config.id,
            name=model_config.name,
            provider=provider_name,
            icon_slug=_get_icon_slug(provider_name),
            created=model_config.created,
            input_cost_per_1m_tokens=(
                model_config.pricing.prompt * 1_000_000
                if model_config.pricing.prompt
                else 0.0
            ),
            output_cost_per_1m_tokens=(
                model_config.pricing.completion * 1_000_000
                if model_config.pricing.completion
                else 0.0
            ),
        )

# Singleton instance of the ModelService
model_service = ModelService() 