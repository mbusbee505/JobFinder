#!/usr/bin/env python3
"""
Migration script to add is_dismissed column to approved_jobs table.
Run this on the remote server to update the database structure.

Usage: python3 migrate_add_dismissed.py
"""

import sqlite3
import sys

DB_PATH = "jobfinder.db"

def migrate():
    """Add is_dismissed column to approved_jobs table"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("PRAGMA table_info(approved_jobs)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'is_dismissed' in columns:
            print("✅ Column 'is_dismissed' already exists. No migration needed.")
            conn.close()
            return True

        # Add the column
        print("Adding 'is_dismissed' column to approved_jobs table...")
        cursor.execute("ALTER TABLE approved_jobs ADD COLUMN is_dismissed BOOLEAN DEFAULT FALSE")
        conn.commit()

        print("✅ Successfully added 'is_dismissed' column to approved_jobs table")
        conn.close()
        return True

    except Exception as e:
        print(f"❌ Error during migration: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("JobFinder Database Migration: Add is_dismissed column")
    print("=" * 60)

    success = migrate()

    if success:
        print("\n✅ Migration completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)
