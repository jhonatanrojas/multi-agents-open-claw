"""Models router - handles model management and configuration."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/models", tags=["models"])

class ModelUpdate(BaseModel):
    arch: Optional[str] = None
    byte: Optional[str] = None
    pixel: Optional[str] = None

class SingleModelUpdate(BaseModel):
    agent: str
    model: str

class DefaultsUpdate(BaseModel):
    default: str
    fallback: Optional[str] = None


@router.get("")
def get_models():
    """Get current agent models and normalized model catalog."""
    from openclaw_sdk import get_agent_models, get_available_models
    
    try:
        agent_models = get_agent_models()
        available = get_available_models()
        return {
            "agents": agent_models,
            "available": available,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/available")
def get_available_models_endpoint():
    """Get normalized flat list of gateway models + local fallback."""
    from openclaw_sdk import get_available_models
    
    try:
        models = get_available_models()
        return {"models": models}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/providers")
def get_model_providers():
    """Get provider configs (without API keys)."""
    from openclaw_sdk import load_openclaw_config
    
    try:
        config = load_openclaw_config()
        providers = config.get("providers", {})
        # Sanitize - remove sensitive data
        safe_providers = {}
        for name, provider in providers.items():
            safe_providers[name] = {
                k: v for k, v in provider.items() 
                if not any(secret in k.lower() for secret in ["key", "token", "secret", "password"])
            }
        return {"providers": safe_providers}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.put("/agent")
def update_agent_model(update: SingleModelUpdate):
    """Change model for a single agent."""
    from openclaw_sdk import set_agent_model
    
    try:
        set_agent_model(update.agent, update.model)
        return {"ok": True, "agent": update.agent, "model": update.model}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.put("")
def update_models(update: ModelUpdate):
    """Bulk-update arch/byte/pixel models."""
    from openclaw_sdk import set_agent_model
    
    updated = {}
    try:
        if update.arch:
            set_agent_model("arch", update.arch)
            updated["arch"] = update.arch
        if update.byte:
            set_agent_model("byte", update.byte)
            updated["byte"] = update.byte
        if update.pixel:
            set_agent_model("pixel", update.pixel)
            updated["pixel"] = update.pixel
        return {"ok": True, "updated": updated}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.put("/defaults")
def update_defaults(update: DefaultsUpdate):
    """Change global default model + fallbacks."""
    from openclaw_sdk import set_default_model
    
    try:
        set_default_model(update.default, fallback=update.fallback)
        return {"ok": True, "default": update.default, "fallback": update.fallback}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/test")
def test_model(payload: dict):
    """Test a model with a simple prompt."""
    # Implementation would test the model
    return {"ok": True, "message": "Model test endpoint"}


@router.get("/health")
def get_models_health():
    """Get health summary for models."""
    from model_fallback import get_models_health_report
    
    try:
        return get_models_health_report()
    except Exception as e:
        return {"ok": False, "error": str(e)}
