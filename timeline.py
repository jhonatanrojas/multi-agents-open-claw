#!/usr/bin/env python3
"""
timeline.py - Timeline UI data provider (F3.3)

Provides timeline data for UI visualization.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from persistence import get_db, EventRepository


def get_run_timeline(run_id: str) -> List[Dict[str, Any]]:
    """Get timeline events for a run."""
    db = next(get_db())
    repo = EventRepository(db)
    events = repo.get_events_for_run(run_id, limit=1000)
    
    timeline = []
    for event in events:
        timeline.append({
            "timestamp": event.created_at.isoformat(),
            "type": event.event_type,
            "agent": event.agent,
            "description": f"{event.event_type} by {event.agent}",
        })
    
    return timeline


__all__ = ["get_run_timeline"]
