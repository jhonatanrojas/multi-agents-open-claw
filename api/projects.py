"""Projects router - handles project management endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/project", tags=["projects"])


class ProjectStartRequest(BaseModel):
    """Request to start a new project."""
    name: str
    description: Optional[str] = None
    brief: str


class ProjectClarificationReply(BaseModel):
    """Reply to a clarification request."""
    reply: str


class ProjectExtendRequest(BaseModel):
    """Request to extend a project with additional work."""
    brief: str


@router.post("/start")
def start_project(request: ProjectStartRequest):
    """Start a new project with the orchestrator."""
    try:
        from coordination import ensure_project_id
        from shared_state import load_memory, save_memory, utc_now
        from run_lock import run_lock_context
        from fastapi import HTTPException
        
        mem = load_memory()
        project_id = ensure_project_id(mem)
        
        # F1.3: Acquire execution lock to prevent double runs
        try:
            with run_lock_context(project_id):
                # Initialize project
                mem.setdefault("project", {})
                mem["project"].update({
                    "id": project_id,
                    "name": request.name,
                    "description": request.description or "",
                    "brief": request.brief,
                    "status": "planning",
                    "phase": "discovery",
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                })
                
                save_memory(mem)
                
                return {"ok": True, "project_id": project_id}
        except RuntimeError as e:
            # Lock already held - run is active
            raise HTTPException(
                status_code=409,
                detail=f"Run already active for project {project_id}"
            )
    except HTTPException:
        raise
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/pause")
def pause_project():
    """Pause the current project execution."""
    try:
        from dashboard_api import _stop_orchestrator
        
        result = _stop_orchestrator(reason="Pausado desde el dashboard")
        return {"ok": True, "stopped": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/resume")
def resume_project():
    """Resume a paused project."""
    try:
        from shared_state import load_memory, save_memory, utc_now
        
        mem = load_memory()
        mem.setdefault("project", {})
        mem["project"]["status"] = "executing"
        mem["project"]["updated_at"] = utc_now()
        save_memory(mem)
        
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/delete")
def delete_project():
    """Delete the current project."""
    try:
        from dashboard_api import _stop_orchestrator
        from shared_state import load_memory, save_memory
        
        # Stop orchestrator
        _stop_orchestrator(reason="Eliminado desde el dashboard")
        
        # Clear project data
        mem = load_memory()
        mem["project"] = {}
        mem["tasks"] = []
        save_memory(mem)
        
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/restart")
def restart_project():
    """Restart the current project (stop and allow restart)."""
    try:
        from dashboard_api import _stop_orchestrator
        
        result = _stop_orchestrator(reason="Reinicio forzado desde el dashboard")
        return {"ok": True, "stopped_pid": result.get("pid"), "alive": result.get("alive")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/extend")
def extend_project(request: ProjectExtendRequest):
    """Enqueue a follow-up task on the current project."""
    try:
        from orchestrator import propose_follow_up_task
        from shared_state import load_memory
        
        mem = load_memory()
        project_id = mem.get("project", {}).get("id")
        
        if not project_id:
            return {"ok": False, "error": "No active project"}
        
        # Add follow-up task
        propose_follow_up_task(mem, request.brief)
        
        return {"ok": True, "project_id": project_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/retry-planning")
def retry_planning():
    """Re-run planning for the current project."""
    try:
        from shared_state import load_memory, save_memory, utc_now
        
        mem = load_memory()
        mem.setdefault("project", {})
        mem["project"]["phase"] = "planning"
        mem["project"]["status"] = "planning"
        mem["project"]["updated_at"] = utc_now()
        save_memory(mem)
        
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/clarification/reply")
def clarification_reply(request: ProjectClarificationReply):
    """Reply to a clarification request from an agent."""
    try:
        from orchestrator import approve_proposal
        from shared_state import load_memory, save_memory
        
        mem = load_memory()
        approve_proposal(mem, request.reply)
        save_memory(mem)
        
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/load")
def load_project(payload: dict):
    """Load an existing project by ID."""
    try:
        from shared_state import load_memory, save_memory
        
        project_id = payload.get("project_id")
        if not project_id:
            return {"ok": False, "error": "project_id required"}
        
        mem = load_memory()
        
        # Find project in history
        projects = mem.get("projects", [])
        target = None
        for p in projects:
            if p.get("id") == project_id:
                target = p
                break
        
        if not target:
            return {"ok": False, "error": "Project not found"}
        
        mem["project"] = target
        save_memory(mem)
        
        return {"ok": True, "project": target}
    except Exception as e:
        return {"ok": False, "error": str(e)}
