# Language model providers and registry setup
from .language_model import LanguageModel, ToolCall
from .random_model import RandomModel
from .anthropic_model import AnthropicModel
from .openai_model import OpenAIModel
from .registry import model_registry, get_model_registry

# Register all available model providers
model_registry.register_provider("random", RandomModel)
model_registry.register_provider("anthropic", AnthropicModel)
model_registry.register_provider("openai", OpenAIModel)

__all__ = [
    "LanguageModel",
    "ToolCall", 
    "RandomModel",
    "AnthropicModel",
    "OpenAIModel",
    "model_registry",
    "get_model_registry"
]
