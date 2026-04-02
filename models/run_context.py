#!/usr/bin/env python3
"""
run_context.py - Formal RunContext model (F1.1)

This module defines the formal RunContext dataclass that encapsulates
all state necessary for task execution. It provides serialization,
deserialization, and checkpoint persistence.

Usage:
    from models.run_context import RunContext, RunStatus
    
    context = RunContext(
        run_id="run-001",
        project_id="proj-001",
        status=RunStatus.EXECUTING,
        current_phase="implementation",
        current_agent="byte"
    )
    
    # Serialize to dict
    data = context.to_dict()
    
    # Deserialize from dict
    context = RunContext.from_dict(data)
    
    # Persist checkpoint
    context.checkpoint()
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal, Optional, Any

# Import GraphState for normalized state management (F1.5)
from graph_state import GraphState

# Base directory for persistence
BASE_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = BASE_DIR / "data" / "runs"


class RunStatus(str, Enum):
    """Valid run statuses."""
    PLANNING = "planning"
    EXECUTING = "executing"
    BLOCKED = "blocked"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentType(str, Enum):
    """Valid agent types."""
    ARCH = "arch"
    BYTE = "byte"
    PIXEL = "pixel"
    JUDGE = "judge"


@dataclass
class TaskInfo:
    """Lightweight task information for RunContext."""
    task_id: str
    agent: AgentType
    status: str
    description: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent": self.agent.value if isinstance(self.agent, AgentType) else self.agent,
            "status": self.status,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskInfo:
        return cls(
            task_id=data["task_id"],
            agent=AgentType(data["agent"]) if data.get("agent") in [a.value for a in AgentType] else data.get("agent", ""),
            status=data["status"],
            description=data["description"],
            created_at=datetime.fromisoformat(data["created_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        )


@dataclass
class Artifact:
    """Artifact produced during a run."""
    artifact_id: str
    name: str
    path: str
    type: str  # file, url, text
    created_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "name": self.name,
            "path": self.path,
            "type": self.type,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Artifact:
        return cls(
            artifact_id=data["artifact_id"],
            name=data["name"],
            path=data["path"],
            type=data["type"],
            created_at=datetime.fromisoformat(data["created_at"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Blocker:
    """Blocker that prevents run progress."""
    blocker_id: str
    description: str
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolution: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "blocker_id": self.blocker_id,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution": self.resolution,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Blocker:
        return cls(
            blocker_id=data["blocker_id"],
            description=data["description"],
            created_at=datetime.fromisoformat(data["created_at"]),
            resolved_at=datetime.fromisoformat(data["resolved_at"]) if data.get("resolved_at") else None,
            resolution=data.get("resolution"),
        )


@dataclass
class Milestone:
    """Milestone achieved during a run."""
    milestone_id: str
    name: str
    description: str
    achieved_at: datetime
    agent: Optional[AgentType] = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "milestone_id": self.milestone_id,
            "name": self.name,
            "description": self.description,
            "achieved_at": self.achieved_at.isoformat(),
            "agent": self.agent.value if isinstance(self.agent, AgentType) else self.agent,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Milestone:
        return cls(
            milestone_id=data["milestone_id"],
            name=data["name"],
            description=data["description"],
            achieved_at=datetime.fromisoformat(data["achieved_at"]),
            agent=AgentType(data["agent"]) if data.get("agent") in [a.value for a in AgentType] else None,
        )


@dataclass
class RunContext:
    """
    Formal RunContext that encapsulates all state for a run.
    
    This dataclass provides:
    - Type-safe state management
    - Serialization/deserialization
    - Checkpoint persistence
    - Schema versioning
    - Normalized graph states (F1.5)
    
    Attributes:
        run_id: Unique identifier for this run
        project_id: Associated project identifier
        status: Current run status
        current_phase: Current execution phase (GraphState - never use string literals)
        current_agent: Currently assigned agent
        plan_version: Version of the plan being executed
        tasks: List of tasks in this run
        artifacts: List of artifacts produced
        blockers: List of blockers encountered
        milestones: List of milestones achieved
        started_at: When the run started
        updated_at: When the run was last updated
        schema_version: Schema version for migrations
    """
    
    # Core identifiers
    run_id: str
    project_id: str
    
    # Execution state (F1.5: GraphState enum instead of string)
    status: RunStatus
    current_phase: Optional[GraphState] = None
    current_agent: Optional[AgentType] = None
    
    # Plan and tasks
    plan_version: int = 1
    tasks: list[TaskInfo] = field(default_factory=list)
    
    # Outputs and blockers
    artifacts: list[Artifact] = field(default_factory=list)
    blockers: list[Blocker] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    
    # Timestamps
    started_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Schema version for future migrations
    schema_version: int = 1
    
    def __post_init__(self):
        """Validate run context after initialization."""
        if not self.run_id:
            raise ValueError("run_id is required")
        if not self.project_id:
            raise ValueError("project_id is required")
        
        # Ensure status is valid
        if isinstance(self.status, str):
            self.status = RunStatus(self.status)
        
        # F1.5: Ensure current_phase is GraphState (never use string literals)
        if self.current_phase and isinstance(self.current_phase, str):
            phase = GraphState.from_string(self.current_phase)
            if phase:
                self.current_phase = phase
        
        # Ensure agent is valid if provided
        if self.current_agent and isinstance(self.current_agent, str):
            if self.current_agent in [a.value for a in AgentType]:
                self.current_agent = AgentType(self.current_agent)
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize RunContext to dictionary."""
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "status": self.status.value if isinstance(self.status, RunStatus) else self.status,
            "current_phase": self.current_phase.value if isinstance(self.current_phase, GraphState) else self.current_phase,
            "current_agent": self.current_agent.value if isinstance(self.current_agent, AgentType) else self.current_agent,
            "plan_version": self.plan_version,
            "tasks": [t.to_dict() for t in self.tasks],
            "artifacts": [a.to_dict() for a in self.artifacts],
            "blockers": [b.to_dict() for b in self.blockers],
            "milestones": [m.to_dict() for m in self.milestones],
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "schema_version": self.schema_version,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunContext:
        """Deserialize RunContext from dictionary."""
        # Handle schema migrations if needed
        schema_version = data.get("schema_version", 1)
        
        # F1.5: Parse current_phase as GraphState (never use string literals)
        current_phase = None
        if data.get("current_phase"):
            current_phase = GraphState.from_string(data["current_phase"])
        
        return cls(
            run_id=data["run_id"],
            project_id=data["project_id"],
            status=RunStatus(data["status"]) if data.get("status") else RunStatus.PLANNING,
            current_phase=current_phase,
            current_agent=AgentType(data["current_agent"]) if data.get("current_agent") in [a.value for a in AgentType] else None,
            plan_version=data.get("plan_version", 1),
            tasks=[TaskInfo.from_dict(t) for t in data.get("tasks", [])],
            artifacts=[Artifact.from_dict(a) for a in data.get("artifacts", [])],
            blockers=[Blocker.from_dict(b) for b in data.get("blockers", [])],
            milestones=[Milestone.from_dict(m) for m in data.get("milestones", [])],
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.utcnow(),
            schema_version=schema_version,
        )
    
    def to_json(self) -> str:
        """Serialize RunContext to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)
    
    @classmethod
    def from_json(cls, json_str: str) -> RunContext:
        """Deserialize RunContext from JSON string."""
        return cls.from_dict(json.loads(json_str))
    
    def checkpoint(self) -> Path:
        """
        Persist current state to persistence layer.
        
        Returns:
            Path to the checkpoint file
        """
        # Ensure runs directory exists
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Update timestamp
        self.updated_at = datetime.utcnow()
        
        # Write to file
        checkpoint_path = RUNS_DIR / f"{self.run_id}.json"
        checkpoint_path.write_text(self.to_json(), encoding="utf-8")
        
        return checkpoint_path
    
    @classmethod
    def load(cls, run_id: str) -> Optional[RunContext]:
        """
        Load RunContext from persistence layer.
        
        Args:
            run_id: The run identifier
        
        Returns:
            RunContext if found, None otherwise
        """
        checkpoint_path = RUNS_DIR / f"{run_id}.json"
        
        if not checkpoint_path.exists():
            return None
        
        return cls.from_json(checkpoint_path.read_text(encoding="utf-8"))
    
    @classmethod
    def list_all(cls) -> list[RunContext]:
        """
        List all persisted RunContexts.
        
        Returns:
            List of RunContext objects
        """
        if not RUNS_DIR.exists():
            return []
        
        contexts = []
        for checkpoint_file in RUNS_DIR.glob("*.json"):
            try:
                context = cls.from_json(checkpoint_file.read_text(encoding="utf-8"))
                contexts.append(context)
            except Exception:
                # Skip corrupted files
                continue
        
        return contexts
    
    def add_task(self, task: TaskInfo) -> None:
        """Add a task to this run."""
        self.tasks.append(task)
        self.updated_at = datetime.utcnow()
    
    def add_artifact(self, artifact: Artifact) -> None:
        """Add an artifact to this run."""
        self.artifacts.append(artifact)
        self.updated_at = datetime.utcnow()
    
    def add_blocker(self, blocker: Blocker) -> None:
        """Add a blocker to this run."""
        self.blockers.append(blocker)
        self.status = RunStatus.BLOCKED
        self.updated_at = datetime.utcnow()
    
    def resolve_blocker(self, blocker_id: str, resolution: str) -> bool:
        """
        Resolve a blocker.
        
        Returns:
            True if blocker was found and resolved, False otherwise
        """
        for blocker in self.blockers:
            if blocker.blocker_id == blocker_id and not blocker.resolved_at:
                blocker.resolved_at = datetime.utcnow()
                blocker.resolution = resolution
                self.updated_at = datetime.utcnow()
                
                # Update status if no more active blockers
                if not any(b.resolved_at is None for b in self.blockers):
                    self.status = RunStatus.EXECUTING
                
                return True
        
        return False
    
    def add_milestone(self, milestone: Milestone) -> None:
        """Add a milestone to this run."""
        self.milestones.append(milestone)
        self.updated_at = datetime.utcnow()
    
    def get_summary(self) -> dict[str, Any]:
        """Get a summary of this run for display."""
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "status": self.status.value if isinstance(self.status, RunStatus) else self.status,
            "current_phase": self.current_phase,
            "current_agent": self.current_agent.value if isinstance(self.current_agent, AgentType) else self.current_agent,
            "task_count": len(self.tasks),
            "artifact_count": len(self.artifacts),
            "blocker_count": len([b for b in self.blockers if b.resolved_at is None]),
            "milestone_count": len(self.milestones),
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


def generate_run_id() -> str:
    """Generate a unique run identifier."""
    return f"run-{uuid.uuid4().hex[:12]}"


def generate_task_id() -> str:
    """Generate a unique task identifier."""
    return f"task-{uuid.uuid4().hex[:12]}"


__all__ = [
    "RunStatus",
    "AgentType",
    "TaskInfo",
    "Artifact",
    "Blocker",
    "Milestone",
    "RunContext",
    "generate_run_id",
    "generate_task_id",
]
