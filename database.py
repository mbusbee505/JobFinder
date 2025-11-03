# database.py - Single User Database Operations

from pathlib import Path
import sqlite3
from contextlib import contextmanager
from typing import Iterable, Dict, Any, Optional, Tuple, List
import re
import json
from utils import DB_PATH

# Regular expression for extracting job IDs
_JOB_ID_RE = re.compile(r"/jobs/view/(?:[^/?]*-)?(\d+)(?:[/?]|$)")

# Admin user ID for single-user mode (compatibility with multi-user schema)
ADMIN_USER_ID = 1

# -- connection helpers ------------------------------------------------------
@contextmanager
def get_conn():
    """Context‑managed connection that commits on success and rolls back on error."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row       # fetch rows as dict‑like objects
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Initialize database with single-user compatibility"""
    try:
        with get_conn() as conn:
            # Verify that the tables exist (keeping multi-user schema for compatibility)
            tables = conn.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name IN ('users', 'discovered_jobs', 'approved_jobs', 'user_configs', 'user_scan_control')
            """).fetchall()

            table_names = [t['name'] for t in tables]
            required_tables = ['users', 'discovered_jobs', 'approved_jobs', 'user_configs', 'user_scan_control']

            missing_tables = [t for t in required_tables if t not in table_names]

            if missing_tables:
                # Create the missing tables for single-user mode
                create_single_user_tables(conn)

            # Migrate existing tables to add missing columns
            migrate_database_schema(conn)

            # Ensure admin user exists
            ensure_admin_user(conn)
            print("✅ Single-user database initialized")

    except Exception as e:
        print(f"Error initializing database: {e}")
        raise


def migrate_database_schema(conn):
    """Migrate existing database schema to add missing columns"""
    try:
        # Check if user_scan_control table exists
        table_exists = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='user_scan_control'
        """).fetchone()

        if table_exists:
            # Check if stop_scan_flag column exists
            columns = conn.execute("PRAGMA table_info(user_scan_control)").fetchall()
            column_names = [col['name'] for col in columns]

            if 'stop_scan_flag' not in column_names:
                conn.execute("ALTER TABLE user_scan_control ADD COLUMN stop_scan_flag BOOLEAN DEFAULT FALSE")
                print("Added stop_scan_flag column to user_scan_control table")

            if 'scan_active' not in column_names:
                conn.execute("ALTER TABLE user_scan_control ADD COLUMN scan_active BOOLEAN DEFAULT FALSE")
                print("Added scan_active column to user_scan_control table")

    except Exception as e:
        print(f"Error migrating database schema: {e}")


def create_single_user_tables(conn):
    """Create the necessary tables for single-user mode"""
    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        google_id TEXT UNIQUE,
        email TEXT UNIQUE,
        name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS discovered_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        job_id INTEGER NOT NULL,
        url TEXT NOT NULL,
        location TEXT NOT NULL,
        keyword TEXT NOT NULL,
        title TEXT,
        description TEXT,
        analyzed BOOLEAN DEFAULT FALSE,
        date_discovered TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        UNIQUE(user_id, job_id)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS approved_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        discovered_job_id INTEGER NOT NULL,
        reason TEXT,
        date_approved TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        date_applied TIMESTAMP NULL,
        is_archived BOOLEAN DEFAULT FALSE,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (discovered_job_id) REFERENCES discovered_jobs(id),
        UNIQUE(user_id, discovered_job_id)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS user_configs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        config_key TEXT NOT NULL,
        config_value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        UNIQUE(user_id, config_key)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS user_scan_control (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        stop_scan_flag BOOLEAN DEFAULT FALSE,
        scan_active BOOLEAN DEFAULT FALSE,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)


def ensure_admin_user(conn):
    """Ensure the admin user exists for single-user mode"""
    admin = conn.execute("SELECT id FROM users WHERE id = ?", (ADMIN_USER_ID,)).fetchone()
    if not admin:
        conn.execute("""
        INSERT INTO users (id, email, name)
        VALUES (?, 'admin@localhost', 'Admin User')
        """, (ADMIN_USER_ID,))


# -- Single-user functions (simplified from multi-user wrappers) --------------

