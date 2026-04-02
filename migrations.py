#!/usr/bin/env python3
"""
migrations.py - Database migrations (F4.3)

Simple migration system for database schema.
"""

from persistence import init_db


def run_migrations() -> None:
    """Run database migrations."""
    # Initialize database (creates tables if not exist)
    init_db()
    print("Database migrations completed")


__all__ = ["run_migrations"]
