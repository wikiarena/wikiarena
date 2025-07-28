import json
import os
import sys

def verify_allowed_models():
    """
    Verifies the model allow list by filtering the main models file
    and printing the names and count of the allowed models.
    """
    try:
        # --- Add project root to sys.path to allow importing from backend ---
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        # Add the 'src' directory to the Python path to find the config module
        sys.path.insert(0, os.path.join(project_root))

        # --- Load the models ---
        models_file_path = os.path.join(project_root, "openrouter_models.json")
        with open(models_file_path, "r") as f:
            all_models_data = json.load(f)

        
        # --- Sort the models by creation date ---
        sorted_models = sorted(all_models_data['data'], key=lambda x: x.get('created', 0), reverse=True)

        # --- Print the results ---
        print("--- Model List (copy and paste into config.py) ---")
        
        print("MODEL_ALLOW_SET = {")
        # Print sorted models
        for model in sorted_models:
            print(f'    "{model["id"]}",')
        print("}")

    except FileNotFoundError as e:
        print(f"Error: Could not find a required file. Make sure 'openrouter_models.json' and 'src/backend/config.py' exist.")
        print(f"Details: {e}")
    except ImportError:
        print("Error: Could not import MODEL_ALLOW_SET from src.backend.config. Please check the file path and structure.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    verify_allowed_models() 