# Model Configuration Guide

This guide explains how to configure and onboard language models in the Wiki Arena.

## Overview

The Wiki Arena uses a **simplified JSON-based configuration system** that provides:

- **Single source of truth** in `models.json`
- **Automatic pricing and cost tracking** 
- **Runtime configurable** models
- **Easy model onboarding** process
- **Type safety** with Pydantic validation

## Architecture

### Key Components

1. **models.json**: Dedicated file for model definitions
2. **create_model()**: Simple function to create model instances
3. **ModelConfig**: Pydantic model for type safety
4. **Provider classes**: AnthropicModel, OpenAIModel, RandomModel

### Data Flow

```
models.json → create_model() → ModelConfig → Language Model Instance → Game
```

## Using Models

### Simple Usage

```python
from wiki_arena.language_models import create_model

# Create model (no config needed!)
model = create_model("claude-3-haiku-20240307")

# Use in game configuration
game_config = GameConfig(
    start_page_title="Start Page",
    target_page_title="Target Page", 
    model=model.model_config
)
```

### With Custom Settings

```python
# Override default settings
model = create_model(
    "gpt-4o-mini-2024-07-18",
    max_tokens=2048,
    temperature=0.1
)
```

### Available Models

Use the CLI to see all available models:

```bash
python -m wiki_arena.cli.list_models
python -m wiki_arena.cli.list_models --provider anthropic
```

## Configuration Format

### models.json Structure

```json
{
  "claude-3-5-haiku-20241022": {
    "provider": "anthropic",
    "display_name": "Claude 3.5 Haiku (Oct 2024)",
    "description": "Fast, affordable model for everyday tasks",
    "input_cost_per_1m_tokens": 0.80,
    "output_cost_per_1m_tokens": 4.0,
    "default_settings": {
      "max_tokens": 1024,
      "temperature": 0.0
    }
  }
}
```

### Model Definition Fields

| Field | Required | Description |
|-------|----------|-------------|
| `provider` | ✅ | Provider name: "anthropic", "openai", "random" |
| `display_name` | ❌ | Human-readable name |
| `description` | ❌ | Model description |
| `input_cost_per_1m_tokens` | ✅ | Cost per 1M input tokens (USD) |
| `output_cost_per_1m_tokens` | ✅ | Cost per 1M output tokens (USD) |
| `default_settings` | ✅ | Provider-specific default settings |

### Model Naming Strategy

**Use full model names as keys** to avoid confusion between versions:

✅ **Good:**
- `claude-3-5-haiku-20241022`
- `gpt-4o-mini-2024-07-18`
- `claude-3-haiku-20240307`

❌ **Avoid:**
- `claude-haiku` (which version?)
- `gpt-4o-mini` (which release?)
- `sonnet` (too generic)

The key becomes the `model_name` used in API calls, so it should match the exact model identifier.

## Adding New Models

### 1. Add to models.json

```json
"claude-4-opus-2025-01-15": {
  "provider": "anthropic",
  "display_name": "Claude 4 Opus (Jan 2025)",
  "description": "Next generation reasoning model",
  "input_cost_per_1m_tokens": 15.0,
  "output_cost_per_1m_tokens": 75.0,
  "default_settings": {
    "max_tokens": 1024,
    "temperature": 0.0
  }
}
```

### 2. Test the Model

```python
# Verify it works
from wiki_arena.cli.list_models import main
main()  # Should show your new model

# Test creation
model = create_model("claude-4-opus-2025-01-15")
```

### 3. No Code Changes Needed!

Unlike the old system, adding models requires **zero code changes**. Just update the JSON file.

## Provider Differences

### Why Different Providers Need Different Settings

**Anthropic:**
- Uses `system` parameter for system prompts
- Tool format: `{"name": "...", "description": "...", "input_schema": {...}}`
- Token fields: `input_tokens`, `output_tokens`

**OpenAI:**
- System prompts in messages array
- Tool format: `{"type": "function", "function": {...}}`
- Token fields: `prompt_tokens`, `completion_tokens`

**Random:**
- No API calls, zero cost
- Simulates model behavior for baselines

## Cost Tracking

The system automatically tracks:

- **Input/output tokens** from API responses
- **Estimated costs** using models.json pricing
- **API response times** for performance analysis
- **Historical pricing** preserved in game results

### Cost Calculation

```python
# Automatic cost calculation
input_cost = (input_tokens / 1_000_000) * model_config.input_cost_per_1m_tokens
output_cost = (output_tokens / 1_000_000) * model_config.output_cost_per_1m_tokens
total_cost = input_cost + output_cost
```

## Migration from Old System

### Before (Complex)
```python
from wiki_arena.config.model_registry import create_model_config_from_registry
from wiki_arena.language_models.registry import model_registry
from wiki_arena.config import load_config

config = load_config()
model = create_model("claude-3-haiku", config)
```

### After (Simple)
```python
from wiki_arena.language_models import create_model

model = create_model("claude-3-haiku-20240307")
```

### Benefits of New System

1. **80% less code** - removed config parameter requirement
2. **Separate concerns** - models.json vs config.json
3. **Better naming** - full model names prevent confusion
4. **No redundancy** - key is the model name
5. **Cleaner structure** - dedicated models file

## Examples

### Running Different Models

```python
# Fast and cheap
model = create_model("claude-3-haiku-20240307")

# More powerful
model = create_model("claude-3-5-sonnet-20241022")

# OpenAI alternative
model = create_model("gpt-4o-mini-2024-07-18")

# Baseline comparison
model = create_model("random")
```

### Custom Settings

```python
# More creative responses
model = create_model("claude-3-5-sonnet-20241022", temperature=0.7)

# Longer responses
model = create_model("gpt-4o-2024-05-13", max_tokens=4096)

# Multiple overrides
model = create_model("gpt-4o-mini-2024-07-18", max_tokens=2048, temperature=0.1)
```

## File Structure

```
wiki-arena/
├── models.json              # Model definitions
├── config.json              # App configuration (MCP servers, logging)
└── wiki_arena/
    └── language_models/
        └── __init__.py       # Simple create_model() function
```

## Troubleshooting

### Model Not Found
```
ValueError: Model 'unknown-model' not found. Available: ['claude-3-haiku-20240307', ...]
```
**Solution:** Check available models with `python -m wiki_arena.cli.list_models`

### Provider Not Registered
```
ValueError: Unknown provider 'newprovider'. Available: ['anthropic', 'openai', 'random']
```
**Solution:** Add provider class to `PROVIDERS` dict in `wiki_arena/language_models/__init__.py`

### Missing API Keys
```
AnthropicError: API key not found
```
**Solution:** Set environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`)

### Models File Not Found
```
FileNotFoundError: models.json not found
```
**Solution:** Ensure `models.json` exists in the project root

## Best Practices

### Model Naming
- Include release date: `claude-3-5-haiku-20241022`
- Use official model identifiers
- Be specific to avoid confusion

### Pricing Updates
- Update costs when providers change rates
- Use official provider pricing pages
- Consider creating dated snapshots for historical accuracy

### Settings
- Keep defaults conservative (low temperature, reasonable token limits)
- Document any special settings in the description
- Test new models before adding to production

This simplified system makes it easy to onboard new models, track costs accurately, and maintain consistency across the Wiki Arena with **minimal complexity**. 