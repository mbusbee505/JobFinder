#!/bin/bash
# JobFinder FastAPI Application Launcher
# Replaces the old Streamlit run_app.sh

# Get the absolute directory of this bash script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
FASTAPI_SCRIPT="$SCRIPT_DIR/run_fastapi.py"

echo "🚀 Starting JobFinder FastAPI Application..."

# Check for virtual environment Python executable
if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ Virtual environment's Python ($VENV_PYTHON) not found."
    echo "📦 Please run setup.py first to create the virtual environment:"
    echo "   python3 setup.py"
    echo "   # or use the enhanced version:"
    echo "   python3 setup_fastapi.py"
    exit 1
fi

# Check for FastAPI run script
if [ ! -f "$FASTAPI_SCRIPT" ]; then
    echo "❌ FastAPI run script ($FASTAPI_SCRIPT) not found."
    exit 1
fi

echo "✓ Using Python from .venv: $VENV_PYTHON"
echo "✓ Starting FastAPI server..."

# Run FastAPI application
"$VENV_PYTHON" "$FASTAPI_SCRIPT" "$@"

echo ""
echo "JobFinder FastAPI application has finished." 