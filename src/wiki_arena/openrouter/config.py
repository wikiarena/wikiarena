from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Architecture(BaseModel):
    modality: str
    input_modalities: List[str]
    output_modalities: List[str]
    tokenizer: str
    instruct_type: Optional[str] = None


class Pricing(BaseModel):
    prompt: float
    completion: float
    request: float
    image: float
    web_search: Optional[float] = None
    internal_reasoning: Optional[float] = None
    input_cache_read: Optional[float] = None
    input_cache_write: Optional[float] = None


class TopProvider(BaseModel):
    context_length: Optional[int] = None
    max_completion_tokens: Optional[int] = None
    is_moderated: bool


class OpenRouterModelConfig(BaseModel):
    """Configuration for a specific language model from OpenRouter."""
    id: str
    name: str
    created: int
    description: str
    context_length: int
    pricing: Pricing
    top_provider: TopProvider
    per_request_limits: Optional[Dict[str, Any]] = None
    supported_parameters: Optional[List[str]] = None
    settings: Dict[str, Any] = Field(default_factory=dict)


class OpenRouterModelsData(BaseModel):
    data: List[OpenRouterModelConfig] 

