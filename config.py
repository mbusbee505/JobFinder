# config.py
from pathlib import Path
from functools import lru_cache
import shutil # ADDED
from utils import CONFIG_FILE_PATH, EXAMPLE_CONFIG_FILE_PATH # MODIFIED: Import from utils.py

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
import toml # For saving

DEFAULT_CONFIG = {
    "search_parameters": {
        "locations": ["Remote"],
        "keywords": ["Software Engineer", "Python Developer"],
        "exclusion_keywords": ["Senior", "Sr.", "Lead", "Manager"],
    },
    "resume": {
        "text": "Your resume text here. Paste your full resume or a summary."
    },
    "prompts": {
        "evaluation_prompt": """Please evaluate this job posting based on the following criteria:

MUST-HAVE Criteria (job must meet ALL of these):
- Must NOT require any security clearance
- Must be a full-time position

FLEXIBLE Criteria (job should ideally meet these, but can be flexible):
- Technical requirements can be offset by certifications, education, or demonstrated learning ability
- Tool-specific experience can often be learned on the job

Do NOT reject the job solely for:
- Asking for 1-2 years of experience
- Requiring specific tools experience
- Listing certifications as requirements (unless explicitly marked as "must have before starting")"""
    },
    "api_keys": { # API keys section
        "openai_api_key": "YOUR_OPENAI_API_KEY_HERE"
    },
    "general": { # General settings
        "ai_provider": "openai"
    }
}

def save_config(config_data: dict, path: Path = CONFIG_FILE_PATH):
    """Save the configuration data to the TOML file."""
    with path.expanduser().open("w", encoding="utf-8") as f: # Open in text mode for toml.dump
        toml.dump(config_data, f)

def create_config_if_not_exists(path: Path = CONFIG_FILE_PATH): # RENAMED function for clarity
    """Ensures config.toml exists.
    1. If config.toml exists, do nothing.
    2. If config.toml does not exist, try to copy example_config.toml to config.toml.
    3. If example_config.toml also does not exist, create config.toml from hardcoded defaults.
    """
    if not path.expanduser().exists():
        if EXAMPLE_CONFIG_FILE_PATH.expanduser().exists():
            try:
                shutil.copy2(EXAMPLE_CONFIG_FILE_PATH, path)
                print(f"'{path.name}' not found. Copied '{EXAMPLE_CONFIG_FILE_PATH.name}' to '{path.name}'.")
            except Exception as e:
                print(f"Error copying '{EXAMPLE_CONFIG_FILE_PATH.name}' to '{path.name}': {e}. Falling back to default config.")
                save_config(DEFAULT_CONFIG, path)
                print(f"Default '{path.name}' created at {path}. Please review and update it as needed.")
        else:
            print(f"'{path.name}' not found. '{EXAMPLE_CONFIG_FILE_PATH.name}' also not found. Creating default '{path.name}'.")
            save_config(DEFAULT_CONFIG, path)
            print(f"Default '{path.name}' created at {path}. Please review and update it as needed.")

def load(path: Path = CONFIG_FILE_PATH) -> dict:
    """Load the TOML config. Ensures defaults are used if file is empty or malformed."""
    create_config_if_not_exists(path) # MODIFIED: Call renamed function

    try:
        with path.expanduser().open("rb") as f:
            loaded_config = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        print(f"Error decoding TOML from '{path}': {e}. Attempting to re-initialize with defaults.")
        loaded_config = {} # Treat as empty to trigger default re-initialization

    # Check if the loaded config is empty or missing essential structures
    if not loaded_config or "search_parameters" not in loaded_config:
        # This condition handles: an empty file, a TOMLDecodeError, or a valid TOML file missing critical keys.
        print(f"Warning: Configuration at '{path}' was empty, malformed, or incomplete. Re-initializing with default values and saving.")
        save_config(DEFAULT_CONFIG, path) # Save defaults to repair/initialize the file
        return DEFAULT_CONFIG.copy() # Return a copy of the defaults for current use
        
    return loaded_config