def insert_stub(job_id: int, url: str, location: str, keyword: str) -> bool:
    """Insert a new job stub"""
    sql = """
    INSERT OR IGNORE INTO discovered_jobs (user_id, job_id, url, location, keyword)
    VALUES (?, ?, ?, ?, ?);
    """
    try:
        with get_conn() as conn:
            cursor = conn.execute(sql, (ADMIN_USER_ID, job_id, url, location, keyword))
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error inserting job stub: {e}")
        return False


def row_missing_details(job_id: int) -> bool:
    """Check if job is missing title/description"""
    sql = "SELECT title FROM discovered_jobs WHERE user_id = ? AND job_id = ?;"
    with get_conn() as conn:
        row = conn.execute(sql, (ADMIN_USER_ID, job_id)).fetchone()
        return row is None or row['title'] is None


def update_details(job_id: int, title: Optional[str], desc: Optional[str]) -> None:
    """Update job title and description"""
    sql = """
    UPDATE discovered_jobs
    SET title = ?, description = ?
    WHERE user_id = ? AND job_id = ?;
    """
    with get_conn() as conn:
        conn.execute(sql, (title, desc, ADMIN_USER_ID, job_id))


def mark_job_as_analyzed(job_id: int) -> None:
    """Mark job as analyzed"""
    sql = "UPDATE discovered_jobs SET analyzed = TRUE WHERE user_id = ? AND job_id = ?;"
    with get_conn() as conn:
        conn.execute(sql, (ADMIN_USER_ID, job_id))


def approve_job(linkedin_job_id: int, reason: str) -> bool:
    """Approve a job"""
    try:
        with get_conn() as conn:
            # Get the discovered job
            discovered_job = conn.execute("""
                SELECT id FROM discovered_jobs
                WHERE user_id = ? AND job_id = ?
            """, (ADMIN_USER_ID, linkedin_job_id)).fetchone()

            if not discovered_job:
                return False

            # Insert into approved_jobs
            conn.execute("""
                INSERT OR IGNORE INTO approved_jobs (user_id, discovered_job_id, reason)
                VALUES (?, ?, ?)
            """, (ADMIN_USER_ID, discovered_job['id'], reason))

            return True
    except Exception as e:
        print(f"Error approving job: {e}")
        return False


def mark_job_as_applied(approved_job_pk: int) -> bool:
    """Mark an approved job as applied and automatically archive it"""
    sql = """
    UPDATE approved_jobs
    SET date_applied = CURRENT_TIMESTAMP, is_archived = TRUE
    WHERE user_id = ? AND id = ? AND date_applied IS NULL;
    """
    try:
        with get_conn() as conn:
            cursor = conn.execute(sql, (ADMIN_USER_ID, approved_job_pk))
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error marking job as applied: {e}")
        return False


def delete_approved_job(approved_job_pk: int) -> bool:
    """Delete an approved job"""
    sql = "DELETE FROM approved_jobs WHERE user_id = ? AND id = ?;"
    try:
        with get_conn() as conn:
            cursor = conn.execute(sql, (ADMIN_USER_ID, approved_job_pk))
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error deleting approved job: {e}")
        return False


def clear_all_approved_jobs() -> int:
    """Clear all approved jobs"""
    sql = "DELETE FROM approved_jobs WHERE user_id = ?;"
    with get_conn() as conn:
        cursor = conn.execute(sql, (ADMIN_USER_ID,))
        return cursor.rowcount


def clear_all_discovered_jobs() -> int:
    """Clear all discovered jobs"""
    try:
        with get_conn() as conn:
            # Delete approved jobs first (foreign key constraint)
            conn.execute("DELETE FROM approved_jobs WHERE user_id = ?", (ADMIN_USER_ID,))
            # Then delete discovered jobs
            cursor = conn.execute("DELETE FROM discovered_jobs WHERE user_id = ?", (ADMIN_USER_ID,))
            return cursor.rowcount
    except Exception as e:
        print(f"Error clearing discovered jobs: {e}")
        return 0


