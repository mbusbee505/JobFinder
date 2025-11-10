# database_multiuser.py - Multi-user database operations

from pathlib import Path
import sqlite3
from contextlib import contextmanager
from typing import Iterable, Dict, Any, Optional, Tuple, List
import re
import json
from datetime import datetime

DB_PATH = "jobfinder.db"

# Regular expression for extracting job IDs
_JOB_ID_RE = re.compile(r"/jobs/view/(?:[^/?]*-)?(\d+)(?:[/?]|$)")

# -- connection helpers ------------------------------------------------------
@contextmanager
def get_conn():
    """Context‑managed connection that commits on success and rolls back on error."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_multiuser_db() -> None:
    """Initialize database with multi-user support"""
    try:
        with get_conn() as conn:
            # Create users table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                is_admin BOOLEAN DEFAULT FALSE,
                is_approved BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # Create discovered_jobs table with user_id
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
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, job_id)
            )
            """)

            # Create index for faster queries
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_discovered_jobs_user_id
            ON discovered_jobs(user_id)
            """)

            # Create approved_jobs table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS approved_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                discovered_job_id INTEGER NOT NULL,
                reason TEXT,
                date_approved TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_applied TIMESTAMP NULL,
                is_archived BOOLEAN DEFAULT FALSE,
                is_dismissed BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (discovered_job_id) REFERENCES discovered_jobs(id) ON DELETE CASCADE,
                UNIQUE(user_id, discovered_job_id)
            )
            """)

            # Create index for faster queries
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_approved_jobs_user_id
            ON approved_jobs(user_id)
            """)

            # Add is_dismissed column if it doesn't exist (migration)
            try:
                conn.execute("SELECT is_dismissed FROM approved_jobs LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute("ALTER TABLE approved_jobs ADD COLUMN is_dismissed BOOLEAN DEFAULT FALSE")
                print("✅ Added is_dismissed column to approved_jobs table")

            # Create user_configs table for per-user configuration
            conn.execute("""
            CREATE TABLE IF NOT EXISTS user_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                config_key TEXT NOT NULL,
                config_value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, config_key)
            )
            """)

            # Create user_scan_control table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS user_scan_control (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                stop_scan_flag BOOLEAN DEFAULT FALSE,
                scan_active BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """)

            # Create user_presets table for configuration presets
            conn.execute("""
            CREATE TABLE IF NOT EXISTS user_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                preset_name TEXT NOT NULL,
                display_name TEXT,
                description TEXT,
                config_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, preset_name)
            )
            """)

            print("✅ Multi-user database initialized")

    except Exception as e:
        print(f"Error initializing database: {e}")
        raise


# -- User-scoped database operations ------------------------------------------

def insert_stub(user_id: int, job_id: int, url: str, location: str, keyword: str) -> bool:
    """Insert a new job stub for a specific user"""
    sql = """
    INSERT OR IGNORE INTO discovered_jobs (user_id, job_id, url, location, keyword)
    VALUES (?, ?, ?, ?, ?);
    """
    try:
        with get_conn() as conn:
            cursor = conn.execute(sql, (user_id, job_id, url, location, keyword))
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error inserting job stub: {e}")
        return False


def row_missing_details(user_id: int, job_id: int) -> bool:
    """Check if job is missing title/description for a specific user"""
    sql = "SELECT title FROM discovered_jobs WHERE user_id = ? AND job_id = ?;"
    with get_conn() as conn:
        row = conn.execute(sql, (user_id, job_id)).fetchone()
        return row is None or row['title'] is None


def update_details(user_id: int, job_id: int, title: Optional[str], desc: Optional[str]) -> None:
    """Update job title and description for a specific user"""
    sql = """
    UPDATE discovered_jobs
    SET title = ?, description = ?
    WHERE user_id = ? AND job_id = ?;
    """
    with get_conn() as conn:
        conn.execute(sql, (title, desc, user_id, job_id))


