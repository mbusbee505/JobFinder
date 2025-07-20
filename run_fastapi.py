#!/usr/bin/env python3
"""
Run script for JobFinder FastAPI application
"""

import uvicorn
import sys
import os
from pathlib import Path

def main():
    """Run the FastAPI application"""
    
    # Ensure we're in the correct directory
    app_dir = Path(__file__).parent.resolve()
    os.chdir(app_dir)
    
    # Default configuration
    host = "0.0.0.0"
    port = 8000
    reload = True
    
    # Check for production mode
    if len(sys.argv) > 1 and sys.argv[1] == "--production":
        reload = False
        print("Running in production mode")
    else:
        print("Running in development mode with auto-reload")
    
    print(f"Starting JobFinder FastAPI server on http://{host}:{port}")
    print("Press Ctrl+C to stop the server")
    
    try:
        # Initialize database before starting
        from database import init_db
        init_db()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Warning: Database initialization failed: {e}")
    
    # Run the server
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=reload,
        reload_dirs=[str(app_dir)] if reload else None,
        log_level="info"
    )

if __name__ == "__main__":
    main() 