def archive_all_applied_jobs() -> int:
    """Archive all applied jobs"""
    sql = """
    UPDATE approved_jobs
    SET is_archived = TRUE
    WHERE user_id = ? AND date_applied IS NOT NULL AND (is_archived IS NULL OR is_archived = FALSE);
    """
    with get_conn() as conn:
        cursor = conn.execute(sql, (ADMIN_USER_ID,))
        return cursor.rowcount


# -- Scan control functions --

def set_stop_scan_flag(stop: bool) -> None:
    """Set the stop scan flag"""
    sql = """
    INSERT OR REPLACE INTO user_scan_control (user_id, stop_scan_flag)
    VALUES (?, ?);
    """
    with get_conn() as conn:
        conn.execute(sql, (ADMIN_USER_ID, stop))


def should_stop_scan() -> bool:
    """Check if scan should be stopped"""
    sql = "SELECT stop_scan_flag FROM user_scan_control WHERE user_id = ?;"
    with get_conn() as conn:
        row = conn.execute(sql, (ADMIN_USER_ID,)).fetchone()
        return bool(row['stop_scan_flag']) if row else False


def set_scan_active(active: bool) -> None:
    """Set scan active status"""
    sql = """
    INSERT OR REPLACE INTO user_scan_control (user_id, scan_active)
    VALUES (?, ?);
    """
    with get_conn() as conn:
        conn.execute(sql, (ADMIN_USER_ID, active))


def is_scan_active() -> bool:
    """Check if scan is active"""
    sql = "SELECT scan_active FROM user_scan_control WHERE user_id = ?;"
    with get_conn() as conn:
        row = conn.execute(sql, (ADMIN_USER_ID,)).fetchone()
        return bool(row['scan_active']) if row else False


def get_scan_status() -> Dict[str, Any]:
    """Get comprehensive scan status"""
    try:
        with get_conn() as conn:
            # Get scan control info
            scan_row = conn.execute("""
                SELECT stop_scan_flag, scan_active
                FROM user_scan_control
                WHERE user_id = ?
            """, (ADMIN_USER_ID,)).fetchone()

            # Get job counts
            stats = conn.execute("""
                SELECT
                    COUNT(*) as total_discovered,
                    (SELECT COUNT(*) FROM approved_jobs WHERE user_id = ? AND (is_archived IS NULL OR is_archived = FALSE)) as total_approved,
                    (SELECT COUNT(*) FROM approved_jobs WHERE user_id = ? AND date_applied IS NOT NULL AND (is_archived IS NULL OR is_archived = FALSE)) as total_applied,
                    (SELECT COUNT(*) FROM discovered_jobs WHERE user_id = ? AND analyzed = TRUE) as total_analyzed
                FROM discovered_jobs WHERE user_id = ?
            """, (ADMIN_USER_ID, ADMIN_USER_ID, ADMIN_USER_ID, ADMIN_USER_ID)).fetchone()

            return {
                'is_active': bool(scan_row['scan_active']) if scan_row else False,
                'should_stop': bool(scan_row['stop_scan_flag']) if scan_row else False,
                'total_discovered': stats['total_discovered'],
                'total_approved': stats['total_approved'],
                'total_applied': stats['total_applied'],
                'total_analyzed': stats['total_analyzed']
            }
    except Exception as e:
        print(f"Error getting scan status: {e}")
        return {
            'is_active': False,
            'should_stop': False,
            'total_discovered': 0,
            'total_approved': 0,
            'total_applied': 0,
            'total_analyzed': 0
        }


# -- Utility functions --

def get_user_job_count(user_id: int) -> int:
    """Get the total count of discovered jobs for a user"""
    with get_conn() as conn:
        result = conn.execute(
            "SELECT COUNT(*) as count FROM discovered_jobs WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        return result['count'] if result else 0


def extract_job_id_from_url(url: str) -> Optional[int]:
    """Extract LinkedIn job ID from URL"""
    match = _JOB_ID_RE.search(url)
    return int(match.group(1)) if match else None


def get_unanalyzed_jobs() -> List[Tuple[int, str]]:
    """Get jobs that haven't been analyzed yet"""
    sql = """
    SELECT job_id, description
    FROM discovered_jobs
    WHERE user_id = ? AND analyzed = FALSE AND description IS NOT NULL;
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (ADMIN_USER_ID,)).fetchall()
        return [(row['job_id'], row['description']) for row in rows]


def get_jobs_missing_content() -> List[Tuple[int, str]]:
    """Get jobs missing title or description for scraping"""
    sql = """
    SELECT job_id, url
    FROM discovered_jobs
    WHERE user_id = ? AND (title IS NULL OR description IS NULL);
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (ADMIN_USER_ID,)).fetchall()
        return [(row['job_id'], row['url']) for row in rows]


