"""Runtime router - handles runtime orchestrator management."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/runtime", tags=["runtime"])


@router.get("/orchestrators")
def get_runtime_orchestrators():
    """Return runtime orchestrator processes snapshot."""
    try:
        from shared_state import utc_now
        from dashboard_api import _runtime_process_snapshot
        
        return {
            "timestamp": utc_now(),
            **_runtime_process_snapshot(),
        }
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"ok": False, "error": str(e)},
            status_code=500
        )


class CleanupRequest(BaseModel):
    mode: str = "duplicates"  # "duplicates" or "all"
    force: bool = True


@router.post("/orchestrators/cleanup")
async def cleanup_orchestrators(payload: CleanupRequest):
    """Clean up orchestrator processes."""
    from dashboard_api import _cleanup_orchestrator_pids, _runtime_process_snapshot
    from shared_state import load_memory, save_memory, refresh_project_runtime_state, utc_now
    from pathlib import Path
    
    BASE_DIR = Path(__file__).resolve().parent.parent
    LOCK_FILE = BASE_DIR / "logs" / "orchestrator.lock"
    
    try:
        snapshot = _runtime_process_snapshot()
        primary_pid = snapshot.get("primary_pid")
        processes = snapshot.get("processes", [])
        
        if payload.mode == "all":
            target_pids = [int(proc["pid"]) for proc in processes if proc.get("pid")]
        else:
            target_pids = [int(proc["pid"]) for proc in snapshot.get("duplicates", []) if proc.get("pid")]
        
        result = await _cleanup_orchestrator_pids(target_pids, force=payload.force)
        
        if payload.mode == "all":
            if LOCK_FILE.exists():
                try:
                    LOCK_FILE.unlink()
                except FileNotFoundError:
                    pass
            mem = load_memory()
            mem.setdefault("project", {})
            mem["project"].setdefault("orchestrator", {})
            mem["project"]["orchestrator"].update({
                "status": "paused",
                "phase": "paused",
                "detail": "Ejecuciones detenidas desde el dashboard",
                "updated_at": utc_now(),
            })
            mem["project"]["updated_at"] = utc_now()
            refresh_project_runtime_state(mem)
            save_memory(mem)
        
        return {"ok": True, "cleaned": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}
