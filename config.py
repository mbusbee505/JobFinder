# config.py
from pathlib import Path
from functools import lru_cache
import shutil # ADDED
import json
import os
from datetime import datetime
from utils import CONFIG_FILE_PATH, EXAMPLE_CONFIG_FILE_PATH, PROJECT_ROOT # MODIFIED: Import from utils.py

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
import toml # For saving

# Preset configuration directory
PRESETS_DIR = PROJECT_ROOT / "presets"
PRESETS_DIR.mkdir(exist_ok=True)

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
    try:
        with path.expanduser().open("w", encoding="utf-8") as f: # Open in text mode for toml.dump
            toml.dump(config_data, f)
        return True
    except Exception as e:
        print(f"Error saving config to {path}: {e}")
        raise

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

def get_user_config(user_id: int) -> dict:
    """Get configuration for a specific user. Currently loads from default config.toml."""
    # For now, all users share the same config. In future, could support per-user configs.
    return load()


# Preset Configuration Management Functions
def get_available_presets():
    """Get list of available preset configurations."""
    presets = []
    try:
        for preset_file in PRESETS_DIR.glob("*.json"):
            preset_data = load_preset(preset_file.stem)
            if preset_data:
                presets.append({
                    'name': preset_file.stem,
                    'display_name': preset_data.get('metadata', {}).get('display_name', preset_file.stem),
                    'description': preset_data.get('metadata', {}).get('description', ''),
                    'created_at': preset_data.get('metadata', {}).get('created_at', ''),
                    'last_modified': preset_data.get('metadata', {}).get('last_modified', ''),
                    'file_size': preset_file.stat().st_size
                })
    except Exception as e:
        print(f"Error loading presets: {e}")

    return sorted(presets, key=lambda x: x['display_name'].lower())

def save_preset(name: str, config_data: dict, display_name: str = None, description: str = "") -> bool:
    """Save current configuration as a named preset."""
    try:
        # Sanitize the name for filename
        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        if not safe_name:
            return False

        preset_data = {
            'metadata': {
                'display_name': display_name or name,
                'description': description,
                'created_at': datetime.now().isoformat(),
                'last_modified': datetime.now().isoformat(),
                'version': '1.0'
            },
            'config': config_data
        }

        preset_path = PRESETS_DIR / f"{safe_name}.json"
        with preset_path.open('w', encoding='utf-8') as f:
            json.dump(preset_data, f, indent=2, ensure_ascii=False)

        return True
    except Exception as e:
        print(f"Error saving preset '{name}': {e}")
        return False

def load_preset(name: str) -> dict:
    """Load a named preset configuration."""
    try:
        preset_path = PRESETS_DIR / f"{name}.json"
        if not preset_path.exists():
            return None

        with preset_path.open('r', encoding='utf-8') as f:
            preset_data = json.load(f)

        return preset_data
    except Exception as e:
        print(f"Error loading preset '{name}': {e}")
        return None

def apply_preset(name: str) -> bool:
    """Load a preset and apply it as the current configuration."""
    try:
        preset_data = load_preset(name)
        if not preset_data:
            return False

        config = preset_data.get('config', {})
        if not config:
            return False

        # Save as current config
        save_config(config)
        return True
    except Exception as e:
        print(f"Error applying preset '{name}': {e}")
        return False

def delete_preset(name: str) -> bool:
    """Delete a named preset."""
    try:
        preset_path = PRESETS_DIR / f"{name}.json"
        if preset_path.exists():
            preset_path.unlink()
            return True
        return False
    except Exception as e:
        print(f"Error deleting preset '{name}': {e}")
        return False

def rename_preset(old_name: str, new_name: str, new_display_name: str = None) -> bool:
    """Rename a preset."""
    try:
        preset_data = load_preset(old_name)
        if not preset_data:
            return False

        # Update metadata
        preset_data['metadata']['display_name'] = new_display_name or new_name
        preset_data['metadata']['last_modified'] = datetime.now().isoformat()

        # Save with new name
        safe_new_name = "".join(c for c in new_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        if save_preset(safe_new_name, preset_data['config'], new_display_name or new_name,
                      preset_data['metadata'].get('description', '')):
            # Delete old preset
            delete_preset(old_name)
            return True
        return False
    except Exception as e:
        print(f"Error renaming preset '{old_name}' to '{new_name}': {e}")
        return False

def create_default_presets():
    """Create some useful default presets if they don't exist."""
    default_presets = [
        {
            'name': 'remote_python',
            'display_name': 'Remote Python Developer',
            'description': 'Configuration for remote Python developer positions',
            'config': {
                "search_parameters": {
                    "locations": ["Remote"],
                    "keywords": ["Python Developer", "Backend Developer", "Full Stack Python"],
                    "exclusion_keywords": ["Senior", "Sr.", "Lead", "Manager", "Director"],
                },
                "resume": DEFAULT_CONFIG["resume"],
                "prompts": DEFAULT_CONFIG["prompts"],
                "api_keys": DEFAULT_CONFIG["api_keys"],
                "general": DEFAULT_CONFIG["general"]
            }
        },
        {
            'name': 'entry_level_software',
            'display_name': 'Entry Level Software Engineer',
            'description': 'Configuration for entry-level software engineering roles',
            'config': {
                "search_parameters": {
                    "locations": ["Remote", "San Francisco Bay Area", "New York", "Seattle"],
                    "keywords": ["Software Engineer", "Junior Developer", "Associate Software Engineer", "Graduate Software Engineer"],
                    "exclusion_keywords": ["Senior", "Sr.", "Lead", "Manager", "Director", "Principal", "Staff"],
                },
                "resume": DEFAULT_CONFIG["resume"],
                "prompts": {
                    "evaluation_prompt": """Please evaluate this job posting for an entry-level candidate based on these criteria:

MUST-HAVE Criteria (job must meet ALL of these):
- Must NOT require any security clearance
- Must be a full-time position
- Should be entry-level, junior, or accept new graduates
- Must not require more than 2 years of experience

FLEXIBLE Criteria (job should ideally meet these, but can be flexible):
- Technical requirements can be learned on the job
- Specific technology experience is preferred but not mandatory
- Certifications are nice-to-have, not requirements

STRONGLY PREFER jobs that:
- Mention training, mentorship, or onboarding programs
- Are open to new graduates or career changers
- Focus on learning and growth opportunities"""
                },
                "api_keys": DEFAULT_CONFIG["api_keys"],
                "general": DEFAULT_CONFIG["general"]
            }
        },
        {
            'name': 'fullstack_web',
            'display_name': 'Full Stack Web Developer',
            'description': 'Configuration for full-stack web development positions',
            'config': {
                "search_parameters": {
                    "locations": ["Remote", "San Francisco Bay Area", "Austin", "Denver"],
                    "keywords": ["Full Stack Developer", "Web Developer", "Frontend Developer", "Backend Developer"],
                    "exclusion_keywords": ["Senior", "Sr.", "Lead", "Manager", "Director", "Mobile", "iOS", "Android"],
                },
                "resume": DEFAULT_CONFIG["resume"],
                "prompts": DEFAULT_CONFIG["prompts"],
                "api_keys": DEFAULT_CONFIG["api_keys"],
                "general": DEFAULT_CONFIG["general"]
            }
        }
    ]

    for preset in default_presets:
        if not load_preset(preset['name']):  # Only create if doesn't exist
            save_preset(
                preset['name'],
                preset['config'],
                preset['display_name'],
                preset['description']
            )