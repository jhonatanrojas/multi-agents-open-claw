"""
event_repository.py - Repository pattern for Event append-only log (F1.2, F3.2)
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc

from persistence.models import Event


class EventRepository:
    """
    Repository for Event database operations.
    
    Provides append-only event logging for observability.
    Events are never updated or deleted - only appended.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def generate_id(self) -> str:
        """Generate unique event ID."""
        return f"evt-{uuid.uuid4().hex[:12]}"
    
    def create_event(
        self,
        run_id: str,
        event_type: str,
        agent: Optional[str] = None,
        task_id: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> Event:
        """
        Create a new event.
        
        This is append-only - events are never modified after creation.
        
        Returns:
            Created Event instance
        """
        db_event = Event(
            id=self.generate_id(),
            run_id=run_id,
            task_id=task_id,
            event_type=event_type,
            agent=agent,
            payload_json=json.dumps(payload) if payload else "{}",
        )
        self.db.add(db_event)
        self.db.commit()
        self.db.refresh(db_event)
        return db_event
    
    def get_event(self, event_id: str) -> Optional[Event]:
        """Get event by ID."""
        return self.db.query(Event).filter(Event.id == event_id).first()
    
    def list_events(
        self,
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
        event_type: Optional[str] = None,
        agent: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Event]:
        """
        List events with optional filtering.
        
        Returns:
            List of Event instances (chronological order)
        """
        query = self.db.query(Event)
        
        if run_id:
            query = query.filter(Event.run_id == run_id)
        if task_id:
            query = query.filter(Event.task_id == task_id)
        if event_type:
            query = query.filter(Event.event_type == event_type)
        if agent:
            query = query.filter(Event.agent == agent)
        if since:
            query = query.filter(Event.created_at >= since)
        if until:
            query = query.filter(Event.created_at <= until)
        
        return (
            query.order_by(desc(Event.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )
    
    def get_events_for_run(self, run_id: str, limit: int = 1000) -> List[Event]:
        """Get all events for a specific run."""
        return (
            self.db.query(Event)
            .filter(Event.run_id == run_id)
            .order_by(desc(Event.created_at))
            .limit(limit)
            .all()
        )
    
    def get_recent_events(self, minutes: int = 60, limit: int = 100) -> List[Event]:
        """Get events from the last N minutes."""
        since = datetime.utcnow() - timedelta(minutes=minutes)
        return (
            self.db.query(Event)
            .filter(Event.created_at >= since)
            .order_by(desc(Event.created_at))
            .limit(limit)
            .all()
        )
    
    def count_events(
        self,
        run_id: Optional[str] = None,
        event_type: Optional[str] = None
    ) -> int:
        """Count events with optional filtering."""
        query = self.db.query(Event)
        if run_id:
            query = query.filter(Event.run_id == run_id)
        if event_type:
            query = query.filter(Event.event_type == event_type)
        return query.count()
    
    def get_event_types_for_run(self, run_id: str) -> List[str]:
        """Get all distinct event types for a run."""
        return [
            row[0] for row in
            self.db.query(Event.event_type)
            .filter(Event.run_id == run_id)
            .distinct()
            .all()
        ]
