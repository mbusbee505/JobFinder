from fastapi import FastAPI, Request, Form, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio
import json
import html
import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List
import pandas as pd
from datetime import datetime

# Import all existing backend modules (no changes needed to these)
try:
    from database import (
        init_db, mark_job_as_applied, 
        delete_approved_job, clear_all_approved_jobs, archive_all_applied_jobs,
        set_stop_scan_flag, should_stop_scan
    )
    from utils import DB_PATH, CONFIG_FILE_PATH
    from config import load as load_config
    from scrape import scrape_phase
    # Import page-specific functions directly from the current structure
    import sqlite3
except ImportError as e:
    print(f"Warning: Some modules could not be imported: {e}")
    # Create fallback functions if needed

# Initialize FastAPI app
app = FastAPI(title="JobFinder", description="AI-Powered Job Discovery Dashboard")

# Add CORS middleware for WebSocket support
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    try:
        init_db()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Database initialization failed: {e}")

# WebSocket connection manager for real-time updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                # Remove disconnected clients
                self.active_connections.remove(connection)

manager = ConnectionManager()

# Import data fetching functions from original Streamlit pages
def fetch_approved_jobs():
    """Fetches all approved jobs, including their primary key and new date_applied status."""
    if not DB_PATH:
        return pd.DataFrame()
    if not DB_PATH.exists():
        return pd.DataFrame()

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        query = """
        SELECT
            aj.id AS approved_job_pk, 
            dj.url,
            dj.title,
            dj.description,
            dj.location,
            dj.keyword,
            aj.date_approved,
            aj.reason,
            aj.date_applied 
        FROM
            approved_jobs aj
        JOIN
            discovered_jobs dj ON aj.discovered_job_id = dj.id
        WHERE aj.date_applied IS NULL
        ORDER BY
            aj.date_approved DESC;
        """
        df = pd.read_sql_query(query, conn)
        
        if 'date_approved' in df.columns:
            try:
                df['date_approved'] = pd.to_datetime(df['date_approved']).dt.strftime('%Y-%m-%d %H:%M:%S')
            except: pass
        if 'date_applied' in df.columns:
            try:
                df['date_applied_str'] = pd.to_datetime(df['date_applied']).dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                df['date_applied_str'] = None
        else:
            df['date_applied_str'] = None

        return df
    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()

def fetch_only_applied_jobs_data():
    """Fetches jobs that have been marked as applied and are NOT archived."""
    if not DB_PATH.exists():
        return pd.DataFrame()

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        query = """
        SELECT
            aj.id AS approved_job_pk, 
            dj.url,
            dj.title,
            dj.location,
            dj.keyword,
            aj.date_approved,
            aj.reason,
            aj.date_applied 
        FROM
            approved_jobs aj
        JOIN
            discovered_jobs dj ON aj.discovered_job_id = dj.id
        WHERE 
            aj.date_applied IS NOT NULL AND (aj.is_archived = FALSE OR aj.is_archived IS NULL)
        ORDER BY
            aj.date_applied DESC;
        """
        df = pd.read_sql_query(query, conn)
        
        if 'date_approved' in df.columns:
            try: df['date_approved'] = pd.to_datetime(df['date_approved']).dt.strftime('%Y-%m-%d %H:%M:%S')
            except: pass
        if 'date_applied' in df.columns:
            try: df['date_applied'] = pd.to_datetime(df['date_applied']).dt.strftime('%Y-%m-%d %H:%M:%S')
            except: pass
        return df
    except sqlite3.Error as e:
        print(f"SQLite error fetching applied jobs: {e}")
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()

def fetch_job_data_for_stats():
    """Fetches all necessary data from discovered_jobs and approved_jobs."""
    if not DB_PATH:
        return pd.DataFrame(), pd.DataFrame()
    if not DB_PATH.exists():
        return pd.DataFrame(), pd.DataFrame()

    try:
        conn = sqlite3.connect(DB_PATH)
        discovered_df = pd.read_sql_query("SELECT * FROM discovered_jobs", conn)
        approved_df = pd.read_sql_query("""
            SELECT aj.*, dj.keyword, dj.location, dj.title as discovered_title
            FROM approved_jobs aj
            JOIN discovered_jobs dj ON aj.discovered_job_id = dj.id
        """, conn)
        conn.close()
        return discovered_df, approved_df
    except Exception as e:
        print(f"Error fetching data for statistics: {e}")
        return pd.DataFrame(), pd.DataFrame()

