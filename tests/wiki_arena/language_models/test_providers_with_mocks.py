import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime

from wiki_arena.language_models import create_model
from wiki_arena.types import AssistantToolCall, ModelCallMetrics
from wiki_arena.types import GameState, GameConfig, Page
from mcp.types import Tool


# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration


class TestProviderToolFormatting:
    """Test that each provider correctly formats tools for their specific API."""

    @pytest.mark.asyncio
    async def test_anthropic_tool_formatting(self):
        """Test that AnthropicModel formats tools correctly."""
        model = create_model("claude-3-haiku-20240307")
        
        tools = [
            Tool(
                name="navigate",
                description="Navigate to a Wikipedia page",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "page": {"type": "string", "description": "Page title"}
                    },
                    "required": ["page"]
                }
            )
        ]
        
        formatted_tools = await model._format_tools_for_provider(tools)
        
        # Anthropic format should be a list of tool definitions
        assert isinstance(formatted_tools, list)
        assert len(formatted_tools) == 1
        
        tool_def = formatted_tools[0]
        assert tool_def["name"] == "navigate"
        assert tool_def["description"] == "Navigate to a Wikipedia page"
        assert "input_schema" in tool_def

    @pytest.mark.asyncio
    async def test_openai_tool_formatting(self):
        """Test that OpenAIModel formats tools correctly."""
        model = create_model("gpt-4o-mini-2024-07-18")
        
        tools = [
            Tool(
                name="navigate",
                description="Navigate to a Wikipedia page",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "page": {"type": "string", "description": "Page title"}
                    },
                    "required": ["page"]
                }
            )
        ]
        
        formatted_tools = await model._format_tools_for_provider(tools)
        
        # OpenAI format should be a list with "type": "function" wrappers
        assert isinstance(formatted_tools, list)
        assert len(formatted_tools) == 1
        
        tool_def = formatted_tools[0]
        assert tool_def["type"] == "function"
        assert "function" in tool_def
        assert tool_def["function"]["name"] == "navigate"

    @pytest.mark.asyncio
    async def test_random_tool_formatting(self):
        """Test that RandomModel tool formatting (no-op)."""
        model = create_model("random")
        
        tools = [
            Tool(
                name="navigate",
                description="Navigate to a Wikipedia page",
                inputSchema={}
            )
        ]
        
        formatted_tools = await model._format_tools_for_provider(tools)
        
        # RandomModel should return tools unchanged
        assert formatted_tools == tools


class TestProviderClientInstantiation:
    """Test that provider clients can be instantiated without API keys (will fail, but gracefully)."""

    def test_anthropic_model_requires_api_key(self):
        """Test that AnthropicModel fails gracefully without API key."""
        # Clear the environment variable to force failure
        with patch.dict('os.environ', {}, clear=True):
            # Anthropic might not fail immediately without an API key (it's lazy)
            # Instead, test that we can create the model but it would fail on use
            try:
                model = create_model("claude-3-haiku-20240307")
                # If no exception, model creation succeeded (anthropic is lazy about API keys)
                assert model.model_config.provider == "anthropic"
            except Exception as e:
                # If it does fail, should be related to API key
                assert "api" in str(e).lower() or "key" in str(e).lower()

    def test_openai_model_requires_api_key(self):
        """Test that OpenAIModel fails gracefully without API key."""
        # Clear the environment variable to force failure
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(Exception, match="api_key.*must be set"):
                create_model("gpt-4o-mini-2024-07-18")

    def test_random_model_no_api_key_needed(self):
        """Test that RandomModel works without any API keys."""
        # Clear environment to ensure no API keys
        with patch.dict('os.environ', {}, clear=True):
            model = create_model("random")
            assert model is not None
            assert model.model_config.provider == "random"


