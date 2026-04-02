#!/usr/bin/env python3
"""
event_log.py - Persistent event log (F3.2)

Append-only event log stored in database.
"""

from persistence import get_db, EventRepository
from event_bus import Event, event_bus, subscribe_to_event


def persist_event(event: Event) -> None:
    """Persist event to database."""
    try:
        db = next(get_db())
        repo = EventRepository(db)
        repo.create_event(
            run_id=event.payload.get("run_id", "system"),
            event_type=event.event_type,
            agent=event.source,
            payload=event.payload,
        )
    except Exception:
        pass  # Don't break event flow on persistence errors


def setup_event_persistence() -> None:
    """Setup automatic event persistence."""
    subscribe_to_event("*", persist_event)


__all__ = ["persist_event", "setup_event_persistence"]
