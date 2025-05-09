import streamlit as st
import sqlite3
import pandas as pd
from pathlib import Path
import html

# It's good practice for pages to be self-contained or import from a shared utility module.
# For now, we'll duplicate the DB_PATH logic and fetch function,
# but long-term, database access functions could be in a shared `utils.py` or similar.

# --- Database Path (consistent with dashboard.py) ---
try:
    # This assumes dashboard.py (and thus its directory) is the root for finding database.py
    # If running `streamlit run dashboard.py`, then relative paths from dashboard.py are key.
    # For pages, Streamlit sets the CWD to the project root.
    from utils import DB_PATH 
except ImportError:
    st.error("Error: Could not import DB_PATH from utils.py.")
    # Fallback, assuming 'pages' is one level down from project root where database.db is
    DB_PATH = Path(__file__).resolve().parent.parent / "database.db"
    if not DB_PATH.exists():
        st.warning(f"Fallback DB_PATH: {DB_PATH} does not exist. App may not function.")

# Attempt to import the new archive function
try:
    from database import archive_all_applied_jobs
except ImportError:
    archive_all_applied_jobs = None # Fallback
    st.error("Could not import archive_all_applied_jobs function from database.py. Archiving will not work.")


def fetch_only_applied_jobs_data():
    """Fetches jobs that have been marked as applied and are NOT archived."""
    if not DB_PATH.exists():
        st.error(f"Database file not found at: {DB_PATH}")
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
            aj.date_applied IS NOT NULL AND (aj.is_archived = FALSE OR aj.is_archived IS NULL) -- Key condition: only fetch applied and not archived jobs
        ORDER BY
            aj.date_applied DESC; -- Order by when applied
        """
        df = pd.read_sql_query(query, conn)
        
        # Format dates
        if 'date_approved' in df.columns:
            try: df['date_approved'] = pd.to_datetime(df['date_approved']).dt.strftime('%Y-%m-%d %H:%M:%S')
            except: pass
        if 'date_applied' in df.columns:
            try: df['date_applied'] = pd.to_datetime(df['date_applied']).dt.strftime('%Y-%m-%d %H:%M:%S')
            except: pass
        return df
    except sqlite3.Error as e:
        st.error(f"SQLite error fetching applied jobs: {e}")
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()

if 'applied_action_message' not in st.session_state:
    st.session_state.applied_action_message = ""

# --- Sidebar Actions for Applied Jobs ---
with st.sidebar:
    st.header("Applied Jobs Actions")
    if archive_all_applied_jobs: # Check if function was imported
        if st.button("🗑️ Archive All Applied Jobs", key="archive_all_applied_sidebar_button", help="Mark all currently visible applied jobs as archived.", use_container_width=True, type="primary"):
            try:
                archived_count = archive_all_applied_jobs()
                st.session_state.applied_action_message = f"Successfully archived {archived_count} applied jobs."
                st.rerun()
            except Exception as e:
                st.session_state.applied_action_message = f"Error archiving applied jobs: {e}"
                st.rerun()
    else:
        st.sidebar.error("Archive functionality is unavailable.")

# --- Streamlit Page Layout for "Applied Jobs" ---
# The global config from 01_Dashboard.py will apply.

st.title("✅ JobFinder - Applied Jobs")

if st.session_state.applied_action_message:
    st.toast(st.session_state.applied_action_message, icon="ℹ️")
    st.session_state.applied_action_message = "" # Clear message after displaying

st.markdown("This page lists all jobs that you have marked as 'applied' and have not been archived.")

applied_df = fetch_only_applied_jobs_data()

if applied_df.empty:
    st.info("No jobs have been marked as 'applied' yet, or an error occurred fetching them.")
else:
    st.metric(label="Total Jobs Applied To", value=len(applied_df))
    st.markdown("---")

    # Displaying applied jobs - similar to approved jobs list but without action buttons for now
    # You might want different columns or actions on this page later.
    for index, row in applied_df.iterrows():
        title_escaped = html.escape(str(row['title'] if pd.notna(row['title']) else 'N/A'))
        url_filled = str(row['url'] if pd.notna(row['url']) else '#')
        
        st.markdown(f"### <a href='{url_filled}' target='_blank'>{title_escaped}</a>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            st.caption(f"Applied On: {row.get('date_applied', 'N/A')}")
            st.caption(f"Originally Approved: {row.get('date_approved', 'N/A')}")
        with col2:
            st.caption(f"Location: {row.get('location', 'N/A')} | Keyword: {row.get('keyword', 'N/A')}")
        
        with st.expander("Reason for Original Approval"):
            st.markdown(f"<div style='word-wrap: break-word; white-space: pre-wrap;'>{html.escape(str(row.get('reason', 'N/A')))}</div>", unsafe_allow_html=True)
        st.markdown("---")
