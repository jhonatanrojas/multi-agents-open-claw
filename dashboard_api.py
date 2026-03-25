#!/usr/bin/env python3
"""
dashboard_api.py - SSE + WebSocket + REST API for the Dev Squad Dashboard
--------------------------------------------------------------------------
Endpoints:
  GET  /health             -> health check (no auth required)
  GET  /api/health         -> alias
  GET  /api/state          -> current shared memory snapshot
  GET  /api/stream         -> SSE stream of state changes
  WS   /ws/state           -> WebSocket push of state changes (GAP-9)
  GET  /api/agents/world   -> proxies Miniverse /api/agents
  GET  /api/logs           -> last log entries
  POST /api/project/start  -> triggers orchestrator
  GET  /api/models           -> current agent models + available models from OpenClaw
  GET  /api/models/available -> flat list of all models across providers
  GET  /api/models/providers -> provider configs (without API keys)
  PUT  /api/models           -> bulk-update arch/byte/pixel models
  PUT  /api/models/agent     -> change model for a single agent
  PUT  /api/models/defaults  -> change global default model + fallbacks

Auth (GAP-1 / P5):
  All endpoints except /health and /api/health require the header
    X-API-Key: <value of DASHBOARD_API_KEY env var>
  when DASHBOARD_API_KEY is set.  Set to the empty string to disable auth.
  Example key for development: dev-squad-api-key-2026
"""

import json
import asyncio
import re
import sys
import subprocess
import os
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import requests
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from openclaw_sdk import (
    get_available_models,
    get_agent_models,
    load_openclaw_config,
    set_agent_model as sdk_set_agent_model,
    set_default_model as sdk_set_default_model,
)
from shared_state import BASE_DIR, load_memory, _pid_is_alive

MINIVERSE_URL = os.getenv("MINIVERSE_URL", "https://miniverse-public-production.up.railway.app")
LOCK_FILE = BASE_DIR / "logs" / "orchestrator.lock"
JSONL_LOG_FILE = BASE_DIR / "logs" / "orchestrator.jsonl"

# GAP-1 / P5 — API key auth (empty string = disabled)
_API_KEY: str = os.getenv("DASHBOARD_API_KEY", "")

# Endpoints exempt from auth (public monitoring + streaming)
_AUTH_EXEMPT = {"/health", "/api/health"}


# ── WebSocket broadcaster (GAP-9) ─────────────────────────────────────────────

