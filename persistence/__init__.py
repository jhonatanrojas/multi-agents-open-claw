"""
persistence/__init__.py - Database persistence layer (F1.2)

This package provides database persistence for the multi-agent system,
replacing MEMORY.json as the source of truth.

Usage:
    from persistence import get_db, RunRepository, TaskRepository
    
    db = next(get_db())
    run_repo = RunRepository(db)
    run = run_repo.create_run(project_id="proj-001", status="planning")
"""

from persistence.database import (
    Base,
    engine,
    SessionLocal,
    get_db,
    init_db,
)
from persistence.models import (
    Run,
    Task,
    Event,
)
from persistence.run_repository import RunRepository
from persistence.task_repository import TaskRepository
from persistence.event_repository import EventRepository

__all__ = [
    # Database
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
    "init_db",
    # Models
    "Run",
    "Task",
    "Event",
    # Repositories
    "RunRepository",
    "TaskRepository",
    "EventRepository",
]