def load_config_data(file_path):
    """Load configuration data from TOML file"""
    try:
        # Use the main config loading function for consistency
        return load_config(file_path)
    except Exception as e:
        print(f"Error loading config file '{file_path}': {e}")
        return {}

def save_config_data(file_path, data):
    """Save configuration data to TOML file"""
    try:
        import toml
        with file_path.open("w", encoding="utf-8") as f:
            toml.dump(data, f)
        print(f"Configuration saved to '{file_path.name}'!")
        return True
    except Exception as e:
        print(f"Error saving TOML config file '{file_path}': {e}")
        return False

def load_config_data(file_path):
    """Load configuration data from TOML file"""
    try:
        import toml
        if file_path.exists():
            with file_path.open("r", encoding="utf-8") as f:
                return toml.load(f)
        return None
    except Exception as e:
        print(f"Error loading TOML config file '{file_path}': {e}")
        return None

def get_default_config_structure():
    """Get default configuration structure"""
    return {
        "search_parameters": {
            "locations": ["remote", "City, State, Country"],
            "keywords": ["Keyword1", "Keyword2"],
            "exclusion_keywords": ["Senior", "Lead", "Manager", "Clearance"],
        },
        "resume": {
            "text": "Paste your default resume text here...\n\nTechnical Skills\n...\n\nProfessional Experience\n..."
        },
        "personal_info": {
            "first_name": "Your First Name",
            "last_name": "Your Last Name", 
            "phone_number": "(555) 123-4567",
            "email_address": "your.email@example.com",
            "linkedin_url": "https://linkedin.com/in/yourprofile"
        },
        "prompts": {
             "evaluation_prompt": "MUST-HAVE Criteria (job must meet ALL of these):\n1. ...\n\nFLEXIBLE Criteria:\n...\n\nDo NOT reject the job solely for:\n..."
        },
        "api_keys": {
            "openai_api_key": "YOUR_OPENAI_API_KEY_HERE"
        },
        "general": {
            "ai_provider": "openai"
        }
    }

# Utility functions for data conversion
def convert_dataframe_for_template(df: pd.DataFrame) -> List[dict]:
    """Convert pandas DataFrame to list of dictionaries for template rendering"""
    if df.empty:
        return []
    return df.to_dict('records')

def format_datetime(dt_str: str) -> str:
    """Format datetime string for display"""
    if not dt_str or pd.isna(dt_str):
        return "N/A"
    try:
        dt = pd.to_datetime(dt_str)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return str(dt_str)

# Global scan state management
scan_state = {
    "is_running": False,
    "last_message": "",
    "progress": 0,
    "stop_requested": False,
    "current_task": None
}

