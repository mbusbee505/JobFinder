# auth.py - Authentication and user management
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import sqlite3
from contextlib import contextmanager

DB_PATH = "jobfinder.db"

@contextmanager
def get_conn():
    """Context-managed connection that commits on success and rolls back on error."""
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


class User(UserMixin):
    def __init__(self, user_id, email, name, is_admin=False, is_approved=True):
        self.id = user_id
        self.email = email
        self.name = name
        self.is_admin = is_admin
        self.is_approved = is_approved

    @staticmethod
    def get(user_id):
        """Get user by ID"""
        with get_conn() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if user:
                return User(
                    user['id'],
                    user['email'],
                    user['name'],
                    user['is_admin'],
                    user['is_approved']
                )
        return None

    @staticmethod
    def get_by_email(email):
        """Get user by email"""
        with get_conn() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()
            if user:
                return User(
                    user['id'],
                    user['email'],
                    user['name'],
                    user['is_admin'],
                    user['is_approved']
                )
        return None

    @staticmethod
    def create_user(email, password, name, is_admin=False, is_approved=False):
        """Create a new user"""
        password_hash = generate_password_hash(password)
        try:
            with get_conn() as conn:
                cursor = conn.execute(
                    """INSERT INTO users (email, password_hash, name, is_admin, is_approved)
                       VALUES (?, ?, ?, ?, ?)""",
                    (email, password_hash, name, is_admin, is_approved)
                )
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None

    @staticmethod
    def verify_password(email, password):
        """Verify user password"""
        with get_conn() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()
            if user and check_password_hash(user['password_hash'], password):
                return User(
                    user['id'],
                    user['email'],
                    user['name'],
                    user['is_admin'],
                    user['is_approved']
                )
        return None

    @staticmethod
    def get_all_users():
        """Get all users (for admin)"""
        with get_conn() as conn:
            users = conn.execute(
                """SELECT id, email, name, is_admin, is_approved, created_at
                   FROM users ORDER BY created_at DESC"""
            ).fetchall()
            return [dict(user) for user in users]

    @staticmethod
    def approve_user(user_id):
        """Approve a user (admin only)"""
        with get_conn() as conn:
            conn.execute(
                "UPDATE users SET is_approved = TRUE WHERE id = ?",
                (user_id,)
            )
            return True

    @staticmethod
    def delete_user(user_id):
        """Delete a user and all their data (admin only)"""
        with get_conn() as conn:
            # Delete in order of dependencies
            conn.execute("DELETE FROM approved_jobs WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM discovered_jobs WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM user_configs WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM user_scan_control WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return True


def init_auth_db():
    """Initialize the authentication database tables"""
    with get_conn() as conn:
        # Create users table with authentication fields
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

        # Create the admin user if it doesn't exist
        admin = conn.execute("SELECT id FROM users WHERE email = ?", ('admin',)).fetchone()
        if not admin:
            admin_hash = generate_password_hash('admin')
            conn.execute("""
            INSERT INTO users (email, password_hash, name, is_admin, is_approved)
            VALUES (?, ?, ?, TRUE, TRUE)
            """, ('admin', admin_hash, 'Administrator'))
            print("✅ Admin user created (admin:admin)")