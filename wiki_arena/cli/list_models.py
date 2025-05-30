#!/usr/bin/env python3
"""
CLI tool to list available language models in the Wiki Arena.
"""

import argparse
import sys
from typing import Optional

from wiki_arena.language_models import list_available_models, get_model_info

def format_model_info(model_key: str, model_info: dict) -> str:
    """Format model information for display."""
    if "error" in model_info:
        return f"{model_key}: {model_info['error']}"
    
    return f"""
{model_key}
  Name: {model_info['display_name']}
  Provider: {model_info['provider']}
  Description: {model_info['description']}
  Pricing: {model_info['input_cost']} input, {model_info['output_cost']} output
  Default Settings: {model_info['default_settings']}
"""

def list_models(provider: Optional[str] = None):
    """List available models."""
    try:
        models = list_available_models()
    except Exception as e:
        print(f"Error loading models: {e}", file=sys.stderr)
        sys.exit(1)
    
    if not models:
        print("No models found in models.json")
        return
    
    # Filter by provider if specified
    if provider:
        models = {k: v for k, v in models.items() if v.get("provider") == provider}
        if not models:
            print(f"No models found for provider '{provider}'")
            return
    
    # Group by provider
    by_provider = {}
    for key, model_def in models.items():
        provider_name = model_def["provider"]
        if provider_name not in by_provider:
            by_provider[provider_name] = []
        by_provider[provider_name].append(key)
    
    # Display
    total_models = 0
    for provider_name in sorted(by_provider.keys()):
        provider_models = by_provider[provider_name]
        print(f"\n=== {provider_name.upper()} MODELS ===")
        
        for model_key in sorted(provider_models):
            model_info = get_model_info(model_key)
            print(format_model_info(model_key, model_info))
            total_models += 1
    
    print(f"\nTotal: {total_models} models")

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="List available language models in Wiki Arena",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # List all models
  %(prog)s --provider anthropic     # List only Anthropic models
        """
    )
    
    parser.add_argument(
        "--provider",
        help="Filter by provider (anthropic, openai, random)"
    )
    
    args = parser.parse_args()
    
    try:
        list_models(provider=args.provider)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main() 