# Routes
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page - replaces 01_Dashboard.py"""
    try:
        # Fetch approved jobs using existing function from 01_Dashboard.py
        approved_jobs_df = fetch_approved_jobs()
        jobs = convert_dataframe_for_template(approved_jobs_df)
        
        # Format dates for display
        for job in jobs:
            job['date_approved'] = format_datetime(job.get('date_approved'))
            job['title_escaped'] = html.escape(str(job.get('title', 'N/A')))
            job['reason_escaped'] = html.escape(str(job.get('reason', 'N/A')))
            job['description_escaped'] = html.escape(str(job.get('description', 'N/A')))
        
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "jobs": jobs,
            "total_jobs": len(jobs),
            "scan_state": scan_state
        })
    except Exception as e:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": f"Error loading dashboard: {e}"
        })

@app.get("/applied-jobs", response_class=HTMLResponse)
async def applied_jobs(request: Request):
    """Applied jobs page - replaces 02_Applied_Jobs.py"""
    try:
        applied_jobs_df = fetch_only_applied_jobs_data()
        jobs = convert_dataframe_for_template(applied_jobs_df)
        
        # Format dates for display
        for job in jobs:
            job['date_approved'] = format_datetime(job.get('date_approved'))
            job['date_applied'] = format_datetime(job.get('date_applied'))
            job['title_escaped'] = html.escape(str(job.get('title', 'N/A')))
            job['reason_escaped'] = html.escape(str(job.get('reason', 'N/A')))
        
        return templates.TemplateResponse("applied_jobs.html", {
            "request": request,
            "jobs": jobs,
            "total_jobs": len(jobs)
        })
    except Exception as e:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": f"Error loading applied jobs: {e}"
        })

@app.get("/statistics", response_class=HTMLResponse)
async def statistics(request: Request):
    """Statistics page - replaces 04_Statistics.py"""
    try:
        discovered_df, approved_df = fetch_job_data_for_stats()
        
        # Calculate metrics
        total_discovered = len(discovered_df)
        total_analyzed = len(discovered_df[discovered_df['analyzed'] == True]) if not discovered_df.empty else 0
        total_approved = len(approved_df)
        total_applied = len(approved_df[approved_df['date_applied'].notna()]) if not approved_df.empty else 0
        
        # Prepare chart data
        keyword_data = []
        location_data = []
        
        if not approved_df.empty and 'keyword' in approved_df.columns:
            keyword_counts = approved_df['keyword'].value_counts()
            keyword_data = [{"keyword": k, "count": v} for k, v in keyword_counts.items()]
        
        if not approved_df.empty and 'location' in approved_df.columns:
            location_counts = approved_df['location'].value_counts()
            location_data = [{"location": k, "count": v} for k, v in location_counts.items()]
        
        return templates.TemplateResponse("statistics.html", {
            "request": request,
            "metrics": {
                "total_discovered": total_discovered,
                "total_analyzed": total_analyzed,
                "total_approved": total_approved,
                "total_applied": total_applied
            },
            "keyword_data": keyword_data,
            "location_data": location_data
        })
    except Exception as e:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": f"Error loading statistics: {e}"
        })

@app.get("/configuration", response_class=HTMLResponse)
@app.get("/settings", response_class=HTMLResponse)
async def configuration_page(request: Request):
    """Settings/Configuration page - replaces 03_Inputs.py"""
    try:
        config_data = load_config_data(CONFIG_FILE_PATH)
        if not config_data:
            config_data = get_default_config_structure()
        
        # Ensure all required sections exist with defaults
        default_structure = get_default_config_structure()
        for section, defaults in default_structure.items():
            if section not in config_data:
                config_data[section] = defaults
            elif isinstance(defaults, dict):
                for key, default_value in defaults.items():
                    if key not in config_data[section]:
                        config_data[section][key] = default_value
        
        return templates.TemplateResponse("configuration.html", {
            "request": request,
            "config": config_data
        })
    except Exception as e:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": f"Error loading configuration: {e}"
        })

# API Routes for actions
@app.post("/api/mark-applied/{job_id}")
async def api_mark_applied(job_id: int):
    """Mark a job as applied"""
    try:
        success = mark_job_as_applied(job_id)
        if success:
            await manager.broadcast(json.dumps({
                "type": "job_updated",
                "message": "Job marked as applied successfully"
            }))
            return {"success": True, "message": "Job marked as applied"}
        else:
            return {"success": False, "message": "Failed to mark job as applied"}
    except Exception as e:
        return {"success": False, "message": f"Error: {e}"}

@app.post("/api/delete-job/{job_id}")
async def api_delete_job(job_id: int):
    """Delete an approved job"""
    try:
        success = delete_approved_job(job_id)
        if success:
            await manager.broadcast(json.dumps({
                "type": "job_updated",
                "message": "Job deleted successfully"
            }))
            return {"success": True, "message": "Job deleted"}
        else:
            return {"success": False, "message": "Failed to delete job"}
    except Exception as e:
        return {"success": False, "message": f"Error: {e}"}

@app.post("/api/start-scan")
async def api_start_scan():
    """Start job scanning"""
    global scan_state
    if scan_state["is_running"]:
        return {"success": False, "message": "Scan already running"}
    
    try:
        # Reset all flags and state
        set_stop_scan_flag(False)
        scan_state["is_running"] = True
        scan_state["stop_requested"] = False
        scan_state["last_message"] = "Scan started..."
        scan_state["progress"] = 0
        
        # Start scan in background and store task reference
        scan_state["current_task"] = asyncio.create_task(run_scan_background())
        
        await manager.broadcast(json.dumps({
            "type": "scan_started",
            "message": "Job scan started"
        }))
        
        return {"success": True, "message": "Scan started"}
    except Exception as e:
        scan_state["is_running"] = False
        scan_state["stop_requested"] = False
        return {"success": False, "message": f"Error starting scan: {e}"}

@app.post("/api/stop-scan")
async def api_stop_scan():
    """Stop job scanning"""
    global scan_state
    try:
        # Set stop flags
        set_stop_scan_flag(True)
        scan_state["stop_requested"] = True
        
        # Cancel the background task if it exists
        if scan_state["current_task"] and not scan_state["current_task"].done():
            scan_state["current_task"].cancel()
        
        # Update state immediately for UI feedback
        scan_state["last_message"] = "Stop requested - terminating scan..."
        
        await manager.broadcast(json.dumps({
            "type": "scan_stopping",
            "message": "Stop requested - terminating scan..."
        }))
        
        # Wait a moment for graceful shutdown
        await asyncio.sleep(0.1)
        
        # Force update state if not already stopped
        if scan_state["is_running"]:
            scan_state["is_running"] = False
            scan_state["last_message"] = "Scan force stopped"
            
            await manager.broadcast(json.dumps({
                "type": "scan_stopped",
                "message": "Scan stopped"
            }))
        
        return {"success": True, "message": "Stop signal sent"}
    except Exception as e:
        return {"success": False, "message": f"Error stopping scan: {e}"}

@app.post("/api/clear-jobs")
async def api_clear_jobs():
    """Clear all approved jobs"""
    try:
        deleted_count = clear_all_approved_jobs()
        await manager.broadcast(json.dumps({
            "type": "jobs_cleared",
            "message": f"Cleared {deleted_count} approved jobs"
        }))
        return {"success": True, "message": f"Cleared {deleted_count} jobs"}
    except Exception as e:
        return {"success": False, "message": f"Error clearing jobs: {e}"}

@app.post("/api/archive-applied-jobs")
async def api_archive_applied_jobs():
    """Archive all applied jobs"""
    try:
        archived_count = archive_all_applied_jobs()
        await manager.broadcast(json.dumps({
            "type": "jobs_archived",
            "message": f"Archived {archived_count} applied jobs"
        }))
        return {"success": True, "message": f"Archived {archived_count} applied jobs"}
    except Exception as e:
        return {"success": False, "message": f"Error archiving applied jobs: {e}"}

@app.post("/api/generate-resume/{job_id}")
async def api_generate_resume(job_id: int):
    """Generate a personalized resume for a specific job"""
    try:
        # Import generate_resume module
        from generate_resume import generate_resume
        
        # Get job details from database
        conn = None
        try:
            import sqlite3
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.execute("""
                SELECT dj.title, dj.description, dj.url
                FROM approved_jobs aj
                JOIN discovered_jobs dj ON aj.discovered_job_id = dj.id
                WHERE aj.id = ?
            """, (job_id,))
            
            job_row = cursor.fetchone()
            if not job_row:
                return {"success": False, "message": "Job not found"}
            
            job_title, job_description, job_url = job_row
            
        except Exception as e:
            return {"success": False, "message": f"Error fetching job details: {e}"}
        finally:
            if conn:
                conn.close()
        
        # Load configuration
        config_data = load_config_data(CONFIG_FILE_PATH)
        if not config_data:
            return {"success": False, "message": "Configuration not found"}
        
        # Get personal info and resume text
        personal_info = config_data.get("personal_info", {})
        resume_text = config_data.get("resume", {}).get("text", "")
        
        # Validate required information
        if not resume_text or resume_text.strip() == "Paste your default resume text here...\n\nTechnical Skills\n...\n\nProfessional Experience\n...":
            return {"success": False, "message": "Please add your resume text in the Configuration page"}
        
        if not personal_info.get("first_name") or personal_info.get("first_name") == "Your First Name":
            return {"success": False, "message": "Please complete your personal information in the Configuration page"}
        
        # Generate resume
        try:
            doc_bytes, filename = generate_resume(
                job_title=job_title,
                job_description=job_description,
                original_resume=resume_text,
                personal_info=personal_info
            )
            
            # Return the document as a download
            headers = {
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            }
            
            return Response(
                content=doc_bytes,
                headers=headers,
                media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
            
        except ValueError as ve:
            error_msg = str(ve)
            if "API key" in error_msg or "api_key" in error_msg:
                return {"success": False, "message": f"❌ {error_msg}"}
            return {"success": False, "message": str(ve)}
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "invalid_api_key" in error_msg:
                return {"success": False, "message": "❌ Invalid OpenAI API key. Please update your API key in the Configuration page."}
            return {"success": False, "message": f"Error generating resume: {e}"}
            
    except Exception as e:
        return {"success": False, "message": f"Error processing request: {e}"}

@app.post("/api/save-config")
async def api_save_config(request: Request):
    """Save configuration"""
    try:
        form_data = await request.form()
        
        # Build config structure from form data
        config_data = {
            "search_parameters": {
                "locations": [loc.strip() for loc in form_data.get("locations", "").splitlines() if loc.strip()],
                "keywords": [kw.strip() for kw in form_data.get("keywords", "").splitlines() if kw.strip()],
                "exclusion_keywords": [ex.strip() for ex in form_data.get("exclusions", "").splitlines() if ex.strip()],
            },
            "resume": {
                "text": form_data.get("resume_text", "")
            },
            "personal_info": {
                "first_name": form_data.get("first_name", ""),
                "last_name": form_data.get("last_name", ""),
                "phone_number": form_data.get("phone_number", ""),
                "email_address": form_data.get("email_address", ""),
                "linkedin_url": form_data.get("linkedin_url", "")
            },
            "prompts": {
                "evaluation_prompt": form_data.get("ai_prompt", "")
            },
            "api_keys": {
                "openai_api_key": form_data.get("openai_api_key", "")
            },
            "general": {
                "ai_provider": "openai"  # Always set to OpenAI
            }
        }
        
        save_config_data(CONFIG_FILE_PATH, config_data)
        return {"success": True, "message": "Configuration saved successfully"}
    except Exception as e:
        return {"success": False, "message": f"Error saving configuration: {e}"}

# WebSocket endpoint for real-time updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle any incoming WebSocket messages if needed
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Background task for scanning
async def run_scan_background():
    """Run the scan process in the background"""
    global scan_state
    try:
        # Reload config before scanning
        load_config()
        
        # Create stop signal that can be modified
        stop_signal = [False]
        
        # Monitor scan progress and stop requests
        async def monitor_stop_signal():
            while scan_state["is_running"] and not scan_state["stop_requested"]:
                await asyncio.sleep(0.5)  # Check every 500ms
                if scan_state["stop_requested"] or should_stop_scan():
                    stop_signal[0] = True
                    break
        
        # Start the monitor task
        monitor_task = asyncio.create_task(monitor_stop_signal())
        
        # Run scan in a thread to avoid blocking
        import concurrent.futures
        
        def run_scan_sync():
            return scrape_phase(stop_signal)
        
        # Run the scan in a thread pool
        loop = asyncio.get_event_loop()
        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # Submit the scan task
                future = executor.submit(run_scan_sync)
                
                # Wait for completion or cancellation
                while not future.done():
                    if scan_state["stop_requested"]:
                        stop_signal[0] = True
                        # Wait a bit more for graceful shutdown
                        await asyncio.sleep(2)
                        break
                    await asyncio.sleep(0.1)
                
                # Get results if completed
                if future.done():
                    new_jobs, links_examined = future.result(timeout=1)
                else:
                    # If still running, consider it stopped
                    new_jobs, links_examined = 0, 0
                    
        except concurrent.futures.TimeoutError:
            new_jobs, links_examined = 0, 0
        except asyncio.CancelledError:
            stop_signal[0] = True
            new_jobs, links_examined = 0, 0
            raise
        finally:
            monitor_task.cancel()
        
        # Update final state
        scan_state["is_running"] = False
        scan_state["stop_requested"] = False
        
        if stop_signal[0]:
            scan_state["last_message"] = "Scan stopped by user"
            await manager.broadcast(json.dumps({
                "type": "scan_stopped",
                "message": "Scan stopped by user"
            }))
        else:
            scan_state["last_message"] = f"Scan complete. New jobs: {new_jobs}, Links examined: {links_examined}"
            await manager.broadcast(json.dumps({
                "type": "scan_complete",
                "message": scan_state["last_message"],
                "new_jobs": new_jobs,
                "links_examined": links_examined
            }))
        
    except asyncio.CancelledError:
        scan_state["is_running"] = False
        scan_state["stop_requested"] = False
        scan_state["last_message"] = "Scan cancelled"
        
        await manager.broadcast(json.dumps({
            "type": "scan_stopped",
            "message": "Scan cancelled"
        }))
        
    except Exception as e:
        scan_state["is_running"] = False
        scan_state["stop_requested"] = False
        scan_state["last_message"] = f"Scan error: {e}"
        
        await manager.broadcast(json.dumps({
            "type": "scan_error",
            "message": scan_state["last_message"]
        }))

# Database export endpoint
@app.get("/api/export-database")
async def export_database():
    """Export database file"""
    if DB_PATH and DB_PATH.exists():
        return FileResponse(
            path=DB_PATH,
            filename="jobfinder_database.db",
            media_type="application/octet-stream"
        )
    else:
        raise HTTPException(status_code=404, detail="Database file not found")

# Database import endpoint
@app.post("/api/import-database")
async def import_database(db_file: bytes = Form(...)):
    """Import database file"""
    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as temp_file:
            temp_file.write(db_file)
            temp_path = temp_file.name
        
        # Validate database (basic check)
        try:
            test_conn = sqlite3.connect(temp_path)
            test_conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
            test_conn.close()
        except Exception as e:
            os.unlink(temp_path)
            return {"success": False, "message": f"Invalid database file: {e}"}
        
        # Replace current database
        if DB_PATH:
            shutil.move(temp_path, DB_PATH)
            return {"success": True, "message": "Database imported successfully"}
        else:
            os.unlink(temp_path)
            return {"success": False, "message": "Database path not configured"}
            
    except Exception as e:
        return {"success": False, "message": f"Error importing database: {e}"}

# Reload configuration endpoint
@app.post("/api/reload-config")
async def reload_config():
    """Reload configuration from file"""
    try:
        load_config()
        return {"success": True, "message": "Configuration reloaded successfully"}
    except Exception as e:
        return {"success": False, "message": f"Error reloading configuration: {e}"}

# Configuration export endpoint
@app.get("/api/export-config")
async def export_config():
    """Export configuration file"""
    if CONFIG_FILE_PATH and CONFIG_FILE_PATH.exists():
        return FileResponse(
            path=CONFIG_FILE_PATH,
            filename="jobfinder_config.toml",
            media_type="application/toml"
        )
    else:
        raise HTTPException(status_code=404, detail="Configuration file not found")

# Configuration import endpoint
@app.post("/api/import-config")
async def import_config(config_file: bytes = Form(...)):
    """Import configuration file"""
    try:
        import tempfile
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.toml') as temp_file:
            temp_file.write(config_file)
            temp_path = temp_file.name
        
        # Validate configuration (basic check)
        try:
            import toml
            config_data = toml.load(temp_path)
            # Add basic validation here if needed
        except Exception as e:
            os.unlink(temp_path)
            return {"success": False, "message": f"Invalid configuration file: {e}"}
        
        # Replace current configuration
        if CONFIG_FILE_PATH:
            shutil.move(temp_path, CONFIG_FILE_PATH)
            return {"success": True, "message": "Configuration imported successfully"}
        else:
            os.unlink(temp_path)
            return {"success": False, "message": "Configuration path not configured"}
            
    except Exception as e:
        return {"success": False, "message": f"Error importing configuration: {e}"}

# Resume upload and text extraction endpoint
@app.post("/api/upload-resume")
async def upload_resume(resume_file: UploadFile = File(...)):
    """Upload and extract text from resume file (PDF, DOCX, DOC, TXT)"""
    try:
        # Validate file type
        allowed_types = {'.pdf', '.docx', '.doc', '.txt'}
        file_extension = '.' + resume_file.filename.split('.')[-1].lower()
        
        if file_extension not in allowed_types:
            return {"success": False, "message": "Please upload a PDF, DOCX, DOC, or TXT file."}
        
        # Check file size (max 10MB)
        content = await resume_file.read()
        if len(content) > 10 * 1024 * 1024:
            return {"success": False, "message": "File size must be less than 10MB."}
        
        # Extract text based on file type
        extracted_text = ""
        
        if file_extension == '.txt':
            # Plain text file
            try:
                extracted_text = content.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    extracted_text = content.decode('latin-1')
                except UnicodeDecodeError:
                    return {"success": False, "message": "Unable to decode text file. Please ensure it's in UTF-8 format."}
        
        elif file_extension in ['.docx', '.doc']:
            # Word document
            try:
                import tempfile
                import os
                from docx import Document
                
                # Create temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
                    temp_file.write(content)
                    temp_path = temp_file.name
                
                try:
                    # Extract text from DOCX
                    if file_extension == '.docx':
                        doc = Document(temp_path)
                        paragraphs = [paragraph.text for paragraph in doc.paragraphs]
                        extracted_text = '\n'.join(paragraphs)
                    else:
                        # For .doc files, we'd need python-docx2txt or similar
                        # For now, return an error message
                        return {"success": False, "message": "DOC files are not currently supported. Please convert to DOCX or PDF format."}
                
                finally:
                    # Clean up temporary file
                    os.unlink(temp_path)
                    
            except ImportError:
                return {"success": False, "message": "Word document processing not available. Please install python-docx."}
            except Exception as e:
                return {"success": False, "message": f"Error processing Word document: {str(e)}"}
        
        elif file_extension == '.pdf':
            # PDF file
            try:
                import tempfile
                import os
                try:
                    import PyPDF2
                    
                    # Create temporary file
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                        temp_file.write(content)
                        temp_path = temp_file.name
                    
                    try:
                        # Extract text from PDF
                        with open(temp_path, 'rb') as pdf_file:
                            pdf_reader = PyPDF2.PdfReader(pdf_file)
                            pages_text = []
                            
                            for page in pdf_reader.pages:
                                pages_text.append(page.extract_text())
                            
                            extracted_text = '\n'.join(pages_text)
                    
                    finally:
                        # Clean up temporary file
                        os.unlink(temp_path)
                        
                except ImportError:
                    try:
                        # Fallback to pdfplumber
                        import pdfplumber
                        import io
                        
                        with pdfplumber.open(io.BytesIO(content)) as pdf:
                            pages_text = []
                            for page in pdf.pages:
                                text = page.extract_text()
                                if text:
                                    pages_text.append(text)
                            extracted_text = '\n'.join(pages_text)
                            
                    except ImportError:
                        return {"success": False, "message": "PDF processing not available. Please install PyPDF2 or pdfplumber."}
                        
            except Exception as e:
                return {"success": False, "message": f"Error processing PDF: {str(e)}"}
        
        # Clean up extracted text
        if extracted_text:
            # Remove excessive whitespace
            import re
            extracted_text = re.sub(r'\n\s*\n', '\n\n', extracted_text)  # Multiple newlines to double newline
            extracted_text = re.sub(r' +', ' ', extracted_text)  # Multiple spaces to single space
            extracted_text = extracted_text.strip()
        
        if not extracted_text or len(extracted_text.strip()) < 50:
            return {"success": False, "message": "Could not extract readable text from the file. Please check the file format or try a different file."}
        
        return {
            "success": True, 
            "text": extracted_text,
            "message": f"Successfully extracted {len(extracted_text)} characters from {resume_file.filename}"
        }
        
    except Exception as e:
        return {"success": False, "message": f"Error processing file: {str(e)}"}

if __name__ == "__main__":
    # For development
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)