"""
Models package for OpenClaw Multi-Agent system.

This package contains Pydantic/dataclass models for formal state management.

F1.1 — Formalizar RunContext
F1.5 — Normalizar estados del grafo
"""

from models.run_context import (
    RunStatus,
    AgentType,
    TaskInfo,
    Artifact,
    Blocker,
    Milestone,
    RunContext,
    generate_run_id,
    generate_task_id,
)

# F1.5: Import GraphState for normalized state management
from graph_state import GraphState, validate_state_transition

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
    # F1.5
    "GraphState",
    "validate_state_transition",
]
