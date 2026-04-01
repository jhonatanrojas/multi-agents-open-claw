"""Context router - handles context editing."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/context", tags=["context"])


class ContextUpdateRequest(BaseModel):
    """Request to update shared narrative context."""
    content: str
    append: bool = False


class ContextUpdateResponse(BaseModel):
    """Response after updating context."""
    ok: bool
    context: Optional[str] = None


@router.patch("", response_model=ContextUpdateResponse)
def update_context(request: ContextUpdateRequest):
    """
    Update shared narrative context and track the change.
    
    This endpoint allows operators to edit the shared context that
    agents use for coordination. Changes are tracked with timestamps.
    """
    try:
        from shared_state import load_memory, save_memory, utc_now
        
        mem = load_memory()
        
        if "context" not in mem:
            mem["context"] = {}
        
        if "narrative" not in mem["context"]:
            mem["context"]["narrative"] = ""
        
        if request.append:
            mem["context"]["narrative"] += f"\n\n{request.content}"
        else:
            mem["context"]["narrative"] = request.content
        
        # Track change
        if "context_history" not in mem:
            mem["context_history"] = []
        
        mem["context_history"].append({
            "timestamp": utc_now(),
            "action": "append" if request.append else "replace",
            "preview": request.content[:100] + "..." if len(request.content) > 100 else request.content,
        })
        
        # Trim history
        if len(mem["context_history"]) > 50:
            mem["context_history"] = mem["context_history"][-50:]
        
        save_memory(mem)
        
        return ContextUpdateResponse(
            ok=True,
            context=mem["context"]["narrative"]
        )
    except Exception as e:
        return ContextUpdateResponse(ok=False, context=None)