# Statistics functions for the new stats page
def get_archived_jobs() -> List[Dict[str, Any]]:
    """Get all archived applied jobs"""
    sql = """
    SELECT
        a.id as approved_id,
        a.date_approved,
        a.reason,
        a.date_applied,
        d.job_id,
        d.title,
        d.url,
        d.location,
        d.keyword,
        d.description
    FROM approved_jobs a
    JOIN discovered_jobs d ON a.discovered_job_id = d.id
    WHERE a.user_id = ? AND a.is_archived = TRUE
    ORDER BY a.date_applied DESC
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (ADMIN_USER_ID,)).fetchall()
        return [dict(row) for row in rows]


def get_job_statistics() -> Dict[str, Any]:
    """Get comprehensive job statistics for dashboard"""
    try:
        with get_conn() as conn:
            # Basic counts
            basic_stats = conn.execute("""
                SELECT
                    COUNT(*) as total_discovered,
                    COUNT(CASE WHEN analyzed = TRUE THEN 1 END) as total_analyzed,
                    COUNT(CASE WHEN title IS NOT NULL AND description IS NOT NULL THEN 1 END) as total_with_details
                FROM discovered_jobs WHERE user_id = ?
            """, (ADMIN_USER_ID,)).fetchone()

            # Approved job stats
            approved_stats = conn.execute("""
                SELECT
                    COUNT(*) as total_approved,
                    COUNT(CASE WHEN date_applied IS NOT NULL THEN 1 END) as total_applied,
                    COUNT(CASE WHEN is_archived = TRUE THEN 1 END) as total_archived
                FROM approved_jobs WHERE user_id = ?
            """, (ADMIN_USER_ID,)).fetchone()

            # Jobs by location (for approved jobs)
            location_stats = conn.execute("""
                SELECT location, COUNT(*) as count
                FROM discovered_jobs WHERE user_id = ?
                GROUP BY location
                ORDER BY count DESC
                LIMIT 10
            """, (ADMIN_USER_ID,)).fetchall()

            # Jobs by keyword (for approved jobs)
            keyword_stats = conn.execute("""
                SELECT keyword, COUNT(*) as count
                FROM discovered_jobs WHERE user_id = ?
                GROUP BY keyword
                ORDER BY count DESC
                LIMIT 10
            """, (ADMIN_USER_ID,)).fetchall()

            # Applied jobs breakdown by location
            applied_by_location = conn.execute("""
                SELECT d.location, COUNT(*) as count
                FROM approved_jobs a
                JOIN discovered_jobs d ON a.discovered_job_id = d.id
                WHERE a.user_id = ? AND a.date_applied IS NOT NULL
                GROUP BY d.location
                ORDER BY count DESC
                LIMIT 10
            """, (ADMIN_USER_ID,)).fetchall()

            # Applied jobs breakdown by keyword
            applied_by_keyword = conn.execute("""
                SELECT d.keyword, COUNT(*) as count
                FROM approved_jobs a
                JOIN discovered_jobs d ON a.discovered_job_id = d.id
                WHERE a.user_id = ? AND a.date_applied IS NOT NULL
                GROUP BY d.keyword
                ORDER BY count DESC
                LIMIT 10
            """, (ADMIN_USER_ID,)).fetchall()

            # Approved jobs breakdown by location
            approved_by_location = conn.execute("""
                SELECT d.location, COUNT(*) as count
                FROM approved_jobs a
                JOIN discovered_jobs d ON a.discovered_job_id = d.id
                WHERE a.user_id = ?
                GROUP BY d.location
                ORDER BY count DESC
                LIMIT 10
            """, (ADMIN_USER_ID,)).fetchall()

            # Approved jobs breakdown by keyword
            approved_by_keyword = conn.execute("""
                SELECT d.keyword, COUNT(*) as count
                FROM approved_jobs a
                JOIN discovered_jobs d ON a.discovered_job_id = d.id
                WHERE a.user_id = ?
                GROUP BY d.keyword
                ORDER BY count DESC
                LIMIT 10
            """, (ADMIN_USER_ID,)).fetchall()

            # Conversion rates by location
            conversion_by_location = conn.execute("""
                SELECT
                    d.location,
                    COUNT(DISTINCT d.id) as discovered,
                    COUNT(DISTINCT CASE WHEN a.id IS NOT NULL THEN a.id END) as approved,
                    COUNT(DISTINCT CASE WHEN a.date_applied IS NOT NULL THEN a.id END) as applied
                FROM discovered_jobs d
                LEFT JOIN approved_jobs a ON d.id = a.discovered_job_id AND a.user_id = ?
                WHERE d.user_id = ?
                GROUP BY d.location
                HAVING COUNT(DISTINCT d.id) > 0
                ORDER BY discovered DESC
                LIMIT 10
            """, (ADMIN_USER_ID, ADMIN_USER_ID)).fetchall()

            # Conversion rates by keyword
            conversion_by_keyword = conn.execute("""
                SELECT
                    d.keyword,
                    COUNT(DISTINCT d.id) as discovered,
                    COUNT(DISTINCT CASE WHEN a.id IS NOT NULL THEN a.id END) as approved,
                    COUNT(DISTINCT CASE WHEN a.date_applied IS NOT NULL THEN a.id END) as applied
                FROM discovered_jobs d
                LEFT JOIN approved_jobs a ON d.id = a.discovered_job_id AND a.user_id = ?
                WHERE d.user_id = ?
                GROUP BY d.keyword
                HAVING COUNT(DISTINCT d.id) > 0
                ORDER BY discovered DESC
                LIMIT 10
            """, (ADMIN_USER_ID, ADMIN_USER_ID)).fetchall()

            # Recent activity (last 30 days)
            recent_activity = conn.execute("""
                SELECT
                    DATE(date_discovered) as date,
                    COUNT(*) as discovered_count
                FROM discovered_jobs
                WHERE user_id = ? AND date_discovered >= datetime('now', '-30 days')
                GROUP BY DATE(date_discovered)
                ORDER BY date DESC
            """, (ADMIN_USER_ID,)).fetchall()

            # Application activity (last 30 days)
            application_activity = conn.execute("""
                SELECT
                    DATE(date_applied) as date,
                    COUNT(*) as applied_count
                FROM approved_jobs
                WHERE user_id = ? AND date_applied IS NOT NULL
                  AND date_applied >= datetime('now', '-30 days')
                GROUP BY DATE(date_applied)
                ORDER BY date DESC
            """, (ADMIN_USER_ID,)).fetchall()

            return {
                'basic': dict(basic_stats),
                'approved': dict(approved_stats),
                'by_location': [dict(row) for row in location_stats],
                'by_keyword': [dict(row) for row in keyword_stats],
                'applied_by_location': [dict(row) for row in applied_by_location],
                'applied_by_keyword': [dict(row) for row in applied_by_keyword],
                'approved_by_location': [dict(row) for row in approved_by_location],
                'approved_by_keyword': [dict(row) for row in approved_by_keyword],
                'conversion_by_location': [dict(row) for row in conversion_by_location],
                'conversion_by_keyword': [dict(row) for row in conversion_by_keyword],
                'recent_activity': [dict(row) for row in recent_activity],
                'application_activity': [dict(row) for row in application_activity]
            }
    except Exception as e:
        print(f"Error getting job statistics: {e}")
        return {
            'basic': {'total_discovered': 0, 'total_analyzed': 0, 'total_with_details': 0},
            'approved': {'total_approved': 0, 'total_applied': 0, 'total_archived': 0},
            'by_location': [],
            'by_keyword': [],
            'applied_by_location': [],
            'applied_by_keyword': [],
            'approved_by_location': [],
            'approved_by_keyword': [],
            'conversion_by_location': [],
            'conversion_by_keyword': [],
            'recent_activity': [],
            'application_activity': []
        }