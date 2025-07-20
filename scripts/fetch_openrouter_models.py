import json
import requests
import os

def fetch_and_save_models():
    """
    Fetches model data from the OpenRouter API and saves it to a JSON file.
    """
    url = "https://openrouter.ai/api/v1/models?supported_parameters=tools"
    # url = "https://openrouter.ai/api/v1/models"
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes

        models_data = response.json()

        # Get the root directory of the project
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        file_path = os.path.join(project_root, "openrouter_models.json")

        with open(file_path, "w") as f:
            json.dump(models_data, f, indent=4)

        print(f"Successfully fetched and saved model data to {file_path}")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from OpenRouter: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    fetch_and_save_models() 