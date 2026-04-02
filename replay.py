#!/usr/bin/env python3
"""
replay.py - Run replay functionality (F3.4)

Replay runs from event log.
"""

from typing import List, Dict, Any
from persistence import get_db, EventRepository


def get_run_events_for_replay(run_id: str) -> List[Dict[str, Any]]:
    """Get events for replaying a run."""
    db = next(get_db())
    repo = EventRepository(db)
    events = repo.get_events_for_run(run_id, limit=10000)
    
    return [
        {
            "timestamp": e.created_at.isoformat(),
            "type": e.event_type,
            "agent": e.agent,
            "payload": e.payload_json,
        }
        for e in events
    ]


__all__ = ["get_run_events_for_replay"]
