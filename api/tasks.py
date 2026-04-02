"""Tasks router - handles task pause/resume operations."""

from fastapi import APIRouter, Path
from pydantic import BaseModel

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskPauseRequest(BaseModel):
    """Request to pause a task."""
    reason: str = "Paused from dashboard"


class TaskPauseResponse(BaseModel):
    """Response after pausing a task."""
    ok: bool
    task_id: str


@router.post("/{task_id}/pause", response_model=TaskPauseResponse)
def pause_task(
    task_id: str = Path(..., description="Task ID to pause"),
    request: TaskPauseRequest = None
):
    """
    Pause a task from the dashboard.
    
    Sets the task status to 'paused' and records the reason.
    The orchestrator will stop processing this task until resumed.
    """
    try:
        from shared_state import load_memory, save_memory, utc_now
        
        mem = load_memory()
        tasks = mem.get("tasks", [])
        
        for task in tasks:
            if task.get("id") == task_id:
                task["status"] = "paused"
                task["paused_at"] = utc_now()
                task["pause_reason"] = request.reason if request else "Paused from dashboard"
                task["updated_at"] = utc_now()
                break
        
        mem["tasks"] = tasks
        save_memory(mem)
        
        return TaskPauseResponse(ok=True, task_id=task_id)
    except Exception as e:
        return TaskPauseResponse(ok=False, task_id=task_id)
