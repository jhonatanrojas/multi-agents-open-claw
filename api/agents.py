"""Agents router - handles agent steering and control."""

from fastapi import APIRouter, Path
from pydantic import BaseModel

router = APIRouter(prefix="/api/agents", tags=["agents"])


class SteerRequest(BaseModel):
    """Request to send a steering message to an active agent."""
    message: str
    urgent: bool = False


class SteerResponse(BaseModel):
    """Response after sending a steer message."""
    ok: bool
    agent_id: str


@router.post("/{agent_id}/steer", response_model=SteerResponse)
def steer_agent(
    agent_id: str = Path(..., description="Agent ID to steer"),
    request: SteerRequest = None
):
    """
    Send a steer message to an active agent.
    
    Steering allows operators to guide agent behavior without stopping
    the current task. The message is queued and processed on the agent's
    next heartbeat cycle.
    """
    try:
        from shared_state import load_memory, save_memory
        
        mem = load_memory()
        
        # Initialize steer queue if needed
        if "steer_queue" not in mem:
            mem["steer_queue"] = {}
        
        if agent_id not in mem["steer_queue"]:
            mem["steer_queue"][agent_id] = []
        
        # Add steer message
        steer_entry = {
            "message": request.message if request else "",
            "urgent": request.urgent if request else False,
            "timestamp": __import__('time').time(),
        }
        mem["steer_queue"][agent_id].append(steer_entry)
        
        # Trim queue if too long
        if len(mem["steer_queue"][agent_id]) > 10:
            mem["steer_queue"][agent_id] = mem["steer_queue"][agent_id][-10:]
        
        save_memory(mem)
        
        return SteerResponse(ok=True, agent_id=agent_id)
    except Exception as e:
        return SteerResponse(ok=False, agent_id=agent_id)


@router.get("/world")
def get_agents_world():
    """Proxy to Miniverse /api/agents."""
    try:
        import requests
        import os
        
        miniverse_url = os.getenv("MINIVERSE_URL", "http://127.0.0.1:9999")
        response = requests.get(f"{miniverse_url}/api/agents", timeout=5)
        return response.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}
