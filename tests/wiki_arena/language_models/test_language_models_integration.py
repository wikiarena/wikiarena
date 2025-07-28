import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from typing import Dict, Any

from wiki_arena.openrouter import get_openrouter_model_config, OpenRouterModelConfig
from wiki_arena.language_models import (
    create_model,
    # list_available_models, 
    # get_model_info,
    # PROVIDERS,
    # _load_models_config
)
from wiki_arena.language_models.language_model import LanguageModel
from wiki_arena.types import AssistantToolCall
from wiki_arena.types import ModelConfig, GameState, GameConfig, Page
from mcp.types import Tool


# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration


class TestModelCreation:
    """Test the create_model() function and model instantiation."""

    def test_create_model_success_all_providers(self):
        """Test creating models for each provider type."""
        test_cases = [
            ("anthropic/claude-3-opus:beta", "anthropic"),
            ("openai/gpt-4o-mini-2024-07-18", "openai"),
            ("wikiarena/random", "random")
        ]
        
        for model_id, expected_provider in test_cases:
            model_config = get_openrouter_model_config(model_id)
            assert model_config is not None, f"Model config for {model_id} not found."
            
            model = create_model(model_config)
            
            assert isinstance(model, LanguageModel)
            assert model.model_config.provider == expected_provider
            assert model.model_config.model_name == model_id
            assert isinstance(model.model_config.input_cost_per_1m_tokens, (int, float))
            assert isinstance(model.model_config.output_cost_per_1m_tokens, (int, float))

    def test_create_model_with_overrides(self):
        """Test creating models with setting overrides."""
        model_id = "anthropic/claude-3-opus:beta"
        model_config = get_openrouter_model_config(model_id)
        assert model_config is not None

        model = create_model(model_config, max_tokens=2048, temperature=0.7)
        
        assert model.model_config.settings["max_tokens"] == 2048
        assert model.model_config.settings["temperature"] == 0.7

    def test_create_model_invalid_model_key(self):
        """Test error handling for non-existent model keys."""
        # This test is now about handling a None model_config
        with pytest.raises(ValueError, match="model_config cannot be None"):
            create_model(None)

    def test_create_model_preserves_default_settings(self):
        """Test that default settings are preserved when no overrides provided."""
        model_id = "anthropic/claude-3-opus:beta"
        model_config = get_openrouter_model_config(model_id)
        assert model_config is not None

        model = create_model(model_config)
        
        # OpenRouter configs don't have a 'default_settings' field in the same way.
        # We can check that the settings dict exists.
        assert "max_tokens" in model.model_config.settings
        # The default value might not be 1024 anymore, so we check for presence.

    def test_create_model_overrides_merge_correctly(self):
        """Test that overrides merge with defaults rather than replacing."""
        model_id = "anthropic/claude-3-opus:beta"
        model_config = get_openrouter_model_config(model_id)
        assert model_config is not None

        model = create_model(model_config, temperature=0.5)
        
        assert "max_tokens" in model.model_config.settings  # from default
        assert model.model_config.settings["temperature"] == 0.5  # from override


class TestCostCalculation:
    """Test cost calculation accuracy across different models."""

    def test_cost_calculation_accuracy(self):
        """Test that cost calculations are mathematically correct."""
        model_id = "anthropic/claude-3-opus:beta"
        model_config = get_openrouter_model_config(model_id)
        model = create_model(model_config)
        
        input_tokens = 1000
        output_tokens = 500
        
        expected_input_cost = (1000 / 1_000_000) * (model_config.pricing.prompt)
        expected_output_cost = (500 / 1_000_000) * (model_config.pricing.completion)
        expected_total = expected_input_cost + expected_output_cost
        
        actual_cost = model._calculate_cost(input_tokens, output_tokens)
        
        assert abs(actual_cost - expected_total) < 1e-10

    def test_cost_calculation_zero_tokens(self):
        """Test cost calculation with zero tokens."""
        model_id = "anthropic/claude-3-opus:beta"
        model_config = get_openrouter_model_config(model_id)
        model = create_model(model_config)
        
        cost = model._calculate_cost(0, 0)
        assert cost == 0.0

    def test_cost_calculation_free_model(self):
        """Test cost calculation for free models (like random)."""
        model_config = get_openrouter_model_config("wikiarena/random")
        model = create_model(model_config)
        
        cost = model._calculate_cost(1000, 500)
        assert cost == 0.0

    def test_cost_calculation_different_model_pricing(self):
        """Test cost calculations for models with different pricing."""
        models_to_test = [
            "anthropic/claude-3-opus:beta",
            "openai/gpt-4o-mini-2024-07-18",
            "wikiarena/random"
        ]
        
        for model_id in models_to_test:
            model_config = get_openrouter_model_config(model_id)
            model = create_model(model_config)
            
            cost = model._calculate_cost(1_000_000, 1_000_000)
            expected = model_config.pricing.prompt + model_config.pricing.completion
            
            assert abs(cost - expected) < 1e-10


class TestProviderInstantiation:
    """Test that each provider can be instantiated correctly."""

    def test_random_model_instantiation(self):
        """Test RandomModel instantiation and basic functionality."""
        model_config = get_openrouter_model_config("wikiarena/random")
        model = create_model(model_config)
        
        assert model.model_config.provider == "random"
        assert model.model_config.model_name == "wikiarena/random"

    def test_anthropic_model_instantiation(self):
        """Test AnthropicModel instantiation."""
        from wiki_arena.language_models.anthropic_model import AnthropicModel
        
        model_config = get_openrouter_model_config("anthropic/claude-3-opus:beta")
        model = create_model(model_config)
        
        assert isinstance(model, AnthropicModel)
        assert model.model_config.provider == "anthropic"

    def test_openai_model_instantiation(self):
        """Test OpenAIModel instantiation."""
        from wiki_arena.language_models.openai_model import OpenAIModel
        
        model_config = get_openrouter_model_config("openai/gpt-4o-mini-2024-07-18")
        model = create_model(model_config)
        
        assert isinstance(model, OpenAIModel)
        assert model.model_config.provider == "openai" 