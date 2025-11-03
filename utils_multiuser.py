# utils_multiuser.py - Multi-user utility functions

import os
import sys
import subprocess
import json
from datetime import datetime
from pathlib import Path
import database_multiuser as database

# Database path
DB_PATH = "jobfinder.db"

def ensure_database_initialized():
    """Ensure the database exists and is properly initialized"""
    if not Path(DB_PATH).exists():
        print("Database not found. Initializing...")
        database.init_multiuser_db()
        from auth import init_auth_db
        init_auth_db()
    else:
        print("Database found.")

def get_project_info():
    """Get project information for display"""
    return {
        'version': '2.0.0-multiuser',
        'python_version': sys.version,
        'database_path': DB_PATH,
        'database_size': Path(DB_PATH).stat().st_size if Path(DB_PATH).exists() else 0,
        'last_updated': datetime.now().isoformat()
    }

def start_scan_for_user(user_id):
    """Start scanning process for a specific user"""
    try:
        # Check if scan is already active
        if database.is_scan_active(user_id):
            return False, "Scan is already running"

        # Set scan as active
        database.set_scan_active(user_id, True)
        database.set_stop_scan_flag(user_id, False)

        # TODO: Implement actual scanning logic with user context
        # This would typically start a background job or process
        # For now, we'll just set the flags

        return True, "Scan started successfully"
    except Exception as e:
        return False, f"Error starting scan: {str(e)}"

def stop_scan_for_user(user_id):
    """Stop scanning process for a specific user"""
    try:
        # Set stop flag
        database.set_stop_scan_flag(user_id, True)
        database.set_scan_active(user_id, False)

        return True, "Scan stopped successfully"
    except Exception as e:
        return False, f"Error stopping scan: {str(e)}"

def load_user_config(user_id):
    """Load configuration for a specific user"""
    try:
        with database.get_conn() as conn:
            rows = conn.execute("""
                SELECT config_key, config_value
                FROM user_configs
                WHERE user_id = ?
            """, (user_id,)).fetchall()

            if not rows:
                # Return default configuration if user has no config
                return get_default_config()

            # Convert rows to config dictionary
            config = {}
            for row in rows:
                key = row['config_key']
                value = json.loads(row['config_value'])

                # Parse nested keys (e.g., 'search_parameters.keywords')
                keys = key.split('.')
                current = config
                for k in keys[:-1]:
                    if k not in current:
                        current[k] = {}
                    current = current[k]
                current[keys[-1]] = value

            return config

    except Exception as e:
        print(f"Error loading user config: {e}")
        return get_default_config()

def save_user_config(user_id, config_data):
    """Save configuration for a specific user"""
    try:
        with database.get_conn() as conn:
            # Flatten the config dictionary for storage
            flat_config = flatten_dict(config_data)

            for key, value in flat_config.items():
                conn.execute("""
                    INSERT OR REPLACE INTO user_configs (user_id, config_key, config_value, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (user_id, key, json.dumps(value)))

            return True

    except Exception as e:
        print(f"Error saving user config: {e}")
        return False

def flatten_dict(d, parent_key='', sep='.'):
    """Flatten a nested dictionary"""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def get_default_config():
    """Get default configuration for new users"""
    return {
        'search_parameters': {
            'keywords': ['software engineer', 'developer', 'programmer'],
            'locations': ['Remote', 'New York', 'San Francisco'],
            'experience_level': 'entry',
            'job_type': 'full-time',
            'max_jobs_per_search': 50,
            'exclusion_keywords': []
        },
        'prompts': {
            'evaluation_prompt': """Please evaluate this job posting based on the following criteria:

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
        'resume': {
            'text': ''
        },
        'api_keys': {
            'openai_api_key': '',
            'linkedin_email': '',
            'linkedin_password': ''
        },
        'general': {
            'scan_interval_minutes': 60,
            'auto_approve_threshold': 0.7,
            'enable_notifications': False,
            'ai_provider': 'openai'
        }
    }

def get_user_presets(user_id):
    """Get configuration presets for a specific user"""
    try:
        with database.get_conn() as conn:
            rows = conn.execute("""
                SELECT preset_name, display_name, description, created_at
                FROM user_presets
                WHERE user_id = ?
                ORDER BY created_at DESC
            """, (user_id,)).fetchall()

            return [dict(row) for row in rows]

    except Exception as e:
        print(f"Error loading user presets: {e}")
        return []

def save_user_preset(user_id, preset_name, config_data, display_name=None, description=None):
    """Save a configuration preset for a specific user"""
    try:
        with database.get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO user_presets
                (user_id, preset_name, display_name, description, config_data, created_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (user_id, preset_name, display_name, description, json.dumps(config_data)))

            return True

    except Exception as e:
        print(f"Error saving user preset: {e}")
        return False

def load_user_preset(user_id, preset_name):
    """Load a specific preset for a user"""
    try:
        with database.get_conn() as conn:
            row = conn.execute("""
                SELECT config_data, display_name, description
                FROM user_presets
                WHERE user_id = ? AND preset_name = ?
            """, (user_id, preset_name)).fetchone()

            if row:
                return {
                    'config': json.loads(row['config_data']),
                    'display_name': row['display_name'],
                    'description': row['description']
                }

            return None

    except Exception as e:
        print(f"Error loading user preset: {e}")
        return None

def delete_user_preset(user_id, preset_name):
    """Delete a preset for a user"""
    try:
        with database.get_conn() as conn:
            cursor = conn.execute("""
                DELETE FROM user_presets
                WHERE user_id = ? AND preset_name = ?
            """, (user_id, preset_name))

            return cursor.rowcount > 0

    except Exception as e:
        print(f"Error deleting user preset: {e}")
        return False

# Wrapper functions for compatibility with scan/scrape/evaluate modules
def start_scan_for_user(user_id):
    """Start the scanning process for a specific user"""
    try:
        if database.is_scan_active(user_id):
            return False, "Scan is already active"

        # Reset stop flag and set scan as active
        database.set_stop_scan_flag(user_id, False)
        database.set_scan_active(user_id, True)

        # Load user configuration
        config = load_user_config(user_id)

        # TODO: Start actual scanning process with user context
        # This would typically launch a subprocess or background job
        # that runs scrape.py with user-specific parameters

        return True, "Scan started successfully"

    except Exception as e:
        database.set_scan_active(user_id, False)
        return False, f"Error starting scan: {str(e)}"

def stop_scan_for_user(user_id):
    """Stop the scanning process for a specific user"""
    try:
        database.set_stop_scan_flag(user_id, True)
        database.set_scan_active(user_id, False)
        return True, "Scan stop signal sent"

    except Exception as e:
        return False, f"Error stopping scan: {str(e)}"

def get_scan_status(user_id):
    """Get scan status for compatibility"""
    return database.get_scan_status(user_id)