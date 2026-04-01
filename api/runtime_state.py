"""
Runtime state router - UI synchronization endpoint (F1.4)

Provides a comprehensive runtime state endpoint for UI synchronization.
The UI reads state directly from this endpoint rather than inferring it.
"""

from fastapi import APIRouter, Path, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime

from persistence import get_db, RunRepository, TaskRepository

router = APIRouter(prefix="/api/projects", tags=["runtime-state"])


class TaskState(BaseModel):
    """Task state for UI."""
    task_id: str
    agent: str
    status: str
    description: str
    created_at: str
    completed_at: Optional[str] = None


class AgentState(BaseModel):
    """Agent state for UI."""
    agent_id: str
    status: str
    current_task: Optional[str] = None
    last_activity: Optional[str] = None


class BlockerState(BaseModel):
    """Blocker state for UI."""
    blocker_id: str
    description: str
    created_at: str
    resolved_at: Optional[str] = None


class RuntimeStateResponse(BaseModel):
    """
    Complete runtime state for UI synchronization.
    
    This is the single source of truth for the UI.
    """
    project_id: str
    run_id: str
    status: str
    current_phase: Optional[str]
    current_agent: Optional[str]
    plan_version: int
    tasks: List[TaskState]
    agents: dict
    blockers: List[BlockerState]
    logs: List[str]
    updated_at: str


@router.get("/{project_id}/runtime-state", response_model=RuntimeStateResponse)
def get_runtime_state(
    project_id: str = Path(..., description="Project identifier")
):
    """
    Get complete runtime state for UI synchronization.
    
    This endpoint provides the single source of truth for the UI.
    The UI reads state directly from here rather than inferring it.
    
    Returns:
        Complete runtime state including run, tasks, agents, and blockers
    """
    db = next(get_db())
    run_repo = RunRepository(db)
    task_repo = TaskRepository(db)
    
    # Get the most recent run for this project
    run = run_repo.get_run_by_project(project_id)
    
    if not run:
        raise HTTPException(
            status_code=404,
            detail=f"No active run found for project {project_id}"
        )
    
    # Get tasks for this run
    tasks = task_repo.get_tasks_for_run(run.id)
    
    # Build task states
    task_states = []
    for task in tasks:
        task_states.append(TaskState(
            task_id=task.id,
            agent=task.agent,
            status=task.status,
            description=task.description or "",
            created_at=task.created_at.isoformat() if task.created_at else datetime.utcnow().isoformat(),
            completed_at=task.completed_at.isoformat() if task.completed_at else None,
        ))
    
    # Build agent states from tasks
    agent_states = {}
    agents_from_tasks = set(task.agent for task in tasks)
    for agent_id in agents_from_tasks:
        agent_tasks = [t for t in tasks if t.agent == agent_id]
        current_task = None
        last_activity = None
        
        if agent_tasks:
            # Most recent task
            recent_task = max(agent_tasks, key=lambda t: t.updated_at or t.created_at)
            current_task = recent_task.id if recent_task.status not in ["completed", "failed"] else None
            last_activity = (recent_task.updated_at or recent_task.created_at).isoformat()
        
        agent_states[agent_id] = {
            "status": "busy" if any(t.status == "in_progress" for t in agent_tasks) else "idle",
            "current_task": current_task,
            "last_activity": last_activity,
        }
    
    # Parse blockers from context (if stored there)
    blockers = []
    try:
        import json
        context = json.loads(run.context_json) if run.context_json else {}
        blockers_data = context.get("blockers", [])
        for b in blockers_data:
            blockers.append(BlockerState(
                blocker_id=b.get("blocker_id", "unknown"),
                description=b.get("description", ""),
                created_at=b.get("created_at", datetime.utcnow().isoformat()),
                resolved_at=b.get("resolved_at"),
            ))
    except Exception:
        pass
    
    # Get recent logs (placeholder - could integrate with logging system)
    logs = [
        f"Run {run.id} started",
        f"Status: {run.status}",
    ]
    if run.current_phase:
        logs.append(f"Current phase: {run.current_phase}")
    if run.current_agent:
        logs.append(f"Current agent: {run.current_agent}")
    
    return RuntimeStateResponse(
        project_id=project_id,
        run_id=run.id,
        status=run.status,
        current_phase=run.current_phase,
        current_agent=run.current_agent,
        plan_version=int(run.plan_version) if run.plan_version else 1,
        tasks=task_states,
        agents=agent_states,
        blockers=blockers,
        logs=logs,
        updated_at=run.updated_at.isoformat() if run.updated_at else datetime.utcnow().isoformat(),
    )


@router.get("/{project_id}/runtime-state/stream")
def get_runtime_state_stream(
    project_id: str = Path(..., description="Project identifier")
):
    """
    Get runtime state as SSE stream for real-time updates.
    
    This endpoint is used by the UI for real-time synchronization.
    """
    # This would integrate with the existing SSE infrastructure
    # For now, return a placeholder
    return {
        "message": "SSE stream endpoint - integrate with existing /api/stream",
        "project_id": project_id,
    }