def mark_job_as_analyzed(user_id: int, job_id: int) -> None:
    """Mark job as analyzed for a specific user"""
    sql = "UPDATE discovered_jobs SET analyzed = TRUE WHERE user_id = ? AND job_id = ?;"
    with get_conn() as conn:
        conn.execute(sql, (user_id, job_id))


def approve_job(user_id: int, linkedin_job_id: int, reason: str) -> bool:
    """Approve a job for a specific user"""
    try:
        with get_conn() as conn:
            discovered_job = conn.execute("""
                SELECT id FROM discovered_jobs
                WHERE user_id = ? AND job_id = ?
            """, (user_id, linkedin_job_id)).fetchone()

            if not discovered_job:
                return False

            conn.execute("""
                INSERT OR IGNORE INTO approved_jobs (user_id, discovered_job_id, reason)
                VALUES (?, ?, ?)
            """, (user_id, discovered_job['id'], reason))

            return True
    except Exception as e:
        print(f"Error approving job: {e}")
        return False


def mark_job_as_applied(user_id: int, approved_job_pk: int) -> bool:
    """Mark an approved job as applied and automatically archive it"""
    sql = """
    UPDATE approved_jobs
    SET date_applied = CURRENT_TIMESTAMP, is_archived = TRUE
    WHERE user_id = ? AND id = ? AND date_applied IS NULL;
    """
    try:
        with get_conn() as conn:
            cursor = conn.execute(sql, (user_id, approved_job_pk))
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error marking job as applied: {e}")
        return False


def delete_approved_job(user_id: int, approved_job_pk: int) -> bool:
    """Dismiss an approved job for a specific user (soft delete)"""
    sql = """
    UPDATE approved_jobs
    SET is_dismissed = TRUE
    WHERE user_id = ? AND id = ?;
    """
    try:
        with get_conn() as conn:
            cursor = conn.execute(sql, (user_id, approved_job_pk))
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error dismissing approved job: {e}")
        return False


def clear_all_approved_jobs(user_id: int) -> int:
    """Clear all approved jobs for a specific user"""
    sql = "DELETE FROM approved_jobs WHERE user_id = ?;"
    with get_conn() as conn:
        cursor = conn.execute(sql, (user_id,))
        return cursor.rowcount


def clear_all_discovered_jobs(user_id: int) -> int:
    """Clear all discovered jobs for a specific user"""
    try:
        with get_conn() as conn:
            conn.execute("DELETE FROM approved_jobs WHERE user_id = ?", (user_id,))
            cursor = conn.execute("DELETE FROM discovered_jobs WHERE user_id = ?", (user_id,))
            return cursor.rowcount
    except Exception as e:
        print(f"Error clearing discovered jobs: {e}")
        return 0


def archive_all_applied_jobs(user_id: int) -> int:
    """Archive all applied jobs for a specific user"""
    sql = """
    UPDATE approved_jobs
    SET is_archived = TRUE
    WHERE user_id = ? AND date_applied IS NOT NULL AND (is_archived IS NULL OR is_archived = FALSE) AND (is_dismissed IS NULL OR is_dismissed = FALSE);
    """
    with get_conn() as conn:
        cursor = conn.execute(sql, (user_id,))
        return cursor.rowcount


# -- Scan control functions --

def set_stop_scan_flag(user_id: int, stop: bool) -> None:
    """Set the stop scan flag for a specific user"""
    sql = """
    INSERT OR REPLACE INTO user_scan_control (user_id, stop_scan_flag)
    VALUES (?, ?);
    """
    with get_conn() as conn:
        conn.execute(sql, (user_id, stop))


def should_stop_scan(user_id: int) -> bool:
    """Check if scan should be stopped for a specific user"""
    sql = "SELECT stop_scan_flag FROM user_scan_control WHERE user_id = ?;"
    with get_conn() as conn:
        row = conn.execute(sql, (user_id,)).fetchone()
        return bool(row['stop_scan_flag']) if row else False


