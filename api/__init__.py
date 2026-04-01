"""
API routers package for OpenClaw Multi-Agent Dashboard.

This package contains domain-specific routers that were previously
in dashboard_api.py. Each module handles a specific domain:

- auth: Authentication endpoints (login, logout, session)
- state: State and health endpoints
- projects: Project management (start, pause, resume, delete)
- models: Model management and configuration
- runtime: Runtime orchestrator management
- files: File viewing and listing
- agents: Agent steering and control
- tasks: Task pause/resume
- context: Context editing
- runs: RunContext management (F1.1)
- runtime_state: UI synchronization (F1.4)
"""

from fastapi import APIRouter

from .auth import router as auth_router
from .state import router as state_router
from .projects import router as projects_router
from .models import router as models_router
from .runtime import router as runtime_router
from .files import router as files_router
from .agents import router as agents_router
from .tasks import router as tasks_router
from .context import router as context_router
from .runs import router as runs_router
from .runtime_state import router as runtime_state_router

__all__ = [
    "auth_router",
    "state_router",
    "projects_router",
    "models_router",
    "runtime_router",
    "files_router",
    "agents_router",
    "tasks_router",
    "context_router",
    "runs_router",
    "runtime_state_router",
]
