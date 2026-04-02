"""Run Context router - handles RunContext endpoints (F1.1)."""

from fastapi import APIRouter, Path, HTTPException
from pydantic import BaseModel
from typing import Optional, Any

from models import RunContext, RunStatus, AgentType

router = APIRouter(prefix="/api/runs", tags=["runs"])


class RunContextResponse(BaseModel):
    """Response model for RunContext endpoints."""
    run_id: str
    project_id: str
    status: str
    current_phase: Optional[str]
    current_agent: Optional[str]
    plan_version: int
    task_count: int
    artifact_count: int
    blocker_count: int
    milestone_count: int
    started_at: str
    updated_at: str
    schema_version: int


class RunContextCreateRequest(BaseModel):
    """Request to create a new RunContext."""
    project_id: str
    status: Optional[str] = "planning"
    current_phase: Optional[str] = None
    current_agent: Optional[str] = None


class RunContextUpdateRequest(BaseModel):
    """Request to update a RunContext."""
    status: Optional[str] = None
    current_phase: Optional[str] = None
    current_agent: Optional[str] = None


@router.get("/{run_id}/context", response_model=RunContextResponse)
def get_run_context(
    run_id: str = Path(..., description="Run identifier")
):
    """
    Get RunContext for a specific run.
    
    Returns the full RunContext if it exists, creates one from
    current run state if it doesn't.
    """
    # Try to load existing RunContext
    context = RunContext.load(run_id)
    
    if context is None:
        # Try to create from current MEMORY.json state
        from shared_state import load_memory
        mem = load_memory()
        
        project = mem.get("project", {})
        if project and project.get("id") == run_id or project.get("id"):
            # Create RunContext from current state
            context = RunContext(
                run_id=run_id,
                project_id=project.get("id", "unknown"),
                status=RunStatus(project.get("status", "planning")),
                current_phase=project.get("phase"),
                current_agent=AgentType(project.get("current_agent")) if project.get("current_agent") else None,
                plan_version=1,
            )
            # Persist for future requests
            context.checkpoint()
        else:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    
    summary = context.get_summary()
    return RunContextResponse(**summary)


@router.post("", response_model=RunContextResponse)
def create_run_context(request: RunContextCreateRequest):
    """
    Create a new RunContext.
    """
    from models import generate_run_id
    
    run_id = generate_run_id()
    
    context = RunContext(
        run_id=run_id,
        project_id=request.project_id,
        status=RunStatus(request.status) if request.status else RunStatus.PLANNING,
        current_phase=request.current_phase,
        current_agent=AgentType(request.current_agent) if request.current_agent else None,
    )
    
    # Persist
    context.checkpoint()
    
    summary = context.get_summary()
    return RunContextResponse(**summary)


@router.put("/{run_id}/context", response_model=RunContextResponse)
def update_run_context(
    request: RunContextUpdateRequest,
    run_id: str = Path(..., description="Run identifier")
):
    """
    Update an existing RunContext.
    """
    context = RunContext.load(run_id)
    
    if context is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    
    # Update fields
    if request.status:
        context.status = RunStatus(request.status)
    if request.current_phase is not None:
        context.current_phase = request.current_phase
    if request.current_agent is not None:
        context.current_agent = AgentType(request.current_agent) if request.current_agent else None
    
    # Persist
    context.checkpoint()
    
    summary = context.get_summary()
    return RunContextResponse(**summary)


@router.get("", response_model=list[RunContextResponse])
def list_runs():
    """
    List all persisted RunContexts.
    """
    contexts = RunContext.list_all()
    return [RunContextResponse(**c.get_summary()) for c in contexts]


@router.get("/{run_id}/full")
def get_run_context_full(
    run_id: str = Path(..., description="Run identifier")
):
    """
    Get full RunContext with all details (tasks, artifacts, blockers, etc.).
    """
    context = RunContext.load(run_id)
    
    if context is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    
    return context.to_dict()