def set_scan_active(user_id: int, active: bool) -> None:
    """Set scan active status for a specific user"""
    sql = """
    INSERT OR REPLACE INTO user_scan_control (user_id, scan_active)
    VALUES (?, ?);
    """
    with get_conn() as conn:
        conn.execute(sql, (user_id, active))


def is_scan_active(user_id: int) -> bool:
    """Check if scan is active for a specific user"""
    sql = "SELECT scan_active FROM user_scan_control WHERE user_id = ?;"
    with get_conn() as conn:
        row = conn.execute(sql, (user_id,)).fetchone()
        return bool(row['scan_active']) if row else False


def get_scan_status(user_id: int) -> Dict[str, Any]:
    """Get comprehensive scan status for a specific user"""
    try:
        with get_conn() as conn:
            scan_row = conn.execute("""
                SELECT stop_scan_flag, scan_active
                FROM user_scan_control
                WHERE user_id = ?
            """, (user_id,)).fetchone()

            stats = conn.execute("""
                SELECT
                    COUNT(*) as total_discovered,
                    (SELECT COUNT(*) FROM approved_jobs WHERE user_id = ? AND (is_archived IS NULL OR is_archived = FALSE) AND (is_dismissed IS NULL OR is_dismissed = FALSE)) as total_approved,
                    (SELECT COUNT(*) FROM approved_jobs WHERE user_id = ? AND date_applied IS NOT NULL AND (is_archived IS NULL OR is_archived = FALSE)) as total_applied,
                    (SELECT COUNT(*) FROM discovered_jobs WHERE user_id = ? AND analyzed = TRUE) as total_analyzed
                FROM discovered_jobs WHERE user_id = ?
            """, (user_id, user_id, user_id, user_id)).fetchone()

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


def get_user_job_count(user_id: int) -> int:
    """Get the total count of discovered jobs for a specific user"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as count FROM discovered_jobs WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        return row['count'] if row else 0


# -- Utility functions --

def get_unanalyzed_jobs(user_id: int) -> List[Tuple[int, str]]:
    """Get jobs that haven't been analyzed yet for a specific user"""
    sql = """
    SELECT job_id, description
    FROM discovered_jobs
    WHERE user_id = ? AND analyzed = FALSE AND description IS NOT NULL;
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (user_id,)).fetchall()
        return [(row['job_id'], row['description']) for row in rows]


def get_jobs_missing_content(user_id: int) -> List[Tuple[int, str]]:
    """Get jobs missing title or description for scraping"""
    sql = """
    SELECT job_id, url
    FROM discovered_jobs
    WHERE user_id = ? AND (title IS NULL OR description IS NULL);
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (user_id,)).fetchall()
        return [(row['job_id'], row['url']) for row in rows]


def get_archived_jobs(user_id: int) -> List[Dict[str, Any]]:
    """Get all archived applied jobs for a specific user"""
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
        rows = conn.execute(sql, (user_id,)).fetchall()
        return [dict(row) for row in rows]


