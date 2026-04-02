#!/usr/bin/env python3
"""
metrics.py - Observability and metrics (F3.5)

System metrics collection.
"""

import time
from typing import Dict, Any
from dataclasses import dataclass, field


@dataclass
class SystemMetrics:
    """System-wide metrics."""
    active_runs: int = 0
    completed_runs: int = 0
    failed_runs: int = 0
    active_tasks: int = 0
    avg_task_duration: float = 0.0
    circuit_breaker_trips: int = 0
    retry_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_runs": self.active_runs,
            "completed_runs": self.completed_runs,
            "failed_runs": self.failed_runs,
            "active_tasks": self.active_tasks,
            "avg_task_duration": self.avg_task_duration,
            "circuit_breaker_trips": self.circuit_breaker_trips,
            "retry_count": self.retry_count,
            "timestamp": time.time(),
        }


# Global metrics
metrics = SystemMetrics()


def get_metrics() -> Dict[str, Any]:
    """Get current system metrics."""
    return metrics.to_dict()


__all__ = ["metrics", "get_metrics", "SystemMetrics"]
