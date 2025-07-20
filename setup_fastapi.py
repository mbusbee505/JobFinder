#!/usr/bin/env python3
"""
Enhanced setup script for JobFinder FastAPI deployment
Optimized for Linux/Unix environments
"""

import subprocess
import sys
import os
from pathlib import Path

VENV_DIR = ".venv"
VENV_PATH = Path(__file__).resolve().parent / VENV_DIR
REQUIREMENTS_FILE = "requirements.txt"

def run_command_with_feedback(command_args, cwd=None):
    """Runs a command and prints its output line by line. Exits on error."""
    print(f"Running: {' '.join(str(arg) for arg in command_args)}")
    try:
        process = subprocess.Popen(
            command_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            cwd=cwd
        )
        if process.stdout:
            for line in iter(process.stdout.readline, ''):
                print(line, end='')
            process.stdout.close()
        
        process.wait()
        
        if process.returncode != 0:
            print(f"\nError: Command failed with exit code {process.returncode}")
            sys.exit(process.returncode)
    except FileNotFoundError:
        print(f"\nError: Command not found: {command_args[0]}. Is it installed?")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        sys.exit(1)
    print("-" * 40)

def check_system_requirements():
    """Check if required system packages are available"""
    print("Checking system requirements...")
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("Error: Python 3.8 or higher is required")
        sys.exit(1)
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor} found")
    
    # Check for git (useful for deployments)
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        print("✓ Git is available")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("⚠ Git not found (optional but recommended)")

def main():
    print("=== JobFinder FastAPI Setup ===")
    
    # Check system requirements
    check_system_requirements()
    
    # Create virtual environment if it doesn't exist
    if not VENV_PATH.is_dir():
        print(f"Creating virtual environment in '{VENV_DIR}'...")
        run_command_with_feedback([sys.executable, "-m", "venv", VENV_DIR])
        print(f"✓ Virtual environment '{VENV_DIR}' created successfully.")
    else:
        print(f"✓ Virtual environment '{VENV_DIR}' already exists.")

    # Determine paths to Python and Pip within the virtual environment
    if os.name == "nt":  # Windows
        venv_python = VENV_PATH / "Scripts" / "python.exe"
        venv_pip = VENV_PATH / "Scripts" / "pip.exe"
    else:  # Linux, macOS
        venv_python = VENV_PATH / "bin" / "python"
        venv_pip = VENV_PATH / "bin" / "pip"

    if not venv_python.exists():
        print(f"Error: Python interpreter not found at '{venv_python}'.")
        sys.exit(1)
    if not venv_pip.exists():
        print(f"Error: Pip not found at '{venv_pip}'.")
        sys.exit(1)
    
    print(f"✓ Using Python from venv: {venv_python}")

    # Upgrade pip first
    print("Upgrading pip...")
    run_command_with_feedback([str(venv_pip), "install", "--upgrade", "pip"])

    # Install dependencies from requirements.txt
    req_file_path = Path(__file__).resolve().parent / REQUIREMENTS_FILE
    if req_file_path.exists():
        print(f"Installing dependencies from '{REQUIREMENTS_FILE}'...")
        run_command_with_feedback([str(venv_pip), "install", "-r", str(req_file_path)])
        print("✓ Dependencies installed successfully.")
    else:
        print(f"Warning: '{REQUIREMENTS_FILE}' not found. Skipping dependency installation.")

    # Initialize the database
    print("Initializing database...")
    project_root_dir = Path(__file__).resolve().parent
    run_command_with_feedback([
        str(venv_python),
        "-c",
        "import sys; sys.path.insert(0, ''); import database; database.init_db(); print(f'✓ Database initialized at: {database.DB_PATH.resolve()}')"
    ], cwd=str(project_root_dir))
    
    # Create systemd service file (Linux only)
    if os.name != "nt":
        create_systemd_service()
    
    print("\n=== Setup Complete! ===")
    print("🚀 To start the application:")
    print(f"   {venv_python} run_fastapi.py")
    print("\n📱 Application will be available at: http://localhost:8000")
    
    if os.name != "nt":
        print("\n🔧 For production deployment:")
        print("   sudo systemctl enable jobfinder")
        print("   sudo systemctl start jobfinder")

def create_systemd_service():
    """Create a systemd service file for Linux deployment"""
    try:
        project_root = Path(__file__).resolve().parent
        venv_python = project_root / ".venv" / "bin" / "python"
        run_script = project_root / "run_fastapi.py"
        
        service_content = f"""[Unit]
Description=JobFinder FastAPI Application
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory={project_root}
Environment=PATH={project_root}/.venv/bin
ExecStart={venv_python} {run_script} --production
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""
        
        service_file = Path("/tmp/jobfinder.service")
        service_file.write_text(service_content)
        
        print(f"✓ Systemd service file created at {service_file}")
        print(f"   To install: sudo cp {service_file} /etc/systemd/system/")
        print(f"   Then: sudo systemctl daemon-reload")
        
    except Exception as e:
        print(f"⚠ Could not create systemd service: {e}")

if __name__ == "__main__":
    main() 