class TestProviderAPICallStructure:
    """Test the structure of API calls without actually making them."""

    @pytest.mark.asyncio 
    async def test_anthropic_model_api_call_structure(self):
        """Test that AnthropicModel structures API calls correctly."""
        model = create_model("claude-3-haiku-20240307")
        
        # Mock the client to capture call structure
        with patch.object(model, 'client') as mock_client:
            # Mock a successful response structure
            mock_response = MagicMock()
            mock_response.content = [MagicMock(type="text", text="Test response")]
            mock_response.usage = MagicMock()
            mock_response.usage.input_tokens = 100
            mock_response.usage.output_tokens = 50
            mock_client.messages.create.return_value = mock_response
            
            # Create minimal test data
            game_state = GameState(
                game_id="test",
                config=GameConfig(
                    start_page_title="Start",
                    target_page_title="Target"
                ),
                current_page=Page(title="Test", url="http://test.com", links=["A", "B"])
            )
            
            tools = [Tool(name="navigate", description="Navigate", inputSchema={})]
            
            # Test the call
            result = await model.generate_response(tools, game_state)
            
            # Verify the API was called with correct structure
            mock_client.messages.create.assert_called_once()
            call_kwargs = mock_client.messages.create.call_args[1]
            
            assert call_kwargs["model"] == "claude-3-haiku-20240307"
            assert call_kwargs["max_tokens"] == 1024
            assert "system" in call_kwargs
            assert "messages" in call_kwargs
            assert "tools" in call_kwargs
            
            # Verify result structure
            assert isinstance(result, AssistantToolCall)
            assert result.metrics is not None
            assert result.metrics.input_tokens == 100
            assert result.metrics.output_tokens == 50

    @pytest.mark.asyncio
    async def test_openai_model_api_call_structure(self):
        """Test that OpenAIModel structures API calls correctly."""
        model = create_model("gpt-4o-mini-2024-07-18")
        
        # Mock the client to capture call structure
        with patch.object(model, 'client') as mock_client:
            # Mock a successful response structure
            mock_choice = MagicMock()
            mock_choice.message.content = "Test response"
            mock_choice.message.tool_calls = None
            
            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_response.usage = MagicMock()
            mock_response.usage.prompt_tokens = 120
            mock_response.usage.completion_tokens = 60
            mock_client.chat.completions.create.return_value = mock_response
            
            # Create minimal test data
            game_state = GameState(
                game_id="test",
                config=GameConfig(
                    start_page_title="Start",
                    target_page_title="Target"
                ),
                current_page=Page(title="Test", url="http://test.com", links=["A", "B"])
            )
            
            tools = [Tool(name="navigate", description="Navigate", inputSchema={})]
            
            # Test the call
            result = await model.generate_response(tools, game_state)
            
            # Verify the API was called with correct structure
            mock_client.chat.completions.create.assert_called_once()
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            
            assert call_kwargs["model"] == "gpt-4o-mini-2024-07-18"
            assert call_kwargs["max_tokens"] == 1024
            assert "messages" in call_kwargs
            assert "tools" in call_kwargs
            assert call_kwargs["tool_choice"] == "auto"
            
            # Verify result structure
            assert isinstance(result, AssistantToolCall)
            assert result.metrics is not None
            assert result.metrics.input_tokens == 120
            assert result.metrics.output_tokens == 60


