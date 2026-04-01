#!/usr/bin/env python3
"""
event_bus.py - Event Bus for system-wide events (F3.1)

Central event bus for decoupled communication between components.
"""

import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Callable, Optional
from dataclasses import dataclass, asdict
from threading import Lock


@dataclass
class Event:
    """System event."""
    event_id: str
    event_type: str
    source: str
    payload: Dict[str, Any]
    timestamp: str
    correlation_id: Optional[str] = None


class EventBus:
    """
    Central event bus for system-wide pub/sub.
    
    Components can publish events and subscribe to event types.
    """
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = Lock()
        self._history: List[Event] = []
        self._max_history = 1000
    
    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """
        Subscribe to an event type.
        
        Args:
            event_type: Type of event to subscribe to
            handler: Callback function(event)
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)
    
    def unsubscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """Unsubscribe from an event type."""
        with self._lock:
            if event_type in self._subscribers:
                if handler in self._subscribers[event_type]:
                    self._subscribers[event_type].remove(handler)
    
    def publish(self, event_type: str, source: str, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> Event:
        """
        Publish an event.
        
        Args:
            event_type: Type of event
            source: Source component
            payload: Event data
            correlation_id: Optional correlation ID
        
        Returns:
            Created event
        """
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            source=source,
            payload=payload,
            timestamp=datetime.utcnow().isoformat(),
            correlation_id=correlation_id,
        )
        
        # Store in history
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
        
        # Notify subscribers
        handlers = []
        with self._lock:
            handlers = self._subscribers.get(event_type, []).copy()
        
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                pass  # Don't let handlers break the bus
        
        return event
    
    def get_history(self, event_type: Optional[str] = None, limit: int = 100) -> List[Event]:
        """Get event history."""
        with self._lock:
            events = self._history
            if event_type:
                events = [e for e in events if e.event_type == event_type]
            return events[-limit:]
    
    def clear_history(self) -> None:
        """Clear event history."""
        with self._lock:
            self._history = []


# Global event bus instance
event_bus = EventBus()


def publish_event(event_type: str, source: str, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> Event:
    """Convenience function to publish to global bus."""
    return event_bus.publish(event_type, source, payload, correlation_id)


def subscribe_to_event(event_type: str, handler: Callable[[Event], None]) -> None:
    """Convenience function to subscribe to global bus."""
    event_bus.subscribe(event_type, handler)


__all__ = [
    "Event",
    "EventBus",
    "event_bus",
    "publish_event",
    "subscribe_to_event",
]