def get_job_statistics(user_id: int) -> Dict[str, Any]:
    """Get comprehensive job statistics for a specific user"""
    try:
        with get_conn() as conn:
            basic_stats = conn.execute("""
                SELECT
                    COUNT(*) as total_discovered,
                    COUNT(CASE WHEN analyzed = TRUE THEN 1 END) as total_analyzed,
                    COUNT(CASE WHEN title IS NOT NULL AND description IS NOT NULL THEN 1 END) as total_with_details
                FROM discovered_jobs WHERE user_id = ?
            """, (user_id,)).fetchone()

            approved_stats = conn.execute("""
                SELECT
                    COUNT(*) as total_approved,
                    COUNT(CASE WHEN date_applied IS NOT NULL THEN 1 END) as total_applied,
                    COUNT(CASE WHEN is_archived = TRUE THEN 1 END) as total_archived
                FROM approved_jobs WHERE user_id = ?
            """, (user_id,)).fetchone()

            location_stats = conn.execute("""
                SELECT location, COUNT(*) as count
                FROM discovered_jobs WHERE user_id = ?
                GROUP BY location
                ORDER BY count DESC
                LIMIT 10
            """, (user_id,)).fetchall()

            keyword_stats = conn.execute("""
                SELECT keyword, COUNT(*) as count
                FROM discovered_jobs WHERE user_id = ?
                GROUP BY keyword
                ORDER BY count DESC
                LIMIT 10
            """, (user_id,)).fetchall()

            recent_activity = conn.execute("""
                SELECT
                    DATE(date_discovered) as date,
                    COUNT(*) as discovered_count
                FROM discovered_jobs
                WHERE user_id = ? AND date_discovered >= datetime('now', '-30 days')
                GROUP BY DATE(date_discovered)
                ORDER BY date DESC
            """, (user_id,)).fetchall()

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
            """, (user_id,)).fetchall()

            # Applied jobs breakdown by location
            applied_by_location = conn.execute("""
                SELECT d.location, COUNT(*) as count
                FROM approved_jobs a
                JOIN discovered_jobs d ON a.discovered_job_id = d.id
                WHERE a.user_id = ? AND a.date_applied IS NOT NULL
                GROUP BY d.location
                ORDER BY count DESC
                LIMIT 10
            """, (user_id,)).fetchall()

            # Applied jobs breakdown by keyword
            applied_by_keyword = conn.execute("""
                SELECT d.keyword, COUNT(*) as count
                FROM approved_jobs a
                JOIN discovered_jobs d ON a.discovered_job_id = d.id
                WHERE a.user_id = ? AND a.date_applied IS NOT NULL
                GROUP BY d.keyword
                ORDER BY count DESC
                LIMIT 10
            """, (user_id,)).fetchall()

            # Approved jobs breakdown by location
            approved_by_location = conn.execute("""
                SELECT d.location, COUNT(*) as count
                FROM approved_jobs a
                JOIN discovered_jobs d ON a.discovered_job_id = d.id
                WHERE a.user_id = ?
                GROUP BY d.location
                ORDER BY count DESC
                LIMIT 10
            """, (user_id,)).fetchall()

            # Approved jobs breakdown by keyword
            approved_by_keyword = conn.execute("""
                SELECT d.keyword, COUNT(*) as count
                FROM approved_jobs a
                JOIN discovered_jobs d ON a.discovered_job_id = d.id
                WHERE a.user_id = ?
                GROUP BY d.keyword
                ORDER BY count DESC
                LIMIT 10
            """, (user_id,)).fetchall()

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
            """, (user_id, user_id)).fetchall()

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
            """, (user_id, user_id)).fetchall()

            return {
                'basic': dict(basic_stats),
                'approved': dict(approved_stats),
                'by_location': [dict(row) for row in location_stats],
                'by_keyword': [dict(row) for row in keyword_stats],
                'recent_activity': [dict(row) for row in recent_activity],
                'application_activity': [dict(row) for row in application_activity],
                'applied_by_location': [dict(row) for row in applied_by_location],
                'applied_by_keyword': [dict(row) for row in applied_by_keyword],
                'approved_by_location': [dict(row) for row in approved_by_location],
                'approved_by_keyword': [dict(row) for row in approved_by_keyword],
                'conversion_by_location': [dict(row) for row in conversion_by_location],
                'conversion_by_keyword': [dict(row) for row in conversion_by_keyword]
            }
    except Exception as e:
        print(f"Error getting job statistics: {e}")
        return {
            'basic': {'total_discovered': 0, 'total_analyzed': 0, 'total_with_details': 0},
            'approved': {'total_approved': 0, 'total_applied': 0, 'total_archived': 0},
            'by_location': [],
            'by_keyword': [],
            'recent_activity': [],
            'application_activity': [],
            'applied_by_location': [],
            'applied_by_keyword': [],
            'approved_by_location': [],
            'approved_by_keyword': [],
            'conversion_by_location': [],
            'conversion_by_keyword': []
        }


def extract_job_id_from_url(url: str) -> Optional[int]:
    """Extract LinkedIn job ID from URL"""
    match = _JOB_ID_RE.search(url)
    return int(match.group(1)) if match else None