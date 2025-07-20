import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def create_client() -> OpenAI:
    """
    Creates and configures an OpenAI client to connect to the OpenRouter API.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable not set.")

    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )