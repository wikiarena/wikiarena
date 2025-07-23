import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from typing import Dict, Any

from wiki_arena.language_models import (
    create_model, 
    list_available_models, 
    get_model_info,
    PROVIDERS,
    _load_models_config
)
from wiki_arena.language_models.language_model import LanguageModel, ToolCall
from wiki_arena.language_models.random_model import RandomModel
from wiki_arena.types import ModelConfig, GameState, GameConfig, Page
from mcp.types import Tool


# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration


class TestLanguageModelConfiguration:
    """Test the core configuration system - models.json loading and validation."""

    def test_load_models_config_success(self):
        """Test that models.json loads correctly from project root."""
        config = _load_models_config()
        
        assert isinstance(config, dict)
        assert len(config) > 0
        
        # Check known models exist
        expected_models = [
            "claude-3-5-haiku-20241022",
            "claude-3-haiku-20240307", 
            "gpt-4o-mini-2024-07-18",
            "random"
        ]
        
        for model_key in expected_models:
            assert model_key in config, f"Expected model '{model_key}' not found in config"

    def test_load_models_config_structure(self):
        """Test that each model in models.json has required fields."""
        config = _load_models_config()
        
        required_fields = ["provider", "input_cost_per_1m_tokens", "output_cost_per_1m_tokens", "default_settings"]
        
        for model_key, model_def in config.items():
            for field in required_fields:
                assert field in model_def, f"Model '{model_key}' missing required field '{field}'"
            
            # Validate provider is known
            assert model_def["provider"] in PROVIDERS, f"Unknown provider '{model_def['provider']}' for model '{model_key}'"
            
            # Validate cost fields are numeric
            assert isinstance(model_def["input_cost_per_1m_tokens"], (int, float))
            assert isinstance(model_def["output_cost_per_1m_tokens"], (int, float))
            assert model_def["input_cost_per_1m_tokens"] >= 0
            assert model_def["output_cost_per_1m_tokens"] >= 0
            
            # Validate default_settings is a dict
            assert isinstance(model_def["default_settings"], dict)

    def test_models_config_not_found_error(self):
        """Test error handling when models.json is not found."""
        with patch('wiki_arena.language_models.Path.exists', return_value=False):
            with pytest.raises(FileNotFoundError, match="models.json not found"):
                _load_models_config()

    def test_models_config_invalid_json(self):
        """Test error handling for invalid JSON in models.json."""
        # Mock the file reading to return invalid JSON
        with patch('builtins.open', side_effect=json.JSONDecodeError("Invalid JSON", "test", 0)):
            with pytest.raises(json.JSONDecodeError):
                _load_models_config()


class TestModelCreation:
    """Test the create_model() function and model instantiation."""

    def test_create_model_success_all_providers(self):
        """Test creating models for each provider type."""
        test_cases = [
            ("claude-3-haiku-20240307", "anthropic"),
            ("gpt-4o-mini-2024-07-18", "openai"),
            ("random", "random")
        ]
        
        for model_key, expected_provider in test_cases:
            model = create_model(model_key)
            
            assert isinstance(model, LanguageModel)
            assert model.model_config.provider == expected_provider
            assert model.model_config.model_name == model_key
            assert isinstance(model.model_config.input_cost_per_1m_tokens, (int, float))
            assert isinstance(model.model_config.output_cost_per_1m_tokens, (int, float))

    def test_create_model_with_overrides(self):
        """Test creating models with setting overrides."""
        model = create_model("claude-3-haiku-20240307", max_tokens=2048, temperature=0.7)
        
        assert model.model_config.settings["max_tokens"] == 2048
        assert model.model_config.settings["temperature"] == 0.7

    def test_create_model_invalid_model_key(self):
        """Test error handling for non-existent model keys."""
        with pytest.raises(ValueError, match="Model 'nonexistent-model' not found"):
            create_model("nonexistent-model")

    def test_create_model_invalid_provider(self):
        """Test error handling for invalid provider in models.json."""
        mock_config = {
            "test-model": {
                "provider": "unknown_provider",
                "input_cost_per_1m_tokens": 1.0,
                "output_cost_per_1m_tokens": 2.0,
                "default_settings": {}
            }
        }
        
        with patch('wiki_arena.language_models._load_models_config', return_value=mock_config):
            with pytest.raises(ValueError, match="Unknown provider 'unknown_provider'"):
                create_model("test-model")

    def test_create_model_preserves_default_settings(self):
        """Test that default settings are preserved when no overrides provided."""
        model = create_model("claude-3-haiku-20240307")
        
        # Should have default max_tokens from models.json
        assert "max_tokens" in model.model_config.settings
        assert model.model_config.settings["max_tokens"] == 1024

    def test_create_model_overrides_merge_correctly(self):
        """Test that overrides merge with defaults rather than replacing."""
        model = create_model("claude-3-haiku-20240307", temperature=0.5)
        
        # Should have both default max_tokens and override temperature
        assert model.model_config.settings["max_tokens"] == 1024  # from default
        assert model.model_config.settings["temperature"] == 0.5  # from override


