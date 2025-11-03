# utils.py
from pathlib import Path
import os
import threading
import time

# Path configuration
PROJECT_ROOT = Path(__file__).parent.absolute()
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_FILE_PATH = PROJECT_ROOT / "config.toml"
EXAMPLE_CONFIG_FILE_PATH = PROJECT_ROOT / "example_config.toml"
DB_PATH = DATA_DIR / "jobfinder.db"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)

# Global variables for scan control
_scan_thread = None
_scan_stop_signal = [False]  # Use list for mutable reference across threads
_scan_lock = threading.Lock()

def get_scan_status():
    """Get the current scanning status."""
    with _scan_lock:
        return {
            'is_running': _scan_thread is not None and _scan_thread.is_alive(),
            'stop_requested': _scan_stop_signal[0]
        }

def start_scan():
    """Start the job scanning process in a background thread."""
    global _scan_thread, _scan_stop_signal

    with _scan_lock:
        if _scan_thread and _scan_thread.is_alive():
            return False, "Scan is already running"

        _scan_stop_signal[0] = False

        try:
            from scrape import scrape_phase
            import database

            # Initialize database
            database.init_db()
            database.set_stop_scan_flag(False)

            def scan_worker():
                try:
                    scrape_phase(_scan_stop_signal)
                except Exception as e:
                    print(f"Error during scan: {e}")
                finally:
                    # Reset stop signal when scan completes
                    _scan_stop_signal[0] = False
                    database.set_stop_scan_flag(False)

            _scan_thread = threading.Thread(target=scan_worker, daemon=True)
            _scan_thread.start()

            return True, "Scan started successfully"

        except Exception as e:
            return False, f"Failed to start scan: {e}"

def stop_scan():
    """Stop the job scanning process."""
    global _scan_stop_signal

    with _scan_lock:
        if not _scan_thread or not _scan_thread.is_alive():
            return False, "No scan is currently running"

        _scan_stop_signal[0] = True

        try:
            import database
            database.set_stop_scan_flag(True)
            return True, "Stop signal sent"
        except Exception as e:
            return False, f"Failed to send stop signal: {e}"

def wait_for_scan_completion(timeout=30):
    """Wait for the scan thread to complete, with timeout."""
    global _scan_thread

    if _scan_thread and _scan_thread.is_alive():
        _scan_thread.join(timeout=timeout)
        return not _scan_thread.is_alive()
    return True

def ensure_database_initialized():
    """Ensure the database is properly initialized."""
    try:
        import database
        database.init_db()
        return True
    except Exception as e:
        print(f"Failed to initialize database: {e}")
        return False

def get_project_info():
    """Get basic project information."""
    return {
        'project_root': str(PROJECT_ROOT),
        'data_dir': str(DATA_DIR),
        'config_file': str(CONFIG_FILE_PATH),
        'db_path': str(DB_PATH),
        'db_exists': DB_PATH.exists(),
        'config_exists': CONFIG_FILE_PATH.exists()
    }