import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get the API key from environment variables
api_key = os.environ.get("OPENROUTER_API_KEY")

if not api_key:
    print("Error: OPENROUTER_API_KEY not found in .env file or environment variables.")
    exit(1)

print("Checking key...")

try:
    response = requests.get(
      url="https://openrouter.ai/api/v1/auth/key",
      headers={
        "Authorization": f"Bearer {api_key}"
      }
    )
    response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)
    
    print("Key is valid!")
    print(json.dumps(response.json(), indent=2))

except requests.exceptions.HTTPError as http_err:
    print(f"HTTP error occurred: {http_err}")
    print("Your key is likely invalid or expired.")
    if response.text:
        try:
            print("Server response:")
            print(json.dumps(response.json(), indent=2))
        except json.JSONDecodeError:
            print(response.text)
except requests.exceptions.RequestException as req_err:
    print(f"An error occurred: {req_err}") 