class TestCostCalculation:
    """Test cost calculation accuracy across different models."""

    def test_cost_calculation_accuracy(self):
        """Test that cost calculations are mathematically correct."""
        model = create_model("claude-3-haiku-20240307")
        
        # Known pricing: $0.25/1M input, $1.25/1M output
        input_tokens = 1000
        output_tokens = 500
        
        expected_input_cost = (1000 / 1_000_000) * 0.25  # $0.00025
        expected_output_cost = (500 / 1_000_000) * 1.25  # $0.000625
        expected_total = expected_input_cost + expected_output_cost  # $0.000875
        
        actual_cost = model._calculate_cost(input_tokens, output_tokens)
        
        assert abs(actual_cost - expected_total) < 1e-10, f"Expected {expected_total}, got {actual_cost}"

    def test_cost_calculation_zero_tokens(self):
        """Test cost calculation with zero tokens."""
        model = create_model("claude-3-haiku-20240307")
        
        cost = model._calculate_cost(0, 0)
        assert cost == 0.0

    def test_cost_calculation_free_model(self):
        """Test cost calculation for free models (like random)."""
        model = create_model("random")
        
        cost = model._calculate_cost(1000, 500)
        assert cost == 0.0

    def test_cost_calculation_different_model_pricing(self):
        """Test cost calculations for models with different pricing."""
        models_to_test = [
            ("claude-3-5-haiku-20241022", 0.80, 4.0),
            ("gpt-4o-mini-2024-07-18", 0.15, 0.60),
            ("random", 0.0, 0.0)
        ]
        
        for model_key, expected_input_rate, expected_output_rate in models_to_test:
            model = create_model(model_key)
            
            # Test with 1M tokens to make math simple
            cost = model._calculate_cost(1_000_000, 1_000_000)
            expected = expected_input_rate + expected_output_rate
            
            assert abs(cost - expected) < 1e-10, f"Model {model_key}: expected ${expected}, got ${cost}"


class TestProviderInstantiation:
    """Test that each provider can be instantiated correctly."""

    def test_random_model_instantiation(self):
        """Test RandomModel instantiation and basic functionality."""
        model = create_model("random")
        
        assert isinstance(model, RandomModel)
        assert model.model_config.provider == "random"
        assert model.model_config.model_name == "random"

    def test_anthropic_model_instantiation(self):
        """Test AnthropicModel instantiation."""
        from wiki_arena.language_models.anthropic_model import AnthropicModel
        
        model = create_model("claude-3-haiku-20240307")
        
        assert isinstance(model, AnthropicModel)
        assert model.model_config.provider == "anthropic"

    def test_openai_model_instantiation(self):
        """Test OpenAIModel instantiation."""
        from wiki_arena.language_models.openai_model import OpenAIModel
        
        model = create_model("gpt-4o-mini-2024-07-18")
        
        assert isinstance(model, OpenAIModel)
        assert model.model_config.provider == "openai"

    def test_all_providers_registered(self):
        """Test that all expected providers are properly registered."""
        expected_providers = ["anthropic", "openai", "random"]
        
        for provider in expected_providers:
            assert provider in PROVIDERS, f"Provider '{provider}' not registered"
            assert issubclass(PROVIDERS[provider], LanguageModel)