class _StateBroadcaster:
    """Single background loop that pushes state to all WebSocket clients."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._last: str | None = None

    def add(self, ws: WebSocket) -> None:
        self._clients.add(ws)

    def remove(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def run(self) -> None:
        while True:
            if self._clients:
                current = json.dumps(load_memory(), sort_keys=True)
                if current != self._last:
                    self._last = current
                    dead: set[WebSocket] = set()
                    for ws in list(self._clients):
                        try:
                            await ws.send_text(current)
                        except Exception:
                            dead.add(ws)
                    self._clients -= dead
            await asyncio.sleep(1)


_broadcaster = _StateBroadcaster()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    asyncio.create_task(_broadcaster.run())
    yield


# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="Dev Squad Dashboard API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth middleware (GAP-1 / P5) ──────────────────────────────────────────────

@app.middleware("http")
async def _auth_middleware(request: Request, call_next):
    if _API_KEY and request.url.path not in _AUTH_EXEMPT:
        if request.headers.get("X-API-Key") != _API_KEY:
            return JSONResponse(
                {"error": "Unauthorized — provide a valid X-API-Key header"},
                status_code=401,
            )
    return await call_next(request)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_jsonl_tail(path: Path, limit: int = 100) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    tail: deque[str] = deque(maxlen=limit)
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            tail.append(line)
    records: list[dict[str, Any]] = []
    for line in tail:
        try:
            records.append(json.loads(line))
        except Exception:
            continue
    return records


def _validate_brief(brief: str) -> str:
    """Sanitize and validate the project brief (GAP-2)."""
    brief = brief.strip()
    if len(brief) < 10:
        raise ValueError("El brief debe tener al menos 10 caracteres.")
    if len(brief) > 2000:
        raise ValueError("El brief no puede superar los 2000 caracteres.")
    # Strip ASCII control chars except tab and newline
    brief = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", brief)
    return brief


def _load_models_config() -> dict[str, Any]:
    """Build models config from the live OpenClaw configuration."""
    agents = get_agent_models()
    available = get_available_models()
    defaults = agents.pop("_defaults", {})
    return {
        "agents": agents,
        "available": available,
        "defaults": defaults,
    }


def build_health_snapshot() -> dict[str, Any]:
    mem = load_memory()
    orchestrator_state = mem.get("project", {}).get("orchestrator", {}) or {}
    lock_state: dict[str, Any] = {"exists": LOCK_FILE.exists(), "pid": None, "alive": False}
    if LOCK_FILE.exists():
        try:
            lock_payload = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
        except Exception:
            lock_payload = {}
        lock_state["pid"] = lock_payload.get("pid")
        lock_state["alive"] = _pid_is_alive(lock_state["pid"])
        lock_state["started_at"] = lock_payload.get("started_at")
    issues: list[str] = []
    if lock_state["exists"] and not lock_state["alive"] and lock_state["pid"] is not None:
        issues.append("lockfile obsoleto")
    if orchestrator_state.get("status") == "error":
        issues.append("error del orquestador")
    ok = len(issues) == 0
    return {
        "ok": ok,
        "service": "dashboard_api",
        "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "lockfile": lock_state,
        "orchestrator": orchestrator_state,
        "issues": issues,
        "memory_updated_at": mem.get("project", {}).get("updated_at"),
        "auth_enabled": bool(_API_KEY),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
@app.get("/api/health")
def health():
    snapshot = build_health_snapshot()
    return JSONResponse(snapshot, status_code=200 if snapshot["ok"] else 503)


@app.get("/api/state")
def get_state():
    return load_memory()


@app.get("/api/stream")
async def stream_state():
    """Server-Sent Events stream — pushes state every 2 s with keepalive."""
    async def generator():
        last = None
        while True:
            current = json.dumps(load_memory(), sort_keys=True)
            if current != last:
                last = current
                yield f"data: {current}\n\n"
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(generator(), media_type="text/event-stream")


@app.websocket("/ws/state")
async def ws_state(websocket: WebSocket):
    """WebSocket endpoint — receives push updates at ~1 s interval (GAP-9)."""
    await websocket.accept()
    _broadcaster.add(websocket)
    # Send current snapshot immediately on connect
    await websocket.send_text(json.dumps(load_memory(), sort_keys=True))
    try:
        while True:
            # Keep alive; detect client disconnect via receive
            await asyncio.wait_for(websocket.receive_text(), timeout=30)
    except (WebSocketDisconnect, asyncio.TimeoutError, Exception):
        _broadcaster.remove(websocket)


@app.get("/api/agents/world")
def agents_in_world():
    """Proxy Miniverse agent list."""
    try:
        r = requests.get(f"{MINIVERSE_URL}/api/agents", timeout=5)
        return r.json()
    except Exception as e:
        return {"error": str(e), "agents": []}


# ── Models config (GAP-5 / P6) ────────────────────────────────────────────────

@app.get("/api/models")
def get_models():
    """Return current model assignments and all available models from OpenClaw config."""
    return _load_models_config()


@app.get("/api/models/available")
def get_available():
    """Return flat list of all models available across configured providers."""
    return {"models": get_available_models()}


class AgentModelUpdate(BaseModel):
    """Update the model for a single agent."""
    agent_id: str
    model: str


class ModelsUpdate(BaseModel):
    """Bulk update: change model for one or more agents at once."""
    arch: str | None = None
    byte: str | None = None
    pixel: str | None = None


class DefaultModelUpdate(BaseModel):
    """Update the global default model and optional fallbacks."""
    primary: str
    fallbacks: list[str] | None = None


@app.put("/api/models/agent")
def update_agent_model(update: AgentModelUpdate):
    """Change the model for a single agent in openclaw.json.

    The change takes effect on the next ``openclaw agent`` invocation —
    no gateway restart needed.
    """
    try:
        updated = sdk_set_agent_model(update.agent_id, update.model)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return {
        "saved": True,
        "agent": updated,
        "config": _load_models_config(),
    }


@app.put("/api/models")
def update_models(update: ModelsUpdate):
    """Bulk-update model assignments for arch/byte/pixel.

    Writes directly to ``~/.openclaw/openclaw.json``.
    Changes take effect on the next agent invocation.
    """
    errors: list[str] = []
    updated: dict[str, Any] = {}
    for agent_id, model in update.model_dump(exclude_none=True).items():
        try:
            sdk_set_agent_model(agent_id, model)
            updated[agent_id] = model
        except ValueError as exc:
            errors.append(str(exc))

    if errors and not updated:
        return JSONResponse({"errors": errors}, status_code=422)

    return {
        "saved": True,
        "updated": updated,
        "errors": errors or None,
        "config": _load_models_config(),
    }


@app.put("/api/models/defaults")
def update_default_model(update: DefaultModelUpdate):
    """Change the global default model (used by agents without explicit model)."""
    try:
        result = sdk_set_default_model(update.primary, update.fallbacks)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return {
        "saved": True,
        "defaults": result,
        "config": _load_models_config(),
    }


@app.get("/api/models/providers")
def get_providers():
    """Return the raw providers block from openclaw.json (without secrets)."""
    cfg = load_openclaw_config()
    providers = cfg.get("models", {}).get("providers", {})
    # Strip API keys from the response.
    safe: dict[str, Any] = {}
    for pid, pcfg in providers.items():
        entry = {k: v for k, v in pcfg.items() if k != "apiKey"}
        entry["has_api_key"] = "apiKey" in pcfg
        safe[pid] = entry
    return {"providers": safe}


# ── Project launch ────────────────────────────────────────────────────────────

class ProjectRequest(BaseModel):
    brief: str
    repo_url: str | None = None
    repo_name: str | None = None
    branch: str | None = None
    allow_init_repo: bool = False
    dry_run: bool = False
    task_timeout_sec: int = 1800
    phase_timeout_sec: int = 7200
    retry_attempts: int = 3
    retry_delay_sec: float = 2.0
    max_parallel_byte: int = 1   # GAP-8
    max_parallel_pixel: int = 1  # GAP-8
    webhook_url: str | None = None  # P9


@app.post("/api/project/start")
async def start_project(req: ProjectRequest):
    """Spawn orchestrator in background."""
    # GAP-2 — validate brief before spawning subprocess
    try:
        safe_brief = _validate_brief(req.brief)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    args = [sys.executable, str(BASE_DIR / "orchestrator.py")]
    if req.repo_url:
        args.extend(["--repo-url", req.repo_url])
    if req.repo_name:
        args.extend(["--repo-name", req.repo_name])
    if req.branch:
        args.extend(["--branch", req.branch])
    if req.allow_init_repo:
        args.append("--allow-init-repo")
    if req.dry_run:
        args.append("--dry-run")
    args.extend(["--task-timeout-sec", str(req.task_timeout_sec)])
    args.extend(["--phase-timeout-sec", str(req.phase_timeout_sec)])
    args.extend(["--retry-attempts", str(req.retry_attempts)])
    args.extend(["--retry-delay-sec", str(req.retry_delay_sec)])
    args.extend(["--max-parallel-byte", str(req.max_parallel_byte)])
    args.extend(["--max-parallel-pixel", str(req.max_parallel_pixel)])
    if req.webhook_url:
        args.extend(["--webhook-url", req.webhook_url])
    args.append(safe_brief)

    log_path = BASE_DIR / "logs" / "orchestrator.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        subprocess.Popen(
            args,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=BASE_DIR,
        )
    return {
        "status": "started",
        "message": "Orquestador iniciado correctamente",
        "brief": safe_brief,
        "ts": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    }


@app.get("/api/logs")
def get_logs():
    mem = load_memory()
    return {
        "log": mem.get("log", [])[-100:],
        "structured_log": _read_jsonl_tail(JSONL_LOG_FILE, 100),
    }
