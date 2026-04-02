#!/usr/bin/env python3
"""
task_entity.py - Complete Task entity (F2.3)

Rich task entity with all metadata for full lifecycle tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum


class TaskStatus(str, Enum):
    """Task lifecycle statuses."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class TaskPriority(int, Enum):
    """Task priority levels."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class TaskEntity:
    """
    Complete task entity with full lifecycle metadata.
    
    Attributes:
        task_id: Unique identifier
        run_id: Parent run identifier
        agent_id: Assigned agent
        status: Current status
        priority: Priority level
        
        # Content
        title: Short title
        description: Full description
        acceptance_criteria: List of criteria for completion
        
        # I/O
        input_data: Input parameters
        output_data: Output results
        artifacts: Produced artifacts
        
        # Timing
        created_at: Creation timestamp
        assigned_at: Assignment timestamp
        started_at: Start timestamp
        completed_at: Completion timestamp
        
        # Tracking
        attempt_count: Number of attempts
        retry_count: Number of retries
        blockers: Active blockers
        
        # Quality
        review_status: Review state
        review_feedback: Reviewer feedback
        quality_score: Quality rating (0-1)
    """
    
    # Identifiers
    task_id: str
    run_id: str
    agent_id: str
    
    # State
    status: TaskStatus
    priority: TaskPriority = TaskPriority.NORMAL
    
    # Content
    title: str = ""
    description: str = ""
    acceptance_criteria: List[str] = field(default_factory=list)
    
    # I/O
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[str] = field(default_factory=list)
    
    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    assigned_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Tracking
    attempt_count: int = 0
    retry_count: int = 0
    blockers: List[Dict[str, Any]] = field(default_factory=list)
    
    # Quality
    review_status: Optional[str] = None
    review_feedback: Optional[str] = None
    quality_score: Optional[float] = None
    
    def start(self) -> None:
        """Mark task as started."""
        self.status = TaskStatus.IN_PROGRESS
        self.started_at = datetime.utcnow()
        self.attempt_count += 1
    
    def complete(self, output: Dict[str, Any], artifacts: Optional[List[str]] = None) -> None:
        """Mark task as completed."""
        self.status = TaskStatus.COMPLETED
        self.output_data = output
        if artifacts:
            self.artifacts = artifacts
        self.completed_at = datetime.utcnow()
    
    def fail(self, error: str) -> None:
        """Mark task as failed."""
        self.status = TaskStatus.FAILED
        self.output_data = {"error": error}
        self.completed_at = datetime.utcnow()
    
    def block(self, blocker: Dict[str, Any]) -> None:
        """Block task."""
        self.status = TaskStatus.BLOCKED
        self.blockers.append(blocker)
    
    def unblock(self) -> None:
        """Unblock task."""
        if self.status == TaskStatus.BLOCKED:
            self.status = TaskStatus.PENDING
    
    def assign(self, agent_id: str) -> None:
        """Assign task to agent."""
        self.agent_id = agent_id
        self.status = TaskStatus.ASSIGNED
        self.assigned_at = datetime.utcnow()
    
    def get_duration_seconds(self) -> Optional[float]:
        """Get task duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "status": self.status.value,
            "priority": self.priority.value,
            "title": self.title,
            "description": self.description,
            "acceptance_criteria": self.acceptance_criteria,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "artifacts": self.artifacts,
            "created_at": self.created_at.isoformat(),
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "attempt_count": self.attempt_count,
            "retry_count": self.retry_count,
            "blockers": self.blockers,
            "review_status": self.review_status,
            "review_feedback": self.review_feedback,
            "quality_score": self.quality_score,
        }


__all__ = [
    "TaskStatus",
    "TaskPriority",
    "TaskEntity",
]
