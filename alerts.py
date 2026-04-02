#!/usr/bin/env python3
"""
alerts.py - Alerts and notifications (F3.6)

Alert system for important events.
"""

from typing import Dict, Any, Optional
from enum import Enum
from datetime import datetime

from event_bus import Event, subscribe_to_event


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


def send_alert(level: AlertLevel, message: str, context: Optional[Dict[str, Any]] = None) -> None:
    """Send an alert notification."""
    alert = {
        "level": level.value,
        "message": message,
        "context": context or {},
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    # Log alert (in production, would send to Telegram/email/etc)
    print(f"[ALERT:{level.value.upper()}] {message}")


def on_critical_event(event: Event) -> None:
    """Handle critical events."""
    if event.event_type in ["task_failed", "circuit_breaker_opened"]:
        send_alert(AlertLevel.ERROR, f"Critical: {event.event_type}", event.payload)


# Subscribe to critical events
subscribe_to_event("task_failed", on_critical_event)
subscribe_to_event("circuit_breaker_opened", on_critical_event)


__all__ = ["AlertLevel", "send_alert"]