class TestUtilityFunctions:
    """Test utility functions for model information."""

    def test_list_available_models(self):
        """Test listing all available models."""
        models = list_available_models()
        
        assert isinstance(models, dict)
        assert len(models) > 0
        
        # Check structure
        for model_key, model_def in models.items():
            assert isinstance(model_key, str)
            assert isinstance(model_def, dict)
            assert "provider" in model_def

    def test_get_model_info_existing_model(self):
        """Test getting info for an existing model."""
        info = get_model_info("claude-3-haiku-20240307")
        
        expected_keys = ["key", "display_name", "provider", "description", 
                        "input_cost", "output_cost", "default_settings"]
        
        for key in expected_keys:
            assert key in info, f"Missing key '{key}' in model info"
        
        assert info["key"] == "claude-3-haiku-20240307"
        assert info["provider"] == "anthropic"
        assert "$" in info["input_cost"]  # Should be formatted with currency
        assert "$" in info["output_cost"]

    def test_get_model_info_nonexistent_model(self):
        """Test getting info for a non-existent model."""
        info = get_model_info("nonexistent-model")
        
        assert "error" in info
        assert "not found" in info["error"]


class TestRandomModelIntegration:
    """Test RandomModel end-to-end functionality without external dependencies."""

    @pytest.fixture
    def sample_game_state(self):
        """Create a sample game state for testing."""
        config = GameConfig(
            start_page_title="Test Start",
            target_page_title="Test Target"
        )
        
        current_page = Page(
            title="Current Page",
            url="https://example.com/current",
            links=["Link 1", "Link 2", "Link 3"]
        )
        
        return GameState(
            game_id="test_game",
            config=config,
            current_page=current_page
        )

    @pytest.fixture
    def sample_tools(self):
        """Create sample MCP tools for testing."""
        return [
            Tool(
                name="navigate",
                description="Navigate to a Wikipedia page",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "page_title": {"type": "string"}
                    },
                    "required": ["page_title"]
                }
            )
        ]

    @pytest.mark.asyncio
    async def test_random_model_generate_response_success(self, sample_game_state, sample_tools):
        """Test RandomModel can generate valid responses."""
        model = create_model("random")
        
        response = await model.generate_response(sample_tools, sample_game_state)
        
        assert isinstance(response, ToolCall)
        assert response.tool_name == "navigate"
        assert response.tool_arguments is not None
        assert "page_title" in response.tool_arguments
        assert response.tool_arguments["page_title"] in sample_game_state.current_page.links
        assert response.metrics is not None
        assert response.metrics.estimated_cost_usd == 0.0

    @pytest.mark.asyncio
    async def test_random_model_no_navigate_tool(self, sample_game_state):
        """Test RandomModel behavior when navigate tool is not available."""
        model = create_model("random")
        tools_without_navigate = [
            Tool(name="other_tool", description="Some other tool", inputSchema={})
        ]
        
        response = await model.generate_response(tools_without_navigate, sample_game_state)
        
        assert response.tool_name is None
        assert response.tool_arguments is None
        assert "not available" in response.model_text_response

    @pytest.mark.asyncio 
    async def test_random_model_no_links_available(self, sample_tools):
        """Test RandomModel behavior when no links are available."""
        model = create_model("random")
        
        # Create game state with no links
        config = GameConfig(
            start_page_title="Test Start",
            target_page_title="Test Target"
        )
        
        current_page = Page(
            title="No Links Page",
            url="https://example.com/nolinks",
            links=[]  # No links!
        )
        
        game_state = GameState(
            game_id="test_game",
            config=config,
            current_page=current_page
        )
        
        response = await model.generate_response(sample_tools, game_state)
        
        assert response.tool_name is None
        assert response.tool_arguments is None
        assert "No links available" in response.model_text_response