class TestCostCalculationIntegration:
    """Test cost calculation with realistic API response scenarios."""

    def test_cost_calculation_with_realistic_token_counts(self):
        """Test cost calculations with realistic token counts from actual usage."""
        models_and_costs = [
            ("claude-3-haiku-20240307", 150, 75, 0.25, 1.25),  # Typical short interaction
            ("claude-3-5-sonnet-20241022", 500, 200, 3.0, 15.0),  # Longer reasoning task
            ("gpt-4o-mini-2024-07-18", 300, 100, 0.15, 0.60),  # OpenAI equivalent
        ]
        
        for model_key, input_tokens, output_tokens, input_rate, output_rate in models_and_costs:
            model = create_model(model_key)
            
            calculated_cost = model._calculate_cost(input_tokens, output_tokens)
            expected_cost = (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate
            
            assert abs(calculated_cost - expected_cost) < 1e-10, f"Cost mismatch for {model_key}"
            
            # Verify cost is reasonable (not zero unless it's the random model)
            if model_key != "random":
                assert calculated_cost > 0, f"Cost should be positive for {model_key}"
                assert calculated_cost < 0.01, f"Cost seems too high for {model_key}: ${calculated_cost}"

    def test_move_metrics_creation(self):
        """Test that MoveMetrics objects are created correctly."""
        # Test typical metrics
        metrics = ModelCallMetrics(
            input_tokens=150,
            output_tokens=75,
            total_tokens=225,
            estimated_cost_usd=0.0005,
            response_time_ms=750.0,
            request_timestamp=datetime.now()
        )
        
        assert metrics.input_tokens == 150
        assert metrics.output_tokens == 75
        assert metrics.total_tokens == 225
        assert metrics.estimated_cost_usd == 0.0005
        assert metrics.response_time_ms == 750.0
        assert isinstance(metrics.request_timestamp, datetime)


class TestProviderErrorHandling:
    """Test error handling in provider implementations."""

    @pytest.mark.asyncio
    async def test_anthropic_model_handles_api_errors(self):
        """Test that AnthropicModel handles API errors gracefully."""
        model = create_model("claude-3-haiku-20240307")
        
        with patch.object(model, 'client') as mock_client:
            # Mock API error
            from anthropic import AnthropicError
            mock_client.messages.create.side_effect = AnthropicError("API Error")
            
            game_state = GameState(
                game_id="test",
                config=GameConfig(
                    start_page_title="Start",
                    target_page_title="Target"
                ),
                current_page=Page(title="Test", url="http://test.com", links=["A"])
            )
            
            tools = [Tool(name="navigate", description="Navigate", inputSchema={})]
            
            result = await model.generate_response(tools, game_state)
            
            # Should return error AssistantToolCall, not raise exception
            assert isinstance(result, AssistantToolCall)
            assert result.tool_name is None
            assert result.tool_arguments is None
            assert result.metrics is not None
            assert result.metrics.estimated_cost_usd == 0.0

    @pytest.mark.asyncio
    async def test_openai_model_handles_api_errors(self):
        """Test that OpenAIModel handles API errors gracefully."""
        model = create_model("gpt-4o-mini-2024-07-18")
        
        with patch.object(model, 'client') as mock_client:
            # Mock API error
            from openai import OpenAIError
            mock_client.chat.completions.create.side_effect = OpenAIError("API Error")
            
            game_state = GameState(
                game_id="test",
                config=GameConfig(
                    start_page_title="Start",
                    target_page_title="Target"
                ),
                current_page=Page(title="Test", url="http://test.com", links=["A"])
            )
            
            tools = [Tool(name="navigate", description="Navigate", inputSchema={})]
            
            result = await model.generate_response(tools, game_state)
            
            # Should return error AssistantToolCall, not raise exception
            assert isinstance(result, AssistantToolCall)
            assert result.tool_name is None
            assert result.tool_arguments is None
            assert result.metrics is not None
            assert result.metrics.estimated_cost_usd == 0.0


class TestEndToEndWorkflow:
    """Test the complete workflow from model creation to response generation."""

    @pytest.mark.asyncio
    async def test_complete_workflow_random_model(self):
        """Test complete workflow with RandomModel (no external dependencies)."""
        # 1. Create model from config
        model = create_model("random")
        assert model.model_config.provider == "random"
        
        # 2. Create game state
        config = GameConfig(
            start_page_title="Start",
            target_page_title="Target"
        )
        
        current_page = Page(
            title="Current Page",
            url="https://example.com",
            links=["Option A", "Option B", "Option C"]
        )
        
        game_state = GameState(
            game_id="test",
            config=config,
            current_page=current_page
        )
        
        # 3. Create tools
        tools = [
            Tool(
                name="navigate",
                description="Navigate to a page",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "page_title": {"type": "string"}
                    },
                    "required": ["page_title"]
                }
            )
        ]
        
        # 4. Generate response
        response = await model.generate_response(tools, game_state)
        
        # 5. Verify complete response
        assert isinstance(response, AssistantToolCall)
        assert response.tool_name == "navigate"
        assert response.tool_arguments["page_title"] in current_page.links
        assert response.metrics is not None
        assert response.metrics.estimated_cost_usd == 0.0
        assert response.model_text_response is not None
        
        # 6. Verify cost calculation matches
        calculated_cost = model._calculate_cost(
            response.metrics.input_tokens, 
            response.metrics.output_tokens
        )
        assert calculated_cost == response.metrics.estimated_cost_usd

    def test_provider_registry_completeness(self):
        """Test that all expected providers are registered and working."""
        from wiki_arena.language_models import PROVIDERS
        
        # Test each provider can be instantiated
        provider_tests = [
            ("random", "random"),
            ("anthropic", "claude-3-haiku-20240307"),
            ("openai", "gpt-4o-mini-2024-07-18")
        ]
        
        for provider_name, model_key in provider_tests:
            assert provider_name in PROVIDERS, f"Provider {provider_name} not registered"
            
            # Test model creation (might fail due to missing API keys, but should be graceful)
            if provider_name == "random":
                # Random model should always work
                model = create_model(model_key)
                assert model.model_config.provider == provider_name
            else:
                # API-based models might fail due to missing keys, that's OK
                try:
                    model = create_model(model_key)
                    assert model.model_config.provider == provider_name
                except Exception:
                    # Expected if no API key is set
                    pass


class TestConfigurationEdgeCases:
    """Test edge cases in model configuration and usage."""

    def test_model_settings_override_behavior(self):
        """Test that model settings are properly overridden."""
        # Test with different setting combinations
        base_model = create_model("claude-3-haiku-20240307")
        assert base_model.model_config.settings["max_tokens"] == 1024
        
        # Test override
        custom_model = create_model("claude-3-haiku-20240307", max_tokens=2048, temperature=0.7)
        assert custom_model.model_config.settings["max_tokens"] == 2048
        assert custom_model.model_config.settings["temperature"] == 0.7
        
        # Original model should be unchanged
        assert base_model.model_config.settings["max_tokens"] == 1024
        assert "temperature" not in base_model.model_config.settings

    def test_provider_specific_settings(self):
        """Test that different providers handle settings appropriately."""
        # Test Anthropic-specific settings
        anthropic_model = create_model("claude-3-haiku-20240307", max_tokens=512)
        assert anthropic_model.max_tokens == 512
        
        # Test OpenAI-specific settings  
        openai_model = create_model("gpt-4o-mini-2024-07-18", max_tokens=1536)
        assert openai_model.max_tokens == 1536
        
        # Test Random model (should accept settings but not use them)
        random_model = create_model("random", max_tokens=9999)
        assert random_model.model_config.settings["max_tokens"] == 9999 