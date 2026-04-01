"""State router - handles state, health, and streaming endpoints."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter(tags=["state"])

@router.get("/health")
@router.get("/api/health")
def health():
    """Health check endpoint for monitoring."""
    try:
        from dashboard_api import build_health_snapshot
        snapshot = build_health_snapshot()
        return JSONResponse(snapshot, status_code=200 if snapshot["ok"] else 503)
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": str(e)},
            status_code=503
        )


@router.get("/api/state")
def get_state():
    """Return current shared memory snapshot."""
    try:
        from shared_state import load_memory
        return load_memory()
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": f"Failed to load state: {str(e)}"},
            status_code=500
        )


@router.get("/api/stream")
async def get_stream(request: Request):
    """SSE stream of state changes."""
    # This is a placeholder - the actual implementation remains in dashboard_api
    # for now due to complexity
    from dashboard_api import _stream_endpoint
    return await _stream_endpoint(request)


@router.get("/api/logs")
def get_logs():
    """Return recent log entries from memory and structured log file."""
    try:
        from shared_state import load_memory
        from dashboard_api import _read_jsonl_tail, JSONL_LOG_FILE
        
        mem = load_memory()
        return {
            "log": mem.get("log", [])[-100:],
            "structured_log": _read_jsonl_tail(JSONL_LOG_FILE, 100),
        }
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": str(e)},
            status_code=500
        )