class TestErrorHandling:
    """Test error conditions and edge cases."""

    def test_model_config_validation(self):
        """Test ModelConfig validation with invalid data."""
        # Test missing required fields
        with pytest.raises(ValueError):
            ModelConfig()
        
        # Test valid config
        config = ModelConfig(
            provider="anthropic",
            model_name="test-model",
            input_cost_per_1m_tokens=1.0,
            output_cost_per_1m_tokens=2.0,
            settings={"max_tokens": 1024}
        )
        
        assert config.provider == "anthropic"
        assert config.model_name == "test-model"

    def test_create_model_with_corrupted_models_json(self):
        """Test behavior when models.json contains invalid data."""
        corrupted_config = {
            "invalid-model": {
                # Missing required fields
                "provider": "anthropic"
                # Missing costs and default_settings
            }
        }
        
        with patch('wiki_arena.language_models._load_models_config', return_value=corrupted_config):
            # Should raise a KeyError when trying to access missing fields
            with pytest.raises(KeyError):
                create_model("invalid-model")

    def test_provider_class_instantiation_failure(self):
        """Test handling of provider class instantiation failures."""
        # Mock a provider that fails to instantiate
        mock_provider = MagicMock()
        mock_provider.side_effect = Exception("Provider instantiation failed")
        
        with patch.dict(PROVIDERS, {"test_provider": mock_provider}):
            mock_config = {
                "test-model": {
                    "provider": "test_provider",
                    "input_cost_per_1m_tokens": 1.0,
                    "output_cost_per_1m_tokens": 2.0,
                    "default_settings": {}
                }
            }
            
            with patch('wiki_arena.language_models._load_models_config', return_value=mock_config):
                with pytest.raises(Exception, match="Provider instantiation failed"):
                    create_model("test-model")


class TestModelConfigurationEdgeCases:
    """Test edge cases in model configuration."""

    def test_negative_costs_handling(self):
        """Test that negative costs are technically allowed (for credits/rebates)."""
        mock_config = {
            "credit-model": {
                "provider": "random",
                "input_cost_per_1m_tokens": -0.5,  # Negative cost (credit)
                "output_cost_per_1m_tokens": 1.0,
                "default_settings": {}
            }
        }
        
        with patch('wiki_arena.language_models._load_models_config', return_value=mock_config):
            model = create_model("credit-model")
            
            # Cost calculation should handle negative values
            cost = model._calculate_cost(1_000_000, 0)  # 1M input tokens
            assert cost == -0.5  # Should be negative

    def test_very_large_token_counts(self):
        """Test cost calculation with very large token counts."""
        model = create_model("claude-3-haiku-20240307")
        
        # Test with 1 billion tokens
        large_tokens = 1_000_000_000
        cost = model._calculate_cost(large_tokens, large_tokens)
        
        # Should not overflow and should be reasonable
        assert cost > 0
        assert cost == 1000 * (0.25 + 1.25)  # 1000 * (input + output rate)

    def test_settings_deep_merge(self):
        """Test that nested settings merge correctly."""
        mock_config = {
            "complex-model": {
                "provider": "random", 
                "input_cost_per_1m_tokens": 1.0,
                "output_cost_per_1m_tokens": 2.0,
                "default_settings": {
                    "max_tokens": 1024,
                    "nested": {
                        "temperature": 0.0,
                        "top_p": 1.0
                    }
                }
            }
        }
        
        with patch('wiki_arena.language_models._load_models_config', return_value=mock_config):
            # Test that overrides work with nested settings
            model = create_model("complex-model", max_tokens=2048)
            
            assert model.model_config.settings["max_tokens"] == 2048  # overridden
            assert model.model_config.settings["nested"]["temperature"] == 0.0  # preserved 