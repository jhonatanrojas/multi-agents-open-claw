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
  GET  /api/gateway/events -> live OpenClaw Gateway agent events
  WS   /ws/gateway-events  -> WebSocket push of Gateway agent events
  GET  /api/agents/world   -> proxies Miniverse /api/agents
  GET  /api/miniverse      -> GitHub repo metadata + live Miniverse snapshot
  GET  /api/logs           -> last log entries
  POST /api/project/start  -> triggers orchestrator
  POST /api/project/extend  -> enqueue a follow-up task on the current project
  POST /api/project/retry-planning -> re-run planning for the current project
  GET  /api/models           -> current agent models + normalized model catalog
  GET  /api/models/available -> normalized flat list of gateway models + local fallback
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
import hashlib
import mimetypes
import re
import sys
import subprocess
import os
import signal
import time
from concurrent.futures import ThreadPoolExecutor, wait
from copy import deepcopy
import shutil
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from typing import Any

import requests
import websockets
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, Response
from fastapi import Cookie
from pydantic import BaseModel, Field
import secrets

from openclaw_sdk import (
    get_available_models,
    get_agent_models,
    load_openclaw_config,
    set_agent_model as sdk_set_agent_model,
    set_default_model as sdk_set_default_model,
)
from coordination import (
    ensure_project_id,
    format_telegram_blocker_message,
    infer_project_structure,
    send_telegram_message,
    update_project_history,
)
from shared_state import (
    BASE_DIR,
    DEFAULT_MEMORY,
    _pid_is_alive,
    get_project_blockers,
    load_memory,
    refresh_project_runtime_state,
    save_memory,
    utc_now,
)
from orchestrator import approve_proposal, propose_follow_up_task

# Import API routers (F0.5 - Modularization)
from api import (
    auth_router,
    state_router,
    projects_router,
    models_router,
    runtime_router,
    files_router,
    agents_router,
    tasks_router,
    context_router,
    runs_router,
    runtime_state_router,
)

# Import centralized configuration (F0.7)
from config import config, load_config

from websockets.exceptions import ConnectionClosed

MINIVERSE_URL = os.getenv("MINIVERSE_URL", "http://127.0.0.1:9999")
MINIVERSE_UI_URL = os.getenv("MINIVERSE_UI_URL", MINIVERSE_URL).strip() or MINIVERSE_URL
MINIVERSE_GITHUB_OWNER = "ianscott313"
MINIVERSE_GITHUB_REPO = "miniverse"
MINIVERSE_GITHUB_API_URL = f"https://api.github.com/repos/{MINIVERSE_GITHUB_OWNER}/{MINIVERSE_GITHUB_REPO}"
MINIVERSE_REQUEST_TIMEOUT_SEC = float(os.getenv("MINIVERSE_REQUEST_TIMEOUT_SEC", "6"))
MINIVERSE_CACHE_TTL_SEC = float(os.getenv("MINIVERSE_CACHE_TTL_SEC", "300"))
MINIVERSE_MOCK_FILE = BASE_DIR / "data" / "miniverse-mock.json"
LOCK_FILE = BASE_DIR / "logs" / "orchestrator.lock"
JSONL_LOG_FILE = BASE_DIR / "logs" / "orchestrator.jsonl"
OPENCLAW_RUNTIME_HOME = Path(os.getenv("OPENCLAW_RUNTIME_HOME", str(Path.home() / ".openclaw-runtime")))
OPENCLAW_RUNTIME_PROFILE = os.getenv("OPENCLAW_PROFILE", "multi-agents-runtime-v2").strip()
_MINIVERSE_CACHE: dict[str, Any] = {
    "signature": None,
    "expires_at": 0.0,
    "payload": None,
}

# GAP-1 / P5 — API key auth (empty string = disabled)
_API_KEY: str = os.getenv("DASHBOARD_API_KEY", "")

# Session cookie auth for SSE/WebSocket (F0.1)
_SESSION_SECRET: str = os.getenv("DASHBOARD_SESSION_SECRET", "")
if not _SESSION_SECRET and _API_KEY:
    # Derive a stable secret from API key if not explicitly set
    _SESSION_SECRET = hashlib.sha256(f"sse-session-{_API_KEY}".encode()).hexdigest()[:32]

# Active sessions: token -> {created_at, last_used}
# Persisted to MEMORY.json for surviving gateway restarts
_active_sessions: dict[str, dict[str, Any]] = {}
_SESSION_MAX_AGE_SEC: int = int(os.getenv("DASHBOARD_SESSION_MAX_AGE", "86400"))  # 24 hours
_SESSION_CLEANUP_INTERVAL_SEC: int = 3600  # Cleanup every hour
_SESSION_STATE_KEY = "_sessions"  # Key in MEMORY.json for session persistence

def _load_sessions_from_memory() -> None:
    """Load persisted sessions from MEMORY.json on startup."""
    global _active_sessions
    try:
        mem = load_memory()
        persisted = mem.get(_SESSION_STATE_KEY, {})
        if isinstance(persisted, dict):
            # Filter out expired sessions
            now = datetime.now()
            valid_sessions = {}
            for token, session in persisted.items():
                if not isinstance(session, dict):
                    continue
                try:
                    last_used = datetime.fromisoformat(session.get("last_used", ""))
                    if now - last_used <= timedelta(seconds=_SESSION_MAX_AGE_SEC):
                        valid_sessions[token] = session
                except Exception:
                    continue
            _active_sessions = valid_sessions
            if valid_sessions:
                print(f"[F0.1] Restored {len(valid_sessions)} valid session(s) from persistence")
    except Exception as e:
        print(f"[F0.1] Warning: Could not load persisted sessions: {e}")

def _save_sessions_to_memory() -> None:
    """Save active sessions to MEMORY.json for persistence across restarts."""
    try:
        mem = load_memory()
        mem[_SESSION_STATE_KEY] = _active_sessions
        save_memory(mem)
    except Exception as e:
        print(f"[F0.1] Warning: Could not persist sessions: {e}")

# Load sessions on module import
_load_sessions_from_memory()

# Endpoints exempt from auth (public monitoring)
_AUTH_EXEMPT = {
    "/health", 
    "/api/health",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/session",
}

# Endpoints that accept cookie auth (SSE/WebSocket)
# Endpoints that accept cookie auth (SSE/WebSocket and regular API)
_COOKIE_AUTH_PATHS = {
    "/api/stream",
    "/api/state", 
    "/api/models",
    "/api/models/available",
    "/api/models/providers",
    "/api/models/health",
    "/api/files",
    "/api/gateway/events",
    "/api/miniverse",
    "/api/runtime/orchestrators",
    "/api/context",
    "/api/runs",
    "/api/tasks",
    "/api/agents",
    "/ws/state",
    "/ws/gateway-events"
}
GATEWAY_EVENT_LIMIT = 300
GATEWAY_AGENT_RE = re.compile(r"^agent:(main|arch|byte|pixel):", re.IGNORECASE)
RESUME_COOLDOWN_DEFAULT_SEC = int(os.getenv("OPENCLAW_RESUME_COOLDOWN_SEC", "60"))
RESUME_COOLDOWN_PROVIDER_SEC = int(os.getenv("OPENCLAW_PROVIDER_RESUME_COOLDOWN_SEC", "300"))
_RESUME_PROVIDER_SIGNALS = (
    "429",
    "rate limit",
    "too many requests",
    "quota exceeded",
    "insufficient balance",
    "insufficient account balance",
    "unauthorized",
    "forbidden",
    "invalid api key",
    "api key",
    "invalid or expired token",
)


def _create_session() -> str:
    """Create a new session token for cookie-based auth."""
    token = secrets.token_urlsafe(32)
    now = utc_now()
    _active_sessions[token] = {
        "created_at": now,
        "last_used": now,
    }
    # Persist sessions to survive gateway restarts
    _save_sessions_to_memory()
    return token


def _validate_session(session_token: str | None) -> bool:
    """Validate a session token and update last_used."""
    if not session_token or not _API_KEY:
        return not _API_KEY  # If no API key required, allow all
    
    # Reload sessions from persistence to handle cross-process scenarios
    # (e.g., after gateway restart or load balancer switch)
    _load_sessions_from_memory()
    
    if session_token not in _active_sessions:
        return False
    session = _active_sessions[session_token]
    try:
        last_used = datetime.fromisoformat(session["last_used"])
        # Handle both timezone-aware and naive datetimes
        if last_used.tzinfo is None:
            now = datetime.now()
        else:
            now = datetime.now(timezone.utc)
        max_age = timedelta(seconds=_SESSION_MAX_AGE_SEC)
        if now - last_used > max_age:
            del _active_sessions[session_token]
            _save_sessions_to_memory()
            return False
    except Exception:
        return False
    session["last_used"] = utc_now()
    # Persist updated last_used time
    _save_sessions_to_memory()
    return True


def _cleanup_expired_sessions() -> None:
    """Remove expired sessions. Called periodically."""
    now = datetime.now()
    expired = []
    for token, session in _active_sessions.items():
        try:
            last_used = datetime.fromisoformat(session["last_used"])
            if now - last_used > timedelta(seconds=_SESSION_MAX_AGE_SEC):
                expired.append(token)
        except Exception:
            expired.append(token)
    for token in expired:
        del _active_sessions[token]
    # Persist cleaned sessions
    if expired:
        _save_sessions_to_memory()
        print(f"[F0.1] Cleaned up {len(expired)} expired session(s)")


def _resume_cooldown_seconds(task: dict[str, Any]) -> int:
    """Return the cooldown to apply before resuming a task."""
    text = " ".join(
        str(task.get(key) or "")
        for key in ("failure_kind", "error", "blocked_note", "next_action", "raw_response")
    ).lower()
    if any(signal in text for signal in _RESUME_PROVIDER_SIGNALS):
        return RESUME_COOLDOWN_PROVIDER_SEC
    failure_kind = str(task.get("failure_kind") or "").lower()
    if failure_kind in {"format", "parse"} or "json inválido" in text or "json invalid" in text:
        return max(RESUME_COOLDOWN_DEFAULT_SEC, 90)
    if failure_kind in {"blocked", "review"}:
        return RESUME_COOLDOWN_DEFAULT_SEC
    return RESUME_COOLDOWN_DEFAULT_SEC


def _resume_not_before(seconds: int) -> str:
    return (
        datetime.now(timezone.utc)
        + timedelta(seconds=max(0, int(seconds)))
    ).replace(tzinfo=None).isoformat()


def _set_task_resume_cooldown(task: dict[str, Any], seconds: int) -> str:
    """Set not_before without shortening an existing, later cooldown."""
    next_not_before = _resume_not_before(seconds)
    current = task.get("not_before")
    if isinstance(current, str) and current.strip():
        try:
            if datetime.fromisoformat(current) >= datetime.fromisoformat(next_not_before):
                return current
        except Exception:
            pass
    task["not_before"] = next_not_before
    return next_not_before


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


def _gateway_connection_details() -> dict[str, Any]:
    cfg = load_openclaw_config()
    gateway_cfg = cfg.get("gateway", {}) if isinstance(cfg, dict) else {}
    gateway_auth = gateway_cfg.get("auth", {}) if isinstance(gateway_cfg, dict) else {}
    token = (
        os.getenv("OPENCLAW_GATEWAY_TOKEN")
        or gateway_auth.get("token")
        or gateway_cfg.get("token")  # También buscar en gateway.token
        or ""
    )
    host = os.getenv("OPENCLAW_GATEWAY_HOST") or gateway_cfg.get("host") or "127.0.0.1"
    port = int(os.getenv("OPENCLAW_GATEWAY_PORT") or gateway_cfg.get("port") or 18789)
    return {
        "url": f"ws://{host}:{port}",
        "host": host,
        "port": port,
        "token": token,
    }


def _runtime_profile_root() -> Path | None:
    profile = OPENCLAW_RUNTIME_PROFILE.strip()
    if not profile:
        return None
    return OPENCLAW_RUNTIME_HOME / f".openclaw-{profile}"


def _resolve_provider_secret(cfg: dict[str, Any], provider: str) -> str:
    """Resolve an API key/token for *provider* from config, env, or runtime auth files."""
    providers = cfg.get("models", {}).get("providers", {}) if isinstance(cfg, dict) else {}
    provider_cfg = providers.get(provider, {}) if isinstance(providers, dict) else {}

    def _clean_secret(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        secret = value.strip()
        if not secret:
            return ""
        if secret.startswith("${") and secret.endswith("}"):
            env_name = secret[2:-1].strip()
            if env_name:
                return os.getenv(env_name, "").strip()
            return ""
        return secret

    for key_name in ("apiKey", "api_key", "key", "token", "access"):
        secret = _clean_secret(provider_cfg.get(key_name))
        if secret:
            return secret

    auth_profiles = cfg.get("auth", {}).get("profiles", {}) if isinstance(cfg, dict) else {}
    if isinstance(auth_profiles, dict):
        for profile_name, profile in auth_profiles.items():
            if not isinstance(profile, dict):
                continue
            if profile.get("provider") != provider:
                continue
            for key_name in ("key", "token", "access"):
                secret = _clean_secret(profile.get(key_name))
                if secret:
                    return secret

    runtime_root = _runtime_profile_root()
    if runtime_root is None:
        return ""

    agents_dir = runtime_root / "agents"
    if not agents_dir.exists():
        return ""

    for auth_file in agents_dir.glob("*/agent/auth-profiles.json"):
        try:
            payload = json.loads(auth_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        profiles = payload.get("profiles", {}) if isinstance(payload, dict) else {}
        if not isinstance(profiles, dict):
            continue
        for profile in profiles.values():
            if not isinstance(profile, dict):
                continue
            if profile.get("provider") != provider:
                continue
            for key_name in ("key", "token", "access"):
                secret = _clean_secret(profile.get(key_name))
                if secret:
                    return secret
    return ""


def _parse_gateway_frame(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8", errors="replace")
        except Exception:
            return None
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        try:
            raw = json.loads(raw)
        except Exception:
            if raw.lower() == "hello-ok":
                return {"type": "hello-ok"}
            return {"type": "text", "raw": raw}
    return raw if isinstance(raw, dict) else None


def _gateway_frame_type(frame: dict[str, Any]) -> str:
    frame_type = str(frame.get("type") or "").strip().lower()
    if frame_type:
        return frame_type
    event = str(frame.get("event") or "").strip().lower()
    return event


def _gateway_is_challenge(frame: dict[str, Any]) -> bool:
    frame_type = _gateway_frame_type(frame)
    if "challenge" in frame_type:
        return True
    payload = frame.get("payload")
    if isinstance(payload, dict):
        payload_type = str(payload.get("type") or "").strip().lower()
        if "challenge" in payload_type:
            return True
        if payload.get("nonce"):
            return True
    return False


def _gateway_extract_nonce(frame: dict[str, Any]) -> str | None:
    for source in (frame, frame.get("payload") if isinstance(frame.get("payload"), dict) else None):
        if not isinstance(source, dict):
            continue
        for key in ("nonce", "challenge", "challengeNonce"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _gateway_is_hello_ok(frame: dict[str, Any]) -> bool:
    frame_type = _gateway_frame_type(frame)
    if frame_type in {"hello-ok", "hello.ok"}:
        return True
    if frame_type != "res" or frame.get("ok") is not True:
        return False
    payload = frame.get("payload")
    if isinstance(payload, dict):
        payload_type = str(payload.get("type") or "").strip().lower()
        if payload_type == "hello-ok":
            return True
    return False


def _gateway_connect_frame(token: str, nonce: str | None = None) -> dict[str, Any]:
    cfg = load_openclaw_config()
    version = "openclaw-dashboard"
    if isinstance(cfg, dict):
        meta = cfg.get("meta", {})
        if isinstance(meta, dict):
            touched_version = meta.get("lastTouchedVersion")
            if isinstance(touched_version, str) and touched_version.strip():
                version = touched_version.strip()
    params: dict[str, Any] = {
        "minProtocol": 3,
        "maxProtocol": 3,
        "client": {
            "id": "gateway-client",
            "displayName": "openclaw-dashboard",
            "version": version,
            "platform": sys.platform,
            "mode": "backend",
        },
        "caps": ["tool-events"],
        "auth": {"token": token},
        "role": "operator",
        "scopes": ["operator.read"],
    }
    return {
        "type": "req",
        "id": f"connect-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        "method": "connect",
        "params": params,
    }


def _gateway_session_agent(session_key: str | None) -> str | None:
    if not session_key:
        return None
    match = GATEWAY_AGENT_RE.match(session_key)
    if not match:
        return None
    return match.group(1).lower()


def _gateway_payload_summary(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    message = payload.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type") or "").strip().lower()
                if item_type == "thinking":
                    thinking = str(item.get("thinking") or "").strip()
                    if thinking:
                        parts.append(f"thinking: {thinking[:120]}")
                elif item_type == "toolcall":
                    tool_name = str(item.get("name") or item.get("tool") or "tool").strip()
                    tool_args = item.get("arguments")
                    if isinstance(tool_args, dict) and tool_args:
                        try:
                            parts.append(f"toolCall: {tool_name} {json.dumps(tool_args, ensure_ascii=False)[:120]}")
                        except Exception:
                            parts.append(f"toolCall: {tool_name}")
                    else:
                        parts.append(f"toolCall: {tool_name}")
                elif item_type == "text":
                    text = str(item.get("text") or "").strip()
                    if text:
                        parts.append(text[:120])
                if len(parts) >= 2:
                    break
            if parts:
                return " · ".join(parts)[:240]
    for key in ("text", "message", "content", "detail", "delta"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:240]
    try:
        compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return compact[:240]
    except Exception:
        return ""


def _gateway_event_kind(frame: dict[str, Any], payload: dict[str, Any] | None) -> str:
    event_name = str(frame.get("event") or "").strip().lower()
    if "thinking" in event_name:
        return "thinking"
    if "tool" in event_name:
        return "tool"
    if "message" in event_name or "reply" in event_name or "delta" in event_name:
        return "message"
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    item_type = str(item.get("type") or "").strip().lower()
                    if item_type == "thinking":
                        return "thinking"
                    if item_type in {"toolcall", "tool_call", "tooluse", "tool_use"}:
                        return "tool"
                    if item_type == "text":
                        return "message"
    return "event"


def _normalize_gateway_event(frame: dict[str, Any]) -> dict[str, Any] | None:
    if frame.get("type") != "event":
        return None
    payload = frame.get("payload") if isinstance(frame.get("payload"), dict) else {}
    session_key = payload.get("sessionKey") if isinstance(payload, dict) else None
    agent_id = _gateway_session_agent(session_key if isinstance(session_key, str) else None)
    if not agent_id:
        return None

    event_name = str(frame.get("event") or "").strip()
    normalized = {
        "type": "event",
        "event": event_name,
        "agent_id": agent_id,
        "session_key": session_key,
        "payload": payload,
        "kind": _gateway_event_kind(frame, payload),
        "seq": frame.get("seq"),
        "stateVersion": frame.get("stateVersion"),
        "received_at": utc_now(),
        "summary": _gateway_payload_summary(payload),
    }
    return normalized


def _gateway_fingerprint_payload(value: Any) -> Any:
    """Return a normalized payload used only for deduplication."""
    # Campos que cambian en cada evento pero no afectan el contenido sustancial
    _EXCLUDE_KEYS = {
        "timestamp", "ts", "received_at", "_meta", "date",
        "delta", "seq", "runId", "stateVersion", "state",
        "sessionKey", "kind", "event", "agent_id"
    }
    if isinstance(value, dict):
        return {
            key: _gateway_fingerprint_payload(item)
            for key, item in sorted(value.items())
            if key not in _EXCLUDE_KEYS
        }
    if isinstance(value, list):
        return [_gateway_fingerprint_payload(item) for item in value]
    return value


def _gateway_event_fingerprint(event: dict[str, Any]) -> str:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    fingerprint_source = {
        "agent_id": event.get("agent_id"),
        "session_key": event.get("session_key"),
        "event": event.get("event"),
        "kind": event.get("kind"),
        "payload": _gateway_fingerprint_payload(payload),
    }
    blob = json.dumps(fingerprint_source, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _gateway_event_group_key(event: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (
        event.get("agent_id"),
        event.get("session_key"),
        event.get("seq"),
    )


def _gateway_event_rank(event: dict[str, Any]) -> tuple[int, int, int, int]:
    event_name = str(event.get("event") or "").strip().lower()
    kind = str(event.get("kind") or "").strip().lower()
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    payload_state = ""
    if isinstance(payload, dict):
        payload_state = str(payload.get("state") or payload.get("status") or "").strip().lower()
    if event_name == "chat" or kind == "message":
        primary = 0
    elif event_name == "agent":
        primary = 1
    elif kind in {"thinking", "tool"}:
        primary = 2
    else:
        primary = 3
    has_summary = 0 if _gateway_payload_summary(payload) else 1
    has_text = 0 if payload_state or event.get("summary") else 1
    seq = event.get("seq")
    seq_rank = 0 if isinstance(seq, int) else 1
    return (primary, has_summary, has_text, seq_rank)


def _gateway_event_sort_key(event: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    received = event.get("received_at")
    seq = event.get("seq")
    return (
        received or "",
        seq if isinstance(seq, int) else -1,
        str(event.get("event") or ""),
        str(event.get("kind") or ""),
    )


def _gateway_consolidate_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, Any, Any], list[dict[str, Any]]] = {}
    for event in events:
        key = _gateway_event_group_key(event)
        grouped.setdefault(key, []).append(event)

    consolidated: list[dict[str, Any]] = []
    for items in grouped.values():
        if not items:
            continue
        items_sorted = sorted(items, key=lambda event: (_gateway_event_rank(event), _gateway_event_sort_key(event)))
        best = items_sorted[0]
        if len(items_sorted) > 1:
            merged = dict(best)
            merged["variants"] = [event for event in items_sorted if event is not best]
            merged["variant_count"] = len(items_sorted)
            best = merged
        consolidated.append(best)

    consolidated.sort(key=_gateway_event_sort_key)
    return consolidated


class _GatewayEventBroadcaster:
    """Maintain a live mirror of OpenClaw Gateway agent events."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._events: deque[dict[str, Any]] = deque(maxlen=GATEWAY_EVENT_LIMIT)
        self._recent_fingerprints: deque[str] = deque()
        self._recent_fingerprint_set: set[str] = set()
        self._status: dict[str, Any] = {
            "connected": False,
            "url": None,
            "last_error": None,
            "last_event_at": None,
        }

    def add(self, ws: WebSocket) -> None:
        self._clients.add(ws)

    def remove(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    def snapshot(self) -> dict[str, Any]:
        return {
            "status": dict(self._status),
            "events": list(self._events),
        }

    def _is_duplicate_event(self, event: dict[str, Any]) -> bool:
        fingerprint = _gateway_event_fingerprint(event)
        if fingerprint in self._recent_fingerprint_set:
            return True
        self._recent_fingerprints.append(fingerprint)
        self._recent_fingerprint_set.add(fingerprint)
        while len(self._recent_fingerprints) > GATEWAY_EVENT_LIMIT * 4:
            old = self._recent_fingerprints.popleft()
            self._recent_fingerprint_set.discard(old)
        return False

    async def _broadcast_status(self) -> None:
        payload = json.dumps(
            {"type": "status", "status": dict(self._status)},
            ensure_ascii=False,
        )
        dead: set[WebSocket] = set()
        for ws in list(self._clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    async def publish(self, event: dict[str, Any]) -> None:
        if self._is_duplicate_event(event):
            return
        self._events.append(event)
        self._status.update(
            connected=True,
            last_error=None,
            last_event_at=event.get("received_at") or utc_now(),
        )
        dead: set[WebSocket] = set()
        payload = json.dumps(event, ensure_ascii=False)
        for ws in list(self._clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    async def _authenticate(self, ws: websockets.WebSocketClientProtocol, token: str) -> None:
        connect_sent = False
        deadline = asyncio.get_running_loop().time() + 15

        while True:
            timeout = max(0.1, deadline - asyncio.get_running_loop().time())
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            frame = _parse_gateway_frame(raw)
            if not frame:
                continue
            frame_type = _gateway_frame_type(frame)
            if _gateway_is_hello_ok(frame):
                return
            if _gateway_is_challenge(frame):
                await ws.send(json.dumps(_gateway_connect_frame(token), ensure_ascii=False))
                connect_sent = True
                continue
            if frame_type == "event":
                # Some gateways may stream an event after auth; keep it and wait for ack.
                normalized = _normalize_gateway_event(frame)
                if normalized:
                    await self.publish(normalized)
                if not connect_sent:
                    await ws.send(json.dumps(_gateway_connect_frame(token), ensure_ascii=False))
                    connect_sent = True
                continue
            if frame_type == "res" and frame.get("ok") is False:
                raise RuntimeError(f"Gateway rechazó la conexión: {json.dumps(frame, ensure_ascii=False)[:240]}")
            if not connect_sent:
                await ws.send(json.dumps(_gateway_connect_frame(token), ensure_ascii=False))
                connect_sent = True
                continue
            if frame_type in {"error", "connect.error", "auth.error"}:
                raise RuntimeError(f"Gateway rechazó la conexión: {json.dumps(frame, ensure_ascii=False)[:240]}")

            if asyncio.get_running_loop().time() >= deadline:
                raise RuntimeError("Gateway handshake inválido: no llegó un connect.challenge válido")

    async def _listen_once(self) -> None:
        details = _gateway_connection_details()
        token = details["token"]
        if not token:
            raise RuntimeError("No se encontró token de Gateway en OPENCLAW_GATEWAY_TOKEN ni en ~/.openclaw/openclaw.json")

        self._status.update(url=details["url"], connected=False, last_error=None)
        await self._broadcast_status()
        async with websockets.connect(
            details["url"],
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
            open_timeout=15,
            max_size=2**22,
        ) as ws:
            await self._authenticate(ws, token)
            self._status.update(connected=True, last_error=None)
            await self._broadcast_status()
            while True:
                raw = await ws.recv()
                frame = _parse_gateway_frame(raw)
                if not frame or frame.get("type") != "event":
                    continue
                normalized = _normalize_gateway_event(frame)
                if normalized:
                    await self.publish(normalized)

    async def run(self) -> None:
        delay = 1.0
        while True:
            try:
                await self._listen_once()
                delay = 1.0
            except asyncio.CancelledError:
                self._status.update(connected=False)
                raise
            except ConnectionClosed as exc:
                self._status.update(connected=False, last_error=str(exc))
                await self._broadcast_status()
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30.0)
            except Exception as exc:
                self._status.update(connected=False, last_error=str(exc))
                await self._broadcast_status()
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30.0)


_gateway_events = _GatewayEventBroadcaster()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Validate configuration at startup (F0.7)
    load_config()
    
    asyncio.create_task(_broadcaster.run())
    asyncio.create_task(_gateway_events.run())
    yield


# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="Dev Squad Dashboard API", lifespan=lifespan)

# CORS with credentials support for cookie-based auth (F0.1 / F0.4)
# Default: restrict to localhost for development; production MUST set DASHBOARD_ALLOWED_ORIGINS
_allowed_origins = os.getenv("DASHBOARD_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
_cors_origins = [o.strip() for o in _allowed_origins if o.strip()]

# Security: wildcard is NOT allowed when credentials=True; require explicit origins
if "*" in _cors_origins:
    import warnings
    warnings.warn("DASHBOARD_ALLOWED_ORIGINS contains '*' which is insecure. Using localhost defaults.", RuntimeWarning)
    _cors_origins = ["http://localhost:3000", "http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Requested-With"],
    allow_credentials=True,  # Required for cookie-based SSE auth
    max_age=600,  # Cache preflight requests for 10 minutes
)

# Register API routers (F0.5 - Modularization)
# Routers already have /api prefix in their definitions
app.include_router(auth_router)  # Has /auth prefix
app.include_router(state_router)  # Has /api/* routes
app.include_router(projects_router)  # Has /api/project prefix
app.include_router(models_router)  # Has /api/models prefix
app.include_router(runtime_router)  # Has /api/runtime prefix
app.include_router(files_router)  # Has /api/files prefix
app.include_router(agents_router)  # Has /api/agents prefix
app.include_router(tasks_router)  # Has /api/tasks prefix
app.include_router(context_router)  # Has /api/context prefix
app.include_router(runs_router)  # Has /api/runs prefix
app.include_router(runtime_state_router)  # Has /api prefix


# ── Auth middleware (GAP-1 / P5) ──────────────────────────────────────────────

@app.middleware("http")
async def _auth_middleware(request: Request, call_next):
    path = request.url.path
    
    # Public endpoints - no auth required
    if path in _AUTH_EXEMPT:
        return await call_next(request)
    
    if _API_KEY:
        # Check header auth first
        if request.headers.get("X-API-Key") == _API_KEY:
            return await call_next(request)

        # Check cookie auth for all authenticated endpoints (F0.1)
        session_token = request.cookies.get("dashboard_session")
        if _validate_session(session_token):
            return await call_next(request)

        # Unauthorized
        return JSONResponse(
            {"error": "Unauthorized — provide a valid X-API-Key header or session cookie"},
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


def _stop_orchestrator(reason: str | None = None) -> dict[str, Any]:
    mem = load_memory()
    lock_payload: dict[str, Any] = {}
    if LOCK_FILE.exists():
        try:
            lock_payload = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
        except Exception:
            lock_payload = {}
    pid = lock_payload.get("pid") or mem.get("project", {}).get("orchestrator", {}).get("pid")
    alive = _pid_is_alive(pid)
    if alive:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception as exc:
            return {"ok": False, "error": f"No se pudo detener el orquestador: {exc}"}
    mem.setdefault("project", {})
    mem["project"].setdefault("orchestrator", {})
    mem["project"]["orchestrator"].update(
        {
            "status": "paused",
            "phase": "paused",
            "detail": reason or "Pausado desde el dashboard",
            "updated_at": utc_now(),
        }
    )
    mem["project"]["updated_at"] = utc_now()
    refresh_project_runtime_state(mem)
    save_memory(mem)
    return {"ok": True, "pid": pid, "alive": alive}
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
        "timestamp": utc_now(),
        "lockfile": lock_state,
        "orchestrator": orchestrator_state,
        "issues": issues,
        "memory_updated_at": mem.get("project", {}).get("updated_at"),
        "auth_enabled": bool(_API_KEY),
    }


def _runtime_process_snapshot() -> dict[str, Any]:
    """Return lock + process information for orchestrator runs."""
    mem = load_memory()
    orchestrator_state = mem.get("project", {}).get("orchestrator", {}) or {}
    lock_payload: dict[str, Any] = {}
    if LOCK_FILE.exists():
        try:
            lock_payload = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
        except Exception:
            lock_payload = {}

    lock_pid = lock_payload.get("pid")
    lock_alive = _pid_is_alive(lock_pid)
    processes: list[dict[str, Any]] = []
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid=,ppid=,etimes=,args="],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        result = None

    if result and result.stdout:
        repo_marker = str(BASE_DIR / "orchestrator.py")
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line or "orchestrator.py" not in line:
                continue
            try:
                pid_s, ppid_s, elapsed_s, args = line.split(None, 3)
                pid = int(pid_s)
                ppid = int(ppid_s)
                elapsed = int(float(elapsed_s))
            except Exception:
                continue
            if repo_marker not in args and "orchestrator.py" not in args:
                continue
            processes.append(
                {
                    "pid": pid,
                    "ppid": ppid,
                    "elapsed_sec": elapsed,
                    "cmdline": args,
                    "alive": _pid_is_alive(pid),
                }
            )

    processes.sort(key=lambda item: (item.get("elapsed_sec", 0), item.get("pid", 0)))
    primary_pid: int | None = None
    if lock_alive and isinstance(lock_pid, int):
        primary_pid = lock_pid
    else:
        mem_pid = orchestrator_state.get("pid")
        if _pid_is_alive(mem_pid):
            primary_pid = int(mem_pid)
        elif processes:
            primary_pid = int(processes[0]["pid"])

    for proc in processes:
        proc["role"] = "primary" if primary_pid and proc["pid"] == primary_pid else "duplicate"
        proc["is_lock_pid"] = bool(lock_pid and proc["pid"] == lock_pid)
        proc["is_mem_pid"] = bool(orchestrator_state.get("pid") and proc["pid"] == orchestrator_state.get("pid"))

    duplicates = [proc for proc in processes if primary_pid is None or proc["pid"] != primary_pid]
    issues: list[str] = []
    if lock_payload and not lock_alive:
        issues.append("lockfile obsoleto")
    mem_pid = orchestrator_state.get("pid")
    if mem_pid and not _pid_is_alive(mem_pid):
        issues.append("PID de memoria obsoleto")
    if len(processes) > 1:
        issues.append(f"{len(processes) - 1} ejecución(es) duplicada(s)")
    if orchestrator_state.get("status") == "error":
        issues.append("error del orquestador")

    return {
        "lockfile": {
            "exists": LOCK_FILE.exists(),
            "pid": lock_pid,
            "alive": lock_alive,
            "started_at": lock_payload.get("started_at"),
            "argv": lock_payload.get("argv"),
        },
        "project_orchestrator": {
            "pid": orchestrator_state.get("pid"),
            "status": orchestrator_state.get("status"),
            "phase": orchestrator_state.get("phase"),
            "detail": orchestrator_state.get("detail"),
            "updated_at": orchestrator_state.get("updated_at"),
        },
        "primary_pid": primary_pid,
        "processes": processes,
        "duplicates": duplicates,
        "issues": issues,
        "cleanup_available": bool(duplicates or (lock_payload and not lock_alive)),
    }


def _rewrite_lockfile_for_pid(pid: int, argv: list[str] | None = None) -> None:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text(
        json.dumps(
            {
                "pid": pid,
                "started_at": utc_now(),
                "argv": argv or [sys.executable, str(BASE_DIR / "orchestrator.py")],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


async def _cleanup_orchestrator_pids(pids: list[int], *, force: bool = True) -> dict[str, Any]:
    killed: list[int] = []
    skipped: list[int] = []
    errors: list[dict[str, Any]] = []
    for pid in pids:
        if not _pid_is_alive(pid):
            skipped.append(pid)
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except ProcessLookupError:
            skipped.append(pid)
        except PermissionError as exc:
            errors.append({"pid": pid, "error": f"permission denied: {exc}"})
        except Exception as exc:
            errors.append({"pid": pid, "error": str(exc)})
    if killed:
        await asyncio.sleep(0.7)
        still_alive = [pid for pid in killed if _pid_is_alive(pid)]
        if still_alive and force:
            for pid in still_alive:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    continue
                except Exception as exc:
                    errors.append({"pid": pid, "error": str(exc)})
            await asyncio.sleep(0.4)
    return {"killed": killed, "skipped": skipped, "errors": errors}


def _sync_orchestrator_pid(pid: int | None) -> None:
    mem = load_memory()
    mem.setdefault("project", {})
    mem["project"].setdefault("orchestrator", {})
    if pid:
        mem["project"]["orchestrator"]["pid"] = pid
    else:
        mem["project"]["orchestrator"].pop("pid", None)
    mem["project"]["orchestrator"]["updated_at"] = utc_now()
    refresh_project_runtime_state(mem)
    save_memory(mem)


@app.get("/api/runtime/orchestrators")
def get_runtime_orchestrators():
    """Return runtime orchestrator processes snapshot."""
    try:
        return {
            "timestamp": utc_now(),
            **_runtime_process_snapshot(),
        }
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": str(e)},
            status_code=500
        )


@app.post("/api/runtime/orchestrators/cleanup")
async def cleanup_runtime_orchestrators(payload: dict[str, Any] | None = None):
    mode = "duplicates"
    force = True
    if isinstance(payload, dict):
        mode = str(payload.get("mode") or mode).lower()
        force = bool(payload.get("force", True))

    snapshot = _runtime_process_snapshot()
    primary_pid = snapshot.get("primary_pid")
    processes = snapshot.get("processes", [])
    if mode == "all":
        target_pids = [int(proc["pid"]) for proc in processes if proc.get("pid")]
    else:
        target_pids = [int(proc["pid"]) for proc in snapshot.get("duplicates", []) if proc.get("pid")]

    result = await _cleanup_orchestrator_pids(target_pids, force=force)

    if mode == "all":
        if LOCK_FILE.exists():
            try:
                LOCK_FILE.unlink()
            except FileNotFoundError:
                pass
        mem = load_memory()
        mem.setdefault("project", {})
        mem["project"].setdefault("orchestrator", {})
        mem["project"]["orchestrator"].update(
            {
                "status": "paused",
                "phase": "paused",
                "detail": "Ejecuciones detenidas desde el dashboard",
                "updated_at": utc_now(),
            }
        )
        mem["project"]["updated_at"] = utc_now()
        refresh_project_runtime_state(mem)
        save_memory(mem)
    elif isinstance(primary_pid, int) and _pid_is_alive(primary_pid):
        _rewrite_lockfile_for_pid(primary_pid, argv=snapshot.get("lockfile", {}).get("argv") or None)
        _sync_orchestrator_pid(primary_pid)
    else:
        _sync_orchestrator_pid(None)
        if LOCK_FILE.exists() and not _pid_is_alive(snapshot.get("lockfile", {}).get("pid")):
            try:
                LOCK_FILE.unlink()
            except FileNotFoundError:
                pass
        mem = load_memory()
        mem.setdefault("project", {})
        mem["project"].setdefault("orchestrator", {})
        mem["project"]["orchestrator"].update(
            {
                "status": "paused",
                "phase": "paused",
                "detail": "Estado huérfano limpiado desde el dashboard",
                "updated_at": utc_now(),
            }
        )
        mem["project"]["updated_at"] = utc_now()
        refresh_project_runtime_state(mem)
        save_memory(mem)

    return {
        "ok": True,
        "mode": mode,
        "force": force,
        "terminated": result,
        "runtime": _runtime_process_snapshot(),
        "timestamp": utc_now(),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
@app.get("/api/health")
def health():
    """Health check endpoint for monitoring."""
    try:
        snapshot = build_health_snapshot()
        return JSONResponse(snapshot, status_code=200 if snapshot["ok"] else 503)
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": str(e)},
            status_code=503
        )


@app.get("/api/state")
def get_state():
    """Return current shared memory snapshot."""
    try:
        return load_memory()
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": f"Failed to load state: {str(e)}"},
            status_code=500
        )


@app.post("/api/project/restart")
async def restart_project():
    """Stops the orchestrator and allows it to be restarted."""
    res = _stop_orchestrator(reason="Reinicio forzado desde el agente OpenClaw.")
    return {"ok": True, "stopped_pid": res.get("pid"), "alive": res.get("alive")}


class TelegramAlert(BaseModel):
    message: str


@app.post("/api/alerts/telegram")
async def alert_telegram(payload: TelegramAlert):
    """Allows an agent to manually dispatch an alert via Telegram."""
    if not payload.message:
        return {"ok": False, "error": "Message is empty"}
    try:
        send_telegram_message(f"🚨 [OpenClaw Agent Alert]: {payload.message}")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/gateway/events")
def get_gateway_events(limit: int = 100):
    """Return consolidated gateway events with optional limit."""
    try:
        limit = max(1, min(int(limit or 100), GATEWAY_EVENT_LIMIT))
        snapshot = _gateway_events.snapshot()
        events = _gateway_consolidate_events(list(snapshot.get("events", [])))[-limit:]
        return {
            "status": snapshot.get("status", {}),
            "events": events,
            "limit": limit,
        }
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": str(e)},
            status_code=500
        )


@app.get("/api/stream")
async def stream_state(dashboard_session: str | None = Cookie(None)):
    """
    Server-Sent Events stream — pushes state every 2 s with keepalive.
    
    ## Authentication
    
    This endpoint supports two authentication methods:
    1. **Header**: `X-API-Key: <key>` (for non-browser clients)
    2. **Cookie**: Session cookie from `/api/auth/login` (for browsers)
    
    ## Reconnection
    
    The cookie automatically survives page reloads and reconnections,
    allowing seamless SSE reconnection after gateway restarts.
    """
    # Auth is handled by middleware, but double-check here for clarity
    if _API_KEY:
        # If we got here via middleware, the cookie is valid
        pass
    
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
    """
    WebSocket endpoint — receives push updates at ~1 s interval (GAP-9).
    
    ## Authentication
    
    Supports cookie-based auth from `/api/auth/login`.
    The browser automatically sends cookies with the WebSocket upgrade request.
    """
    # WebSocket auth: check cookie in handshake headers
    if _API_KEY:
        cookie_header = websocket.headers.get("cookie", "")
        session_token = None
        for cookie in cookie_header.split(";"):
            cookie = cookie.strip()
            if cookie.startswith("dashboard_session="):
                session_token = cookie.split("=", 1)[1]
                break
        
        if not _validate_session(session_token):
            await websocket.close(code=1008, reason="Unauthorized")
            return
    
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


@app.websocket("/ws/gateway-events")
async def ws_gateway_events(websocket: WebSocket):
    """
    WebSocket endpoint for live OpenClaw Gateway agent events.
    
    ## Authentication
    
    Supports cookie-based auth from `/api/auth/login`.
    The browser automatically sends cookies with the WebSocket upgrade request.
    """
    # WebSocket auth: check cookie in handshake headers
    if _API_KEY:
        cookie_header = websocket.headers.get("cookie", "")
        session_token = None
        for cookie in cookie_header.split(";"):
            cookie = cookie.strip()
            if cookie.startswith("dashboard_session="):
                session_token = cookie.split("=", 1)[1]
                break
        
        if not _validate_session(session_token):
            await websocket.close(code=1008, reason="Unauthorized")
            return
    
    await websocket.accept()
    _gateway_events.add(websocket)
    try:
        await websocket.send_text(json.dumps({
            "type": "snapshot",
            "snapshot": _gateway_events.snapshot(),
        }, ensure_ascii=False))
        while True:
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        _gateway_events.remove(websocket)


@app.get("/api/agents/world")
def agents_in_world():
    """Proxy Miniverse live observe snapshot."""
    try:
        r = requests.get(f"{MINIVERSE_URL}/api/observe", timeout=5)
        return r.json()
    except Exception as e:
        return {"error": str(e), "agents": [], "events": [], "lastEventId": None}


def _miniverse_repo_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "OpenClaw-Portal",
    }
    token = (
        os.getenv("OPENCLAW_GITHUB_TOKEN")
        or os.getenv("GITHUB_TOKEN")
        or os.getenv("GH_TOKEN")
        or ""
    ).strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _miniverse_ui_headers() -> dict[str, str]:
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "User-Agent": "OpenClaw-Portal",
    }


def _normalize_miniverse_repo(repo: dict[str, Any]) -> dict[str, Any]:
    license_info = repo.get("license") if isinstance(repo, dict) else None
    license_name = None
    if isinstance(license_info, dict):
        license_name = license_info.get("spdx_id") or license_info.get("name")

    return {
        "name": repo.get("name"),
        "full_name": repo.get("full_name"),
        "html_url": repo.get("html_url") or f"https://github.com/{MINIVERSE_GITHUB_OWNER}/{MINIVERSE_GITHUB_REPO}",
        "description": repo.get("description"),
        "homepage": repo.get("homepage"),
        "default_branch": repo.get("default_branch") or "main",
        "language": repo.get("language"),
        "license": license_name,
        "topics": repo.get("topics") if isinstance(repo.get("topics"), list) else [],
        "stargazers_count": repo.get("stargazers_count"),
        "forks_count": repo.get("forks_count"),
        "watchers_count": repo.get("watchers_count"),
        "open_issues_count": repo.get("open_issues_count"),
        "created_at": repo.get("created_at"),
        "updated_at": repo.get("updated_at"),
        "pushed_at": repo.get("pushed_at"),
    }


def _inspect_miniverse_ui() -> dict[str, Any]:
    preview: dict[str, Any] = {
        "url": MINIVERSE_UI_URL,
        "final_url": MINIVERSE_UI_URL,
        "status_code": None,
        "embeddable": False,
        "blocked_by": [],
        "checked_at": utc_now(),
    }
    response = None
    try:
        response = requests.head(
            MINIVERSE_UI_URL,
            headers=_miniverse_ui_headers(),
            timeout=MINIVERSE_REQUEST_TIMEOUT_SEC,
            allow_redirects=True,
        )
        if response.status_code in {405, 501}:
            response.close()
            response = requests.get(
                MINIVERSE_UI_URL,
                headers=_miniverse_ui_headers(),
                timeout=MINIVERSE_REQUEST_TIMEOUT_SEC,
                allow_redirects=True,
                stream=True,
            )

        x_frame_options = (response.headers.get("X-Frame-Options") or "").strip().lower()
        content_security_policy = response.headers.get("Content-Security-Policy") or ""
        blocked_by: list[str] = []

        if x_frame_options in {"deny", "sameorigin"}:
            blocked_by.append(f"x-frame-options:{x_frame_options}")

        frame_ancestors_match = re.search(r"frame-ancestors\s+([^;]+)", content_security_policy, re.IGNORECASE)
        if frame_ancestors_match:
            frame_ancestors = frame_ancestors_match.group(1).strip()
            if "*" not in frame_ancestors:
                blocked_by.append(f"frame-ancestors:{frame_ancestors}")

        preview.update(
            {
                "final_url": response.url or MINIVERSE_UI_URL,
                "status_code": response.status_code,
                "embeddable": not blocked_by,
                "blocked_by": blocked_by,
            }
        )
    except Exception as exc:
        preview["error"] = str(exc)
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
    return preview


def _fetch_miniverse_json(url: str, *, headers: dict[str, str] | None = None, timeout: float | None = None) -> dict[str, Any]:
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {"data": data}


def _default_miniverse_mock() -> dict[str, Any]:
    now = utc_now()
    return {
        "repo": {
            "html_url": f"https://github.com/{MINIVERSE_GITHUB_OWNER}/{MINIVERSE_GITHUB_REPO}",
            "name": MINIVERSE_GITHUB_REPO,
            "full_name": f"{MINIVERSE_GITHUB_OWNER}/{MINIVERSE_GITHUB_REPO}",
            "description": "A tiny pixel world for your agents.",
            "language": "TypeScript",
            "updated_at": now,
        },
            "world": {
                "base_url": "local-mock://miniverse",
                "api_url": "local-mock://miniverse/api",
                "ui_url": "local-mock://miniverse/ui",
            "gridCols": 12,
            "gridRows": 8,
            "floor": [
                ["grass", "grass", "grass", "grass", "path", "path", "path", "path", "grass", "grass", "grass", "grass"],
                ["grass", "grass", "grass", "path", "path", "path", "path", "path", "path", "grass", "grass", "grass"],
                ["grass", "grass", "path", "path", "path", "path", "path", "path", "path", "path", "grass", "grass"],
                ["grass", "grass", "path", "path", "path", "desk", "desk", "path", "path", "path", "grass", "grass"],
                ["grass", "path", "path", "path", "path", "desk", "desk", "path", "path", "path", "path", "grass"],
                ["grass", "path", "path", "path", "path", "path", "path", "path", "path", "path", "path", "grass"],
                ["grass", "grass", "path", "path", "path", "path", "path", "path", "path", "grass", "grass", "grass"],
                ["grass", "grass", "grass", "grass", "path", "path", "path", "path", "grass", "grass", "grass", "grass"],
            ],
            "propImages": {
                "wooden_desk_single": "world_assets/props/prop_0_wooden_desk_single.png",
                "ergonomic_chair": "world_assets/props/prop_1_ergonomic_chair.png",
                "tall_potted_plant": "world_assets/props/prop_2_tall_potted_plant.png",
                "coffee_machine": "world_assets/props/prop_3_coffee_machine.png",
                "whiteboard": "world_assets/props/prop_4_whiteboard.png",
            },
            "props": [
                {
                    "id": "wooden_desk_single",
                    "x": 5.0,
                    "y": 3.0,
                    "w": 2,
                    "h": 2,
                    "layer": "below",
                    "anchors": [
                        {"name": "desk_0_0", "ox": 0.5, "oy": 1.1, "type": "work"},
                        {"name": "desk_0_1", "ox": 1.4, "oy": 1.1, "type": "work"},
                    ],
                },
                {
                    "id": "ergonomic_chair",
                    "x": 5.2,
                    "y": 4.3,
                    "w": 1,
                    "h": 1,
                    "layer": "below",
                    "anchors": [
                        {"name": "chair_0_0", "ox": 0.5, "oy": 0.7, "type": "rest"},
                    ],
                },
                {
                    "id": "tall_potted_plant",
                    "x": 1.0,
                    "y": 1.0,
                    "w": 1,
                    "h": 1.5,
                    "layer": "above",
                    "anchors": [
                        {"name": "social_0_0", "ox": 0.5, "oy": 1.2, "type": "social"},
                    ],
                },
                {
                    "id": "coffee_machine",
                    "x": 9.0,
                    "y": 1.0,
                    "w": 1,
                    "h": 1.5,
                    "layer": "above",
                    "anchors": [
                        {"name": "coffee_0_0", "ox": 0.5, "oy": 1.0, "type": "social"},
                    ],
                },
                {
                    "id": "whiteboard",
                    "x": 8.2,
                    "y": 4.1,
                    "w": 1.4,
                    "h": 1.5,
                    "layer": "above",
                    "anchors": [
                        {"name": "board_0_0", "ox": 0.5, "oy": 1.0, "type": "utility"},
                    ],
                },
            ],
            "citizens": [
                {
                    "agentId": "main",
                    "name": "MAIN",
                    "sprite": "rio",
                    "position": "desk_0_1",
                    "type": "agent",
                },
                {
                    "agentId": "pixel",
                    "name": "PIXEL",
                    "sprite": "nova",
                    "position": "desk_0_0",
                    "type": "agent",
                },
                {
                    "agentId": "byte",
                    "name": "BYTE",
                    "sprite": "dexter",
                    "position": "board_0_0",
                    "type": "agent",
                },
                {
                    "agentId": "arch",
                    "name": "ARCH",
                    "sprite": "rio",
                    "position": "coffee_0_0",
                    "type": "agent",
                },
            ],
            "wanderPoints": [
                {"x": 1, "y": 1},
                {"x": 10, "y": 2},
                {"x": 9, "y": 6},
                {"x": 3, "y": 6},
            ],
            "info": {
                "world": "Miniverse local mock",
                "version": "mock",
                "grid": {"cols": 12, "rows": 8},
                "agents": {"online": 4, "total": 4},
                "theme": "cozy-startup",
            },
            "agents": [
                {
                    "agent": "main",
                    "state": "idle",
                    "role": "Observer",
                    "task": "Observing the squad runtime",
                    "last_seen": now,
                    "x": 6,
                    "y": 4,
                },
                {
                    "agent": "pixel",
                    "state": "working",
                    "role": "UI",
                    "task": "Observing and rendering the world",
                    "last_seen": now,
                    "x": 4,
                    "y": 3,
                },
                {
                    "agent": "byte",
                    "state": "working",
                    "role": "Code",
                    "task": "Implementing task flow",
                    "last_seen": now,
                    "x": 7,
                    "y": 5,
                },
                {
                    "agent": "arch",
                    "state": "thinking",
                    "role": "Coordinator",
                    "task": "Planning and reviewing",
                    "last_seen": now,
                    "x": 2,
                    "y": 1,
                },
            ],
            "events": [
                {
                    "id": "mock-1",
                    "type": "thinking",
                    "agent": "arch",
                    "message": "Plan de prueba cargado en el mock local.",
                    "timestamp": now,
                },
                {
                    "id": "mock-2",
                    "type": "tool",
                    "agent": "pixel",
                    "message": "Render local disponible mientras el mundo real responde.",
                    "timestamp": now,
                },
                {
                    "id": "mock-3",
                    "type": "message",
                    "agent": "main",
                    "message": "MAIN observa el mundo compartido.",
                    "timestamp": now,
                },
            ],
            "observe": {},
            "lastEventId": "mock-2",
        },
        "links": {
            "repo": f"https://github.com/{MINIVERSE_GITHUB_OWNER}/{MINIVERSE_GITHUB_REPO}",
            "api": "local-mock://miniverse/api",
            "world": "local-mock://miniverse/ui",
            "ui": "local-mock://miniverse/ui",
            "docs": "https://minivrs.com/docs/",
        },
        "ui": {
            "url": "local-mock://miniverse/ui",
            "final_url": "local-mock://miniverse/ui",
            "embeddable": True,
            "blocked_by": [],
            "checked_at": now,
            "status_code": 200,
        },
        "meta": {
            "source": "local-mock",
            "cached": False,
            "error": None,
        },
    }


def _merge_miniverse_mock(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = deepcopy(base)
        for key, value in override.items():
            if key in merged:
                merged[key] = _merge_miniverse_mock(merged[key], value)
            else:
                merged[key] = deepcopy(value)
        return merged
    if override is None:
        return deepcopy(base)
    return deepcopy(override)


def _load_miniverse_mock() -> dict[str, Any]:
    default_mock = _default_miniverse_mock()
    if MINIVERSE_MOCK_FILE.exists():
        try:
            data = json.loads(MINIVERSE_MOCK_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return _merge_miniverse_mock(default_mock, data)
        except Exception:
            pass
    mock = default_mock
    MINIVERSE_MOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    MINIVERSE_MOCK_FILE.write_text(json.dumps(mock, ensure_ascii=False, indent=2), encoding="utf-8")
    return mock


def _load_miniverse_snapshot(force_refresh: bool = False) -> dict[str, Any]:
    now = time.monotonic()
    cached_payload = _MINIVERSE_CACHE.get("payload")
    if (
        not force_refresh
        and cached_payload
        and _MINIVERSE_CACHE.get("signature") == (MINIVERSE_GITHUB_API_URL, MINIVERSE_URL, MINIVERSE_UI_URL)
        and now < float(_MINIVERSE_CACHE.get("expires_at", 0.0))
    ):
        return deepcopy(cached_payload)

    payload: dict[str, Any] = {
        "repo": {
            "html_url": f"https://github.com/{MINIVERSE_GITHUB_OWNER}/{MINIVERSE_GITHUB_REPO}",
            "name": MINIVERSE_GITHUB_REPO,
            "full_name": f"{MINIVERSE_GITHUB_OWNER}/{MINIVERSE_GITHUB_REPO}",
        },
        "world": {
            "base_url": MINIVERSE_URL,
            "api_url": MINIVERSE_URL,
            "ui_url": MINIVERSE_UI_URL,
            "info": {},
            "agents": {},
            "events": [],
            "observe": {},
        },
        "links": {
            "repo": f"https://github.com/{MINIVERSE_GITHUB_OWNER}/{MINIVERSE_GITHUB_REPO}",
            "api": MINIVERSE_URL,
            "world": MINIVERSE_UI_URL,
            "ui": MINIVERSE_UI_URL,
            "docs": "https://minivrs.com/docs/",
        },
        "ui": {
            "url": MINIVERSE_UI_URL,
            "final_url": MINIVERSE_UI_URL,
            "embeddable": False,
            "blocked_by": [],
            "checked_at": utc_now(),
        },
        "meta": {
            "source": "observe+github+ui",
            "cached": False,
            "error": None,
        },
    }

    error_messages: list[str] = []

    fetch_timeout = min(MINIVERSE_REQUEST_TIMEOUT_SEC, 4.0)
    overall_deadline = time.monotonic() + max(MINIVERSE_REQUEST_TIMEOUT_SEC + 1.0, 7.0)
    futures: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures["repo"] = executor.submit(
            _fetch_miniverse_json,
            MINIVERSE_GITHUB_API_URL,
            headers=_miniverse_repo_headers(),
            timeout=fetch_timeout,
        )
        futures["observe"] = executor.submit(
            _fetch_miniverse_json,
            f"{MINIVERSE_URL}/api/observe",
            timeout=fetch_timeout,
        )
        futures["world_info"] = executor.submit(
            _fetch_miniverse_json,
            f"{MINIVERSE_URL}/api/info",
            timeout=fetch_timeout,
        )
        futures["agents"] = executor.submit(
            _fetch_miniverse_json,
            f"{MINIVERSE_URL}/api/agents",
            timeout=fetch_timeout,
        )
        futures["ui"] = executor.submit(_inspect_miniverse_ui)

        wait_timeout = max(overall_deadline - time.monotonic(), 0.1)
        done, pending = wait(list(futures.values()), timeout=wait_timeout)

        for name in ("repo", "observe", "world_info", "agents", "ui"):
            future = futures[name]
            if future in pending:
                future.cancel()
                error_messages.append(f"{name}: timeout")
                continue
            try:
                result = future.result()
            except Exception as exc:
                error_messages.append(f"{name}: {exc}")
                continue

            if name == "repo":
                repo_data = result if isinstance(result, dict) else {}
                if repo_data:
                    payload["repo"].update(_normalize_miniverse_repo(repo_data))
            elif name == "observe":
                observe_data = result if isinstance(result, dict) else {}
                if observe_data:
                    payload["world"]["observe"] = observe_data
                    info_payload = observe_data.get("info")
                    if not isinstance(info_payload, dict):
                        info_candidate = observe_data.get("world")
                        info_payload = info_candidate if isinstance(info_candidate, dict) else {}
                    if info_payload:
                        payload["world"]["info"] = info_payload

                    agents_payload = observe_data.get("agents")
                    if agents_payload is None and isinstance(info_payload, dict):
                        agents_payload = info_payload.get("agents")
                    if agents_payload is not None:
                        payload["world"]["agents"] = agents_payload

                    events_payload = observe_data.get("events")
                    if events_payload is None and isinstance(info_payload, dict):
                        events_payload = info_payload.get("events")
                    if events_payload is not None:
                        payload["world"]["events"] = events_payload

                    last_event_id = observe_data.get("lastEventId")
                    if last_event_id is None:
                        last_event_id = observe_data.get("last_event_id")
                    if last_event_id is not None:
                        payload["world"]["lastEventId"] = last_event_id

                    for maybe_url in (
                        info_payload.get("ui_url") if isinstance(info_payload, dict) else None,
                        info_payload.get("url") if isinstance(info_payload, dict) else None,
                        observe_data.get("ui_url"),
                        observe_data.get("world_url"),
                        observe_data.get("base_url"),
                    ):
                        if isinstance(maybe_url, str) and maybe_url.strip():
                            normalized_url = maybe_url.strip()
                            payload["world"]["ui_url"] = normalized_url
                            payload["links"]["world"] = normalized_url
                            payload["links"]["ui"] = normalized_url
                            payload["ui"]["url"] = normalized_url
                            payload["ui"]["final_url"] = normalized_url
                            break
            elif name == "world_info":
                if not payload["world"]["info"]:
                    world_json = result if isinstance(result, dict) else {}
                    if world_json:
                        payload["world"]["info"] = world_json
            elif name == "agents":
                if not payload["world"]["agents"]:
                    agents_json = result if isinstance(result, dict) else {}
                    payload["world"]["agents"] = agents_json if isinstance(agents_json, dict) else {"agents": agents_json}
            elif name == "ui":
                if isinstance(result, dict):
                    payload["ui"].update(result)
                    payload["links"]["ui"] = payload["ui"].get("final_url") or MINIVERSE_UI_URL
                    payload["links"]["world"] = payload["links"]["ui"]
                    payload["world"]["ui_url"] = payload["links"]["ui"]

    payload["meta"]["error"] = "; ".join(error_messages) if error_messages else None
    payload["meta"]["cached"] = False

    # ── Partial-failure: fill gaps with mock data instead of replacing everything ──
    if error_messages:
        mock = deepcopy(_load_miniverse_mock())
        # Only fill in parts that are empty/missing in the live payload
        if not payload["world"].get("info"):
            payload["world"]["info"] = mock.get("world", {}).get("info", {})
        if not payload["world"].get("agents"):
            payload["world"]["agents"] = mock.get("world", {}).get("agents", [])
        if not payload["world"].get("events"):
            payload["world"]["events"] = mock.get("world", {}).get("events", [])
        if not payload["world"].get("floor"):
            payload["world"]["floor"] = mock.get("world", {}).get("floor", [])
        if not payload["world"].get("citizens"):
            payload["world"]["citizens"] = mock.get("world", {}).get("citizens", [])
        if not payload["world"].get("props"):
            payload["world"]["props"] = mock.get("world", {}).get("props", [])
        # Keep track that we had partial failures
        payload["meta"]["partial_fallback"] = True
        payload["meta"]["fallback_parts"] = [msg.split(":")[0] for msg in error_messages]
        # Do NOT set meta.fallback = "local-mock" — that tells the frontend to go full mock
        # Only set it if ALL critical sources failed
        critical_failures = [m for m in error_messages if any(k in m for k in ("observe", "agents", "world_info"))]
        if len(critical_failures) >= 3:
            payload["meta"]["fallback"] = "local-mock"
            payload["meta"]["stale"] = True

    _MINIVERSE_CACHE.update(
        {
            "signature": (MINIVERSE_GITHUB_API_URL, MINIVERSE_URL, MINIVERSE_UI_URL),
            "expires_at": now + MINIVERSE_CACHE_TTL_SEC,
            "payload": deepcopy(payload),
        }
    )
    return payload


@app.get("/api/miniverse")
def get_miniverse_snapshot(force: bool = False):
    """Return repo metadata and the live Miniverse world snapshot."""
    return _load_miniverse_snapshot(force_refresh=force)


# ── Models config (GAP-5 / P6) ────────────────────────────────────────────────

@app.get("/api/models")
def get_models():
    """Return current model assignments and the normalized model catalog."""
    return _load_models_config()


@app.get("/api/models/available")
def get_available():
    """Return the normalized flat list of all available models."""
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


# ── Model Health (Tarea 2.1) ───────────────────────────────────────────────────

@app.post("/api/models/test")
def test_model(payload: dict[str, Any]):
    """Test model availability by checking config and attempting a minimal API call."""
    model = payload.get("model") if isinstance(payload, dict) else None
    if not model:
        return JSONResponse({"error": "Model is required"}, status_code=400)

    import time
    start = time.time()

    # First check if model is in available list
    models_data = get_available_models()
    available_models = [m.get("qualified") for m in models_data]
    
    if model not in available_models:
        elapsed_ms = int((time.time() - start) * 1000)
        return {"ok": False, "model": model, "status": "not_in_catalog", "elapsed_ms": elapsed_ms, 
                "message": f"Model not in available catalog. {len(available_models)} models available."}

    # Get provider info
    provider = model.split("/")[0] if "/" in model else "unknown"
    
    # Try to make a minimal request using httpx to the provider
    try:
        import httpx
        
        # Get provider config
        cfg = load_openclaw_config()
        providers = cfg.get("models", {}).get("providers", {})
        provider_cfg = providers.get(provider, {})
        api_key = _resolve_provider_secret(cfg, provider)
        base_url = (
            provider_cfg.get("baseURL")
            or provider_cfg.get("baseUrl")
            or provider_cfg.get("base_url")
            or ""
        )
        
        if not api_key:
            elapsed_ms = int((time.time() - start) * 1000)
            return {"ok": False, "model": model, "status": "no_api_key", "elapsed_ms": elapsed_ms,
                    "message": f"No API key configured for provider {provider}"}
        
        # Determine endpoint based on provider
        if base_url:
            url = f"{base_url.rstrip('/')}/chat/completions"
        elif provider == "groq":
            url = "https://api.groq.com/openai/v1/chat/completions"
        elif provider == "openai":
            url = "https://api.openai.com/v1/chat/completions"
        elif provider == "deepseek":
            url = "https://api.deepseek.com/v1/chat/completions"
        elif provider == "mistral" or provider == "mistralai":
            url = "https://api.mistral.ai/v1/chat/completions"
        elif provider == "nvidia":
            url = "https://integrate.api.nvidia.com/v1/chat/completions"
        elif provider == "fireworks":
            url = "https://api.fireworks.ai/inference/v1/chat/completions"
        else:
            url = f"https://api.{provider}.com/v1/chat/completions"
        
        # Make minimal test request
        model_name = model.split("/", 1)[1] if "/" in model else model
        request_body = {
            "model": model_name,
            "messages": [{"role": "user", "content": "Say ok"}],
            "max_tokens": 3,
        }

        def _resolve_host_via_doh(hostname: str) -> str | None:
            """Resolve a host via Cloudflare DoH when local DNS is failing."""
            host = hostname.strip()
            if not host:
                return None

            current = host
            seen: set[str] = set()
            for _ in range(3):
                if current in seen:
                    return None
                seen.add(current)

                doh_url = f"https://1.1.1.1/dns-query?name={current}&type=A"
                proc = subprocess.run(
                    [
                        "curl",
                        "-sS",
                        "--max-time",
                        "10",
                        "-k",
                        doh_url,
                        "-H",
                        "accept: application/dns-json",
                    ],
                    capture_output=True,
                    text=True,
                )
                if proc.returncode != 0 or not proc.stdout:
                    return None

                try:
                    payload = json.loads(proc.stdout)
                except Exception:
                    return None

                answers = payload.get("Answer", [])
                if isinstance(answers, list):
                    for answer in answers:
                        if not isinstance(answer, dict):
                            continue
                        if answer.get("type") == 1 and answer.get("data"):
                            return str(answer["data"]).strip()
                    cname = next(
                        (
                            str(answer.get("data")).strip().rstrip(".")
                            for answer in answers
                            if isinstance(answer, dict) and answer.get("type") == 5 and answer.get("data")
                        ),
                        None,
                    )
                    if cname:
                        current = cname
                        continue

                return None

            return None

        def _run_curl_test(resolved_ip: str | None = None) -> tuple[int, str]:
            """Fallback to curl when Python DNS/proxy resolution fails."""
            parsed_url = urlparse(url)
            host = parsed_url.hostname or ""
            curl_args = [
                "curl",
                "-sS",
                "--max-time",
                "30",
                "--retry",
                "10",
                "--retry-all-errors",
                "--retry-delay",
                "2",
                "--retry-max-time",
                "25",
            ]
            if resolved_ip and host:
                curl_args.extend(["--resolve", f"{host}:443:{resolved_ip}"])
            curl_args.extend([
                "-X",
                "POST",
                url,
                "-H",
                f"Authorization: Bearer {api_key}",
                "-H",
                "Content-Type: application/json",
                "-d",
                json.dumps(request_body),
                "-w",
                "\n%{http_code}",
            ])
            proc = subprocess.run(curl_args, capture_output=True, text=True)
            stdout = proc.stdout or ""
            stderr = (proc.stderr or "").strip()
            if proc.returncode != 0 and not stdout:
                raise RuntimeError(stderr or f"curl exited with code {proc.returncode}")

            if "\n" in stdout:
                body, status_text = stdout.rsplit("\n", 1)
            else:
                body, status_text = stdout, ""

            try:
                status_code = int(status_text.strip())
            except Exception:
                status_code = proc.returncode if proc.returncode else 0
                body = stdout

            if status_code == 0 and stderr:
                raise RuntimeError(stderr)

            return status_code, body

        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=request_body,
            )

        response_status = r.status_code
        response_text = r.text

    except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
        try:
            response_status, response_text = _run_curl_test()
        except Exception as curl_error:
            resolved_ip = _resolve_host_via_doh(urlparse(url).hostname or "")
            if resolved_ip:
                try:
                    response_status, response_text = _run_curl_test(resolved_ip=resolved_ip)
                except Exception as curl_ip_error:
                    elapsed_ms = int((time.time() - start) * 1000)
                    return {
                        "ok": False,
                        "model": model,
                        "status": "error",
                        "elapsed_ms": elapsed_ms,
                        "error": f"{e}; curl fallback failed: {curl_error}; DoH {resolved_ip} failed: {curl_ip_error}",
                        "message": str(curl_ip_error),
                    }
            else:
                elapsed_ms = int((time.time() - start) * 1000)
                return {
                    "ok": False,
                    "model": model,
                    "status": "error",
                    "elapsed_ms": elapsed_ms,
                    "error": f"{e}; curl fallback failed: {curl_error}",
                    "message": str(curl_error),
                }

    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return {"ok": False, "model": model, "status": "error", "elapsed_ms": elapsed_ms,
                "error": str(e), "message": str(e)}

    elapsed_ms = int((time.time() - start) * 1000)

    if response_status == 200:
        return {"ok": True, "model": model, "status": "available", "elapsed_ms": elapsed_ms,
                "message": "Model is available and responding"}

    # Parse error
    try:
        err = json.loads(response_text).get("error", {})
        err_msg = err.get("message", response_text[:100])
    except Exception:
        err_msg = response_text[:100] if response_text else f"HTTP {response_status}"

    err_lower = err_msg.lower()

    if response_status == 402 or "insufficient" in err_lower or "balance" in err_lower:
        return {"ok": False, "model": model, "status": "insufficient_balance",
                "elapsed_ms": elapsed_ms, "message": "Insufficient account balance"}
    if response_status == 429 or "rate limit" in err_lower or "too many requests" in err_lower or "quota exceeded" in err_lower:
        return {"ok": False, "model": model, "status": "rate_limit",
                "elapsed_ms": elapsed_ms, "message": "Rate limit reached"}
    if response_status == 404 or "not found" in err_lower:
        return {"ok": False, "model": model, "status": "not_found",
                "elapsed_ms": elapsed_ms, "message": "Model not found"}
    if response_status == 401 or "unauthorized" in err_lower or "invalid" in err_lower:
        return {"ok": False, "model": model, "status": "auth_error",
                "elapsed_ms": elapsed_ms, "message": "Authentication error"}

    return {"ok": False, "model": model, "status": "error", "elapsed_ms": elapsed_ms,
            "error": err_msg, "message": err_msg}
    

def get_models_health():
    """
    Return health status of all configured models.
    
    Shows which models are available, which have failed recently,
    and recommendations for switching.
    """
    try:
        from model_fallback import get_models_health_report
        report = get_models_health_report()
        return report
    except ImportError:
        # Fallback si model_fallback no está disponible
        models_data = get_available_models()
        return {
            "models": {
                "available": [m.get("qualified") for m in models_data],
                "status": "unknown",
                "note": "model_fallback module not loaded"
            }
        }


@app.get("/api/health/summary")
def get_health_summary():
    """
    Return a comprehensive health summary of the system.
    
    Includes:
    - Model status
    - Gateway status
    - Orchestrator status
    - Project status
    """
    from shared_state import load_memory, _pid_is_alive
    
    mem = load_memory()
    
    # Gateway health
    gateway_ok = False
    gateway_error = None
    try:
        resp = requests.get("http://127.0.0.1:18789/", timeout=2)
        gateway_ok = resp.status_code == 200
    except Exception as e:
        gateway_error = str(e)
    
    # Orchestrator health
    orchestrator = mem.get("project", {}).get("orchestrator", {})
    orchestrator_pid = orchestrator.get("pid")
    orchestrator_alive = _pid_is_alive(orchestrator_pid)
    
    # Model health
    model_health = {"status": "unknown"}
    try:
        from model_fallback import get_models_health_report
        model_health = get_models_health_report()
    except:
        pass
    
    # Project health
    project = mem.get("project", {})
    tasks = mem.get("tasks", [])
    task_counts = {
        "total": len(tasks),
        "done": sum(1 for t in tasks if t.get("status") == "done"),
        "pending": sum(1 for t in tasks if t.get("status") == "pending"),
        "in_progress": sum(1 for t in tasks if t.get("status") == "in_progress"),
        "error": sum(1 for t in tasks if t.get("status") == "error"),
    }
    
    return {
        "status": "healthy" if gateway_ok and orchestrator_alive else "degraded",
        "gateway": {
            "status": "ok" if gateway_ok else "error",
            "error": gateway_error,
        },
        "orchestrator": {
            "status": orchestrator.get("status", "idle"),
            "pid": orchestrator_pid,
            "alive": orchestrator_alive,
            "phase": orchestrator.get("phase"),
        },
        "project": {
            "id": project.get("id"),
            "name": project.get("name"),
            "status": project.get("status"),
            "task_counts": task_counts,
        },
        "models": model_health,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Project launch ────────────────────────────────────────────────────────────

class ProjectRequest(BaseModel):
    brief: str
    repo_url: str | None = None
    repo_name: str | None = None
    branch: str | None = None
    agent_models: dict[str, str] | None = None
    allow_init_repo: bool = False
    dry_run: bool = False
    task_timeout_sec: int = 1800
    phase_timeout_sec: int = 7200
    retry_attempts: int = 3
    retry_delay_sec: float = 2.0
    max_parallel_byte: int = 1   # GAP-8
    max_parallel_pixel: int = 1  # GAP-8
    webhook_url: str | None = None  # P9


class ProjectResumeRequest(BaseModel):
    task_id: str | None = None
    resume_all_failed: bool = True
    dry_run: bool = False
    task_timeout_sec: int = 1800
    phase_timeout_sec: int = 7200
    retry_attempts: int = 3
    retry_delay_sec: float = 2.0
    max_parallel_byte: int = 1
    max_parallel_pixel: int = 1
    webhook_url: str | None = None


class ProjectPauseRequest(BaseModel):
    task_id: str | None = None
    pause_running: bool = True
    reason: str | None = None


class ProjectRetryPlanningResponse(BaseModel):
    status: str
    message: str
    project_id: str
    timestamp: str


class ProjectClarificationReplyRequest(BaseModel):
    reply: str = Field(..., min_length=1, max_length=2000)
    auto_resume: bool = Field(default=True)
    source: str = Field(default="dashboard")


class ProjectClarificationReplyResponse(BaseModel):
    ok: bool
    project_id: str
    auto_resumed: bool
    message: str
    timestamp: str


class ProjectExtendRequest(BaseModel):
    brief: str = Field(..., min_length=1, max_length=4000)
    project_id: str | None = None
    auto_resume: bool = Field(default=True)
    source: str = Field(default="dashboard")


class ProjectExtendResponse(BaseModel):
    ok: bool
    project_id: str
    task_id: str
    task_title: str
    agent: str
    project_status: str
    auto_resumed: bool
    message: str
    timestamp: str


_EXTENSION_FRONTEND_MARKERS = (
    "frontend",
    "ui",
    "interfaz",
    "diseño",
    "design",
    "css",
    "html",
    "react",
    "vue",
    "angular",
    "next",
    "component",
    "vista",
    "pantalla",
    "selector",
)

_EXTENSION_BACKEND_MARKERS = (
    "backend",
    "api",
    "endpoint",
    "router",
    "route",
    "coordinador",
    "coordinator",
    "planner",
    "planificador",
    "orquestador",
    "workflow",
    "database",
    "base de datos",
    "servicio",
    "service",
    "node",
    "express",
    "laravel",
    "php",
)


def _infer_extension_agent(project: dict[str, Any], brief: str) -> str:
    text = " ".join(
        [
            str(project.get("name") or ""),
            str(project.get("description") or ""),
            brief,
        ]
    ).lower()
    if any(marker in text for marker in _EXTENSION_BACKEND_MARKERS):
        return "byte"
    if any(marker in text for marker in _EXTENSION_FRONTEND_MARKERS):
        return "pixel"

    structure = infer_project_structure(
        project,
        {
            "title": brief,
            "description": brief,
            "agent": "byte",
        },
    )
    if str(structure.get("kind") or "").lower() in {"framework-frontend", "vanilla-static"}:
        return "pixel"
    return "byte"


def _build_extension_acceptance(project: dict[str, Any], brief: str, agent: str) -> list[str]:
    text = brief.lower()
    acceptance = [
        "La extensión se agrega al proyecto existente sin crear un proyecto nuevo.",
        "La nueva tarea queda registrada en la memoria activa del mismo project_id.",
        "La funcionalidad solicitada se valida con una verificación reproducible.",
    ]
    if any(marker in text for marker in ("preview", "deploy", "publicar", "desplegar")):
        acceptance.append("Si el brief lo solicita, la extensión actualiza o publica el preview correspondiente.")
    if agent == "pixel":
        acceptance.append("La interfaz o experiencia visual mantiene coherencia con el proyecto actual.")
    else:
        acceptance.append("La modificación respeta la base técnica ya existente del proyecto.")
    if str(project.get("status") or "").lower() == "delivered":
        acceptance.append("El proyecto entregado se reabre en la misma memoria para continuar sobre él.")
    return acceptance


def _spawn_orchestrator(args: list[str]) -> None:
    log_path = BASE_DIR / "logs" / "orchestrator.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        subprocess.Popen(
            args,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=BASE_DIR,
        )


@app.post("/api/project/start")
async def start_project(req: ProjectRequest):
    """Spawn orchestrator in background.
    
    Validates that there's no active project with similar description.
    """
    # Check for duplicate active projects
    mem = load_memory()
    active_project = mem.get("project", {})
    projects = mem.get("projects", [])
    
    # Check if there's already an active project running
    if active_project and active_project.get("status") in ("starting", "running", "pending", "in_progress"):
        return JSONResponse({
            "error": f"Ya existe un proyecto activo: {active_project.get('name', 'Sin nombre')}",
            "active_project_id": active_project.get("id"),
            "active_project_status": active_project.get("status"),
        }, status_code=409)
    
    # Check for similar projects (same brief or description)
    normalized_brief = req.brief.strip().lower()[:100]
    for p in projects:
        if p.get("status") in ("completed", "failed"):
            continue
        desc = (p.get("description") or "").lower()
        if normalized_brief in desc or desc[:100] in normalized_brief:
            return JSONResponse({
                "error": f"Ya existe un proyecto similar activo: {p.get('name', 'Sin nombre')}",
                "similar_project_id": p.get("id"),
                "similar_project_status": p.get("status"),
            }, status_code=409)
    
    # GAP-2 — validate brief before spawning subprocess
    try:
        safe_brief = _validate_brief(req.brief)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    if req.agent_models:
        try:
            for agent_id, model in req.agent_models.items():
                if agent_id not in {"arch", "byte", "pixel"}:
                    continue
                if not model:
                    continue
                sdk_set_agent_model(agent_id, model)
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

    mem.setdefault("project", {})
    mem["project"].update(
        {
            "name": req.repo_name or safe_brief[:60] or "Project",
            "description": safe_brief,
            "repo_url": req.repo_url,
            "repo_name": req.repo_name,
            "branch": req.branch,
            "allow_init_repo": req.allow_init_repo,
            "created_at": utc_now(),
            "status": "starting",
            "updated_at": utc_now(),
        }
    )
    mem["blockers"] = []
    mem["project"].pop("pending_clarification", None)
    mem["project"].setdefault("orchestrator", {})
    mem["project"]["orchestrator"].update(
        {
            "status": "starting",
            "phase": "planning",
            "detail": "Proyecto iniciado desde el dashboard",
            "updated_at": utc_now(),
        }
    )
    refresh_project_runtime_state(mem)
    save_memory(mem)

    _spawn_orchestrator(args)
    return {
        "status": "started",
        "message": "Orquestador iniciado correctamente",
        "brief": safe_brief,
        "ts": utc_now(),
    }


@app.post("/api/project/retry-planning", response_model=ProjectRetryPlanningResponse)
async def retry_planning():
    """Retry planning for the current project without creating a new run record."""
    mem = load_memory()
    project = mem.get("project", {}) or {}
    project_id = str(project.get("id") or "").strip()
    orchestrator = project.get("orchestrator", {}) or {}
    project_status = str(project.get("status") or "").lower()
    orchestrator_status = str(orchestrator.get("status") or "").lower()
    orchestrator_phase = str(orchestrator.get("phase") or "").lower()

    retryable_planning_failure = orchestrator_phase == "planning" and orchestrator_status == "error"

    if not retryable_planning_failure:
        return JSONResponse(
            {
                "error": "Solo se puede reintentar la planificación cuando el proyecto está en error de planificación",
                "project_status": project_status or "idle",
                "orchestrator_status": orchestrator_status or None,
                "orchestrator_phase": orchestrator_phase or None,
            },
            status_code=422,
        )

    pending = project.get("pending_clarification")
    if isinstance(pending, dict) and not pending.get("resolved"):
        return JSONResponse(
            {
                "error": "Hay una aclaración pendiente; responde primero ese bloque antes de reintentar",
                "project_id": project_id,
            },
            status_code=422,
        )

    orchestrator_pid = orchestrator.get("pid")
    if _pid_is_alive(orchestrator_pid):
        return JSONResponse(
            {
                "error": "El orquestador todavía está en ejecución; no se puede reintentar ahora",
                "pid": orchestrator_pid,
            },
            status_code=409,
        )

    if not project_id:
        project_id = ensure_project_id(project)
        project["id"] = project_id
    mem["active_project_id"] = project_id

    project["status"] = "starting"
    project["updated_at"] = utc_now()
    project.pop("pending_clarification", None)
    project["orchestrator"] = {
        "status": "starting",
        "phase": "planning",
        "detail": "Reintentando planificación desde el dashboard",
        "pid": None,
        "started_at": utc_now(),
        "updated_at": utc_now(),
        "dry_run": False,
    }
    mem["tasks"] = []
    mem["plan"] = {"phases": [], "current_phase": None}
    mem["blockers"] = []
    mem["proposals"] = []
    mem["milestones"] = []
    mem["files_produced"] = []
    mem["progress_files"] = []
    update_project_history(mem)
    refresh_project_runtime_state(mem)
    save_memory(mem)

    args = [sys.executable, str(BASE_DIR / "orchestrator.py")]
    if project.get("repo_url"):
        args.extend(["--repo-url", str(project.get("repo_url"))])
    if project.get("repo_name"):
        args.extend(["--repo-name", str(project.get("repo_name"))])
    if project.get("branch"):
        args.extend(["--branch", str(project.get("branch"))])
    if project.get("allow_init_repo"):
        args.append("--allow-init-repo")
    args.append(project.get("description") or project.get("name") or "Retry planning project")

    _spawn_orchestrator(args)
    return {
        "status": "replanning",
        "message": "Replanificación iniciada correctamente",
        "project_id": project_id,
        "timestamp": utc_now(),
    }


@app.post("/api/project/resume")
async def resume_project(req: ProjectResumeRequest):
    """Resume failed or pending tasks for the current project."""
    mem = load_memory()
    project = mem.get("project", {}) or {}
    tasks = mem.get("tasks", []) if isinstance(mem.get("tasks", []), list) else []
    closed_statuses = {"done", "passed", "delivered"}

    if not project.get("id"):
        return JSONResponse({"error": "No hay proyecto activo para reanudar"}, status_code=422)

    task_ids: list[str] = []
    resumed: list[str] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id") or "")
        if not task_id:
            continue
        should_resume = False
        if req.task_id:
            should_resume = task_id == req.task_id
        elif req.resume_all_failed:
            should_resume = task.get("status") in {"error", "pending", "paused", "in_progress"}

        if should_resume:
            current_status = str(task.get("status") or "")
            is_healthy_pending = (
                current_status == "pending"
                and not task.get("error")
                and not task.get("failure_kind")
                and int(task.get("failure_count") or 0) == 0
            )
            task["status"] = "pending"
            task.pop("error", None)
            task.pop("failure_kind", None)
            task.pop("retryable", None)
            task.pop("next_action", None)
            task.pop("raw_response", None)
            task.pop("blocked_note", None)
            if is_healthy_pending:
                task.pop("not_before", None)
                task.pop("resume_cooldown_sec", None)
            else:
                cooldown_sec = _resume_cooldown_seconds(task)
                _set_task_resume_cooldown(task, cooldown_sec)
                task["resume_cooldown_sec"] = cooldown_sec
            resumed.append(task_id)
        task_ids.append(task_id)

    if req.task_id and not resumed:
        return JSONResponse({"error": f"No se encontró la tarea {req.task_id} para reanudar"}, status_code=404)

    review_only_resume = (
        not resumed
        and bool(tasks)
        and all(isinstance(task, dict) and task.get("status") in closed_statuses for task in tasks)
        and project.get("status") != "delivered"
    )

    if not resumed:
        if not review_only_resume:
            return JSONResponse({"error": "No hay tareas pendientes o fallidas para reanudar"}, status_code=422)

    mem.setdefault("project", {})
    mem["project"]["status"] = "in_progress"
    mem["project"]["updated_at"] = utc_now()
    mem["project"].setdefault("orchestrator", {})
    detail = (
        "Reanudando revisión final"
        if review_only_resume
        else f"Reanudando {len(resumed)} tarea(s)"
    )
    mem["project"]["orchestrator"].update(
        {
            "status": "starting",
            "phase": "execution",
            "detail": detail,
            "task_id": resumed[0] if len(resumed) == 1 else None,
            "updated_at": utc_now(),
        }
    )
    refresh_project_runtime_state(mem)
    save_memory(mem)

    args = [sys.executable, str(BASE_DIR / "orchestrator.py"), "--resume"]
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
    args.append(project.get("description") or project.get("name") or "Resume project")

    _spawn_orchestrator(args)
    return {
        "status": "resumed",
        "message": "Reanudación iniciada correctamente",
        "resumed_tasks": resumed,
        "review_only": review_only_resume,
        "task_ids": task_ids,
        "ts": utc_now(),
    }


@app.post("/api/project/clarification/reply", response_model=ProjectClarificationReplyResponse)
async def reply_project_clarification(req: ProjectClarificationReplyRequest):
    """Store a clarification reply and optionally restart planning immediately."""
    mem = load_memory()
    project = mem.get("project", {}) or {}
    project_id = str(project.get("id") or "").strip()
    pending = project.get("pending_clarification")
    reply = req.reply.strip()

    if not project_id:
        return JSONResponse({"error": "No hay proyecto activo"}, status_code=422)

    pending_project_id = str(pending.get("project_id") or "").strip() if isinstance(pending, dict) else ""
    clarification_blockers = [
        blocker
        for blocker in get_project_blockers(mem)
        if isinstance(blocker, dict) and isinstance(blocker.get("questions"), list) and blocker.get("questions")
    ]
    active_blocker = clarification_blockers[-1] if clarification_blockers else None

    if not isinstance(pending, dict) or pending.get("resolved") or (pending_project_id and pending_project_id != project_id):
        if not active_blocker:
            return JSONResponse({"error": "No hay una aclaración pendiente para responder"}, status_code=404)
        pending = {
            "questions": list(active_blocker.get("questions") or []),
            "original_brief": str(active_blocker.get("reply_hint") or project.get("description") or project.get("name") or "").strip(),
            "sent_at": str(active_blocker.get("ts") or utc_now()),
            "reply": None,
            "resolved": False,
            "project_id": project_id,
            "project_created_at": project.get("created_at"),
        }
        project["pending_clarification"] = pending

    if not reply:
        return JSONResponse({"error": "La aclaración no puede estar vacía"}, status_code=422)

    if active_blocker and isinstance(mem.get("blockers"), list):
        active_blocker["resolved"] = True
        active_blocker["reply"] = reply
        active_blocker["reply_source"] = req.source or "dashboard"
        active_blocker["reply_received_at"] = utc_now()
        active_blocker["questions"] = []

    pending["reply"] = reply
    pending["reply_source"] = req.source or "dashboard"
    pending["reply_received_at"] = utc_now()
    pending["resolved"] = True

    project.setdefault("orchestrator", {})
    project["updated_at"] = utc_now()
    if req.auto_resume:
        project["status"] = "in_progress"
        project["orchestrator"].update(
            {
                "status": "starting",
                "phase": "planning",
                "detail": "Aclaración recibida; reanudando planificación",
                "updated_at": utc_now(),
            }
        )
    else:
        project["status"] = "blocked"
        project["orchestrator"].update(
            {
                "status": "blocked",
                "phase": "planning",
                "detail": "Aclaración registrada; pendiente de reanudación",
                "updated_at": utc_now(),
            }
        )
    mem.setdefault("log", []).append(
        {
            "ts": utc_now(),
            "level": "info",
            "agent": "dashboard",
            "msg": f"Aclaración recibida desde {req.source}: {reply[:120]}{'...' if len(reply) > 120 else ''}",
            "meta": {"auto_resume": req.auto_resume, "source": req.source},
        }
    )
    mem["log"].append(
        {
            "ts": utc_now(),
            "level": "info",
            "agent": "dashboard",
            "msg": "Acuse de recibo: se recibió la aclaración y ARCH retomará la planificación.",
            "meta": {"auto_resume": req.auto_resume, "source": req.source},
        }
    )
    mem["log"] = mem["log"][-500:]
    refresh_project_runtime_state(mem)
    save_memory(mem)

    try:
        send_telegram_message(
            format_telegram_blocker_message(
                "Aclaración recibida",
                source="DevSquad",
                status="blocked" if not req.auto_resume else "running",
                detail=reply,
                reply_hint="ARCH reanudará la planificación con esta respuesta.",
                next_action="Se está reanudando la planificación si el proyecto lo permite.",
            )
        )
    except Exception as exc:
        mem = load_memory()
        mem.setdefault("log", []).append(
            {
                "ts": utc_now(),
                "level": "warning",
                "agent": "dashboard",
                "msg": f"No se pudo notificar la aclaración por Telegram: {exc}",
            }
        )
        mem["log"] = mem["log"][-500:]
        save_memory(mem)

    if req.auto_resume:
        args = [sys.executable, str(BASE_DIR / "orchestrator.py")]
        if project.get("repo_url"):
            args.extend(["--repo-url", str(project.get("repo_url"))])
        if project.get("repo_name"):
            args.extend(["--repo-name", str(project.get("repo_name"))])
        if project.get("branch"):
            args.extend(["--branch", str(project.get("branch"))])
        if project.get("allow_init_repo"):
            args.append("--allow-init-repo")
        args.append(project.get("description") or project.get("name") or "Resume project")
        _spawn_orchestrator(args)

    return ProjectClarificationReplyResponse(
        ok=True,
        project_id=project_id,
        auto_resumed=bool(req.auto_resume),
        message="Aclaración registrada" + (" y planificación reanudada" if req.auto_resume else ""),
        timestamp=utc_now(),
    )


@app.post("/api/project/load")
async def load_project(payload: dict[str, Any] | None = None):
    project_id = payload.get("project_id") if isinstance(payload, dict) else None
    if not project_id:
        return JSONResponse({"error": "Se requiere project_id"}, status_code=400)

    mem = load_memory()
    current_proj = mem.get("project", {})
    if current_proj.get("id") == project_id:
        return {
            "status": "already_active",
            "message": "El proyecto ya está activo",
            "ts": utc_now(),
        }

    # Buscar el proyecto en el archivo
    archive = mem.get("projects", [])
    project_to_load = next((p for p in archive if p.get("id") == project_id), None)
    if not project_to_load:
        return JSONResponse({"error": "Proyecto no encontrado en el archivo"}, status_code=404)

    # Si hay un proyecto activo actualmente, lo archivamos
    if current_proj.get("id"):
        # Lo actualizamos en archive si ya existe, o lo agregamos
        existing = next((p for p in archive if p.get("id") == current_proj["id"]), None)
        if existing:
            existing.update(current_proj)
            existing["status"] = current_proj.get("status") or existing.get("status") or "paused"
        else:
            current_proj["status"] = current_proj.get("status") or "paused"
            archive.append(current_proj)

    # Detener cualquier ejecución actual
    _stop_orchestrator(reason="Cargando otro proyecto")

    # Restaurar el proyecto seleccionado a mem["project"]
    # Nota: Sólo recuperamos sus metadatos básicos, tasks y logs no se archivan completos en "projects",
    # pero al menos reanudamos sobre la ruta del repo donde OpenClaw reparará su estado
    defaults = deepcopy(DEFAULT_MEMORY)
    artifacts = _load_project_artifacts(project_to_load)
    artifact_project = artifacts.get("project") if isinstance(artifacts.get("project"), dict) else {}

    mem["project"] = project_to_load
    mem["active_project_id"] = project_to_load.get("id")
    mem["blockers"] = []
    if artifact_project:
        for key, value in artifact_project.items():
            if key != "id" and value is not None:
                mem["project"][key] = value
    mem["project"]["status"] = "in_progress"
    mem["project"]["updated_at"] = utc_now()
    mem["project"].setdefault("created_at", utc_now())
    
    # Rehidratar tasks y archivos desde el snapshot del proyecto
    mem["tasks"] = artifacts.get("tasks", []) if isinstance(artifacts.get("tasks"), list) else []
    mem["plan"] = defaults["plan"]
    mem["log"] = []
    mem["blockers"] = []
    mem["project"].pop("pending_clarification", None)
    mem["files_produced"] = artifacts.get("files", []) if isinstance(artifacts.get("files"), list) else []
    mem["progress_files"] = []
    mem["project"]["task_count_snapshot"] = artifacts.get("task_count", 0)
    mem["project"]["task_ids_snapshot"] = [
        str(task.get("id") or "").strip()
        for task in mem["tasks"]
        if isinstance(task, dict) and str(task.get("id") or "").strip()
    ]
    mem["project"]["artifact_manifest"] = artifacts.get("manifest_path")
    mem["project"]["artifact_index"] = artifacts.get("index_path")
    mem["project"]["artifact_evidence"] = artifacts.get("evidence_path")
    mem["project"]["artifact_task_count"] = artifacts.get("task_count", 0)
    mem["project"]["artifact_file_count"] = artifacts.get("file_count", 0)
    if artifacts.get("generated_at"):
        mem["project"]["artifacts_updated_at"] = artifacts.get("generated_at")
    if artifacts.get("summary"):
        mem["project"]["artifact_summary"] = artifacts.get("summary")
    
    mem["project"].setdefault("orchestrator", {})
    mem["project"]["orchestrator"].update({
        "status": "starting",
        "phase": "execution",
        "detail": "Proyecto cargado desde historial",
        "updated_at": utc_now()
    })
    
    refresh_project_runtime_state(mem)
    save_memory(mem)

    # Reanudar
    args = [sys.executable, str(BASE_DIR / "orchestrator.py"), "--resume"]
    args.append(project_to_load.get("description") or project_to_load.get("name") or "Resume project")
    _spawn_orchestrator(args)

    return {"status": "loaded", "message": "Proyecto cargado y reanudado", "ts": utc_now()}


@app.post("/api/project/extend", response_model=ProjectExtendResponse)
async def extend_project(req: ProjectExtendRequest):
    """Enqueue a follow-up task on the current project without creating a new project."""
    brief = req.brief.strip()
    if not brief:
        return JSONResponse({"error": "La descripción de la extensión no puede estar vacía"}, status_code=422)

    mem = load_memory()
    project = mem.get("project", {}) if isinstance(mem.get("project"), dict) else {}
    project_id = str(project.get("id") or "").strip()
    requested_project_id = str(req.project_id or "").strip()
    if not project_id:
        return JSONResponse({"error": "No hay un proyecto activo para extender"}, status_code=422)
    if requested_project_id and requested_project_id != project_id:
        return JSONResponse(
            {
                "error": "La extensión debe aplicarse al proyecto activo actual. Carga primero el proyecto correcto para reutilizarlo sin crear uno nuevo.",
                "active_project_id": project_id,
                "requested_project_id": requested_project_id,
            },
            status_code=409,
        )

    project_status = str(project.get("status") or "").lower()
    if project_status == "blocked":
        pending = project.get("pending_clarification")
        if isinstance(pending, dict) and not pending.get("resolved"):
            return JSONResponse(
                {
                    "error": "El proyecto tiene una aclaración pendiente; responde primero ese bloqueo antes de extenderlo",
                    "project_id": project_id,
                },
                status_code=422,
            )

    agent = _infer_extension_agent(project, brief)
    title_prefix = "Extensión"
    project_name = str(project.get("name") or "proyecto").strip()
    task_title = f"{title_prefix} de {project_name}: {brief[:72].strip()}".strip()
    if len(task_title) > 120:
        task_title = task_title[:117].rstrip() + "..."

    acceptance = _build_extension_acceptance(project, brief, agent)
    execution_dir = str(project.get("repo_path") or project.get("output_dir") or "").strip() or None
    proposal = propose_follow_up_task(
        title=task_title,
        description=brief,
        rationale=f"Extensión solicitada desde {req.source or 'dashboard'} para el proyecto actual.",
        agent=agent,
        kind="extension",
        execution_dir=execution_dir,
        acceptance=acceptance,
    )
    task = approve_proposal(str(proposal.get("id") or ""))
    if not task:
        return JSONResponse({"error": "No se pudo encolar la extensión"}, status_code=500)

    mem = load_memory()
    project = mem.get("project", {}) if isinstance(mem.get("project"), dict) else {}
    project.setdefault("extensions", [])
    project["extensions"].append(
        {
            "task_id": task.get("id"),
            "title": task.get("title"),
            "brief": brief,
            "agent": agent,
            "created_at": utc_now(),
            "source": req.source or "dashboard",
            "auto_resume": bool(req.auto_resume),
        }
    )
    project["extensions"] = project["extensions"][-20:]
    project["status"] = "in_progress"
    project["updated_at"] = utc_now()
    project.setdefault("orchestrator", {})

    orchestrator_pid = project["orchestrator"].get("pid")
    orchestrator_alive = _pid_is_alive(orchestrator_pid)
    auto_resumed = False
    if orchestrator_alive:
        project["orchestrator"].update(
            {
                "status": "starting",
                "phase": "execution",
                "detail": "Extensión agregada al proyecto existente",
                "updated_at": utc_now(),
            }
        )
    elif req.auto_resume:
        project["orchestrator"].update(
            {
                "status": "starting",
                "phase": "execution",
                "detail": "Extensión agregada; reanudando ejecución del proyecto existente",
                "updated_at": utc_now(),
            }
        )
        args = [sys.executable, str(BASE_DIR / "orchestrator.py"), "--resume"]
        if project.get("repo_url"):
            args.extend(["--repo-url", str(project.get("repo_url"))])
        if project.get("repo_name"):
            args.extend(["--repo-name", str(project.get("repo_name"))])
        if project.get("branch"):
            args.extend(["--branch", str(project.get("branch"))])
        if project.get("allow_init_repo"):
            args.append("--allow-init-repo")
        args.append(project.get("description") or project.get("name") or "Resume project")
        _spawn_orchestrator(args)
        auto_resumed = True
    else:
        project["orchestrator"].update(
            {
                "status": "paused",
                "phase": "execution",
                "detail": "Extensión agregada; reanudación manual pendiente",
                "updated_at": utc_now(),
            }
        )

    mem.setdefault("milestones", [])
    mem["milestones"].append(f"Extensión encolada: {task.get('id')}")
    mem.setdefault("log", []).append(
        {
            "ts": utc_now(),
            "level": "info",
            "agent": "dashboard",
            "msg": f"Extensión encolada para {project_id}: {task_title}",
            "meta": {
                "project_id": project_id,
                "task_id": task.get("id"),
                "auto_resume": bool(req.auto_resume),
                "source": req.source or "dashboard",
            },
        }
    )
    mem["log"] = mem["log"][-500:]
    refresh_project_runtime_state(mem)
    save_memory(mem)

    return ProjectExtendResponse(
        ok=True,
        project_id=project_id,
        task_id=str(task.get("id") or ""),
        task_title=str(task.get("title") or task_title),
        agent=agent,
        project_status=str(project.get("status") or "in_progress"),
        auto_resumed=auto_resumed,
        message=(
            "Extensión encolada y proyecto reanudado"
            if auto_resumed
            else "Extensión encolada en el proyecto actual"
        ),
        timestamp=utc_now(),
    )


@app.post("/api/project/pause")
async def pause_project(payload: dict[str, Any] | None = None):
    reason = None
    task_id = None
    pause_running = True
    if isinstance(payload, dict):
        reason = payload.get("reason")
        task_id = payload.get("task_id")
        pause_running = bool(payload.get("pause_running", True))

    mem = load_memory()
    tasks = mem.get("tasks", []) if isinstance(mem.get("tasks", []), list) else []
    paused_ids: list[str] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        current_status = str(task.get("status") or "").lower()
        if current_status != "in_progress":
            continue
        if task_id and str(task.get("id") or "") != task_id and pause_running:
            continue
        task["status"] = "paused"
        task["paused_at"] = utc_now()
        task["pause_reason"] = reason or "Pausado desde el dashboard"
        paused_ids.append(str(task.get("id") or ""))
        if task_id:
            break

    if paused_ids:
        mem.setdefault("project", {})
        mem["project"]["status"] = "paused"
        mem["project"].setdefault("orchestrator", {})
        mem["project"]["orchestrator"].update(
            {
                "status": "paused",
                "phase": "paused",
                "detail": reason or f"Pausadas {len(paused_ids)} tarea(s)",
                "updated_at": utc_now(),
            }
        )
        refresh_project_runtime_state(mem)
        save_memory(mem)

    result = _stop_orchestrator(reason=reason)
    status = 200 if result.get("ok") else 500
    if paused_ids:
        result["paused_tasks"] = paused_ids
    return JSONResponse(result, status_code=status)


@app.post("/api/project/delete")
async def delete_project(payload: dict[str, Any] | None = None):
    reason = None
    target_project_id = None
    if isinstance(payload, dict):
        reason = payload.get("reason")
        target_project_id = payload.get("project_id")

    mem = load_memory()
    current_project_id = mem.get("project", {}).get("id")
    
    is_active = not target_project_id or target_project_id == current_project_id

    if is_active:
        stop_result = _stop_orchestrator(reason=reason or "Eliminado desde el dashboard")
        project_id = current_project_id
        project_name = mem.get("project", {}).get("name")
        project_repo_path = mem.get("project", {}).get("repo_path") or mem.get("project", {}).get("output_dir")
    else:
        stop_result = {"ok": False}
        project_to_delete = next((p for p in mem.get("projects", []) if p.get("id") == target_project_id), None)
        if not project_to_delete:
            return JSONResponse({"error": "Project not found"}, status_code=404)
        project_id = target_project_id
        project_name = project_to_delete.get("name")
        project_repo_path = project_to_delete.get("repo_path") or project_to_delete.get("output_dir")

    raw_project_key = str(project_id or project_name or "project").strip().lower()
    project_key = re.sub(r"[^a-z0-9]+", "-", raw_project_key).strip("-") or "project"

    def _safe_remove(path_value: str | None) -> bool:
        if not path_value:
            return False
        path = Path(path_value).expanduser()
        if not path.exists():
            return False
        resolved = path.resolve()
        allowed_roots = [
            (BASE_DIR / "projects").resolve(),
            (BASE_DIR / "workspaces").resolve(),
            (BASE_DIR / "output").resolve(),
        ]
        if not any(str(resolved).startswith(str(root) + os.sep) or resolved == root for root in allowed_roots):
            return False
        try:
            if resolved.is_file():
                resolved.unlink()
            else:
                shutil.rmtree(resolved)
        except Exception:
            return False
        return True

    removed_paths: list[str] = []
    candidates = [
        project_repo_path,
        str(BASE_DIR / "workspaces" / "designer" / project_key),
        str(BASE_DIR / "workspaces" / "programmer" / project_key),
        str(BASE_DIR / "workspaces" / "coordinator" / project_key),
    ]
    for candidate in candidates:
        if candidate and _safe_remove(candidate):
            removed_paths.append(candidate)

    if project_id:
        mem.setdefault("projects", [])
        for existing in mem["projects"]:
            if existing.get("id") == project_id:
                existing["status"] = "deleted"
                existing["updated_at"] = utc_now()
                existing["deleted_at"] = utc_now()
                existing["removed_paths"] = removed_paths
                break

    if is_active:
        defaults = deepcopy(DEFAULT_MEMORY)
        mem["project"] = defaults["project"]
        mem["plan"] = defaults["plan"]
        mem["tasks"] = []
        mem["log"] = []
        mem["blockers"] = []
        mem["files_produced"] = []
        mem["progress_files"] = []
        mem["messages"] = []
        mem["milestones"] = []
        mem["project"]["updated_at"] = utc_now()
        refresh_project_runtime_state(mem)
        save_memory(mem)
        
        result = {"ok": True, "stopped": stop_result.get("ok", False), "removed_paths": removed_paths}
    else:
        save_memory(mem)
        result = {"ok": True, "stopped": False, "removed_paths": removed_paths}
        
    return JSONResponse(result, status_code=200)


from coordination import (
    fetch_telegram_updates,
    get_telegram_credentials,
    slugify, # Needed for ID generation if not using SHA
)

@app.on_event("startup")
async def startup_event():
    """Start background tasks on API startup."""
    asyncio.create_task(background_telegram_polling())

async def background_telegram_polling():
    """Centralized polling loop for the whole project lifecycle."""
    while True:
        try:
            token, chat_id = get_telegram_credentials()
            if not token:
                await asyncio.sleep(60)
                continue

            mem = load_memory()
            offset = mem.setdefault("_telegram_offset", None)
            
            # Fetch updates
            result = fetch_telegram_updates(offset=offset, timeout=15, token=token)
            if not result.get("ok"):
                await asyncio.sleep(30)
                continue

            updates = result.get("updates", [])
            last_id = offset
            
            new_msgs = []
            for up in updates:
                last_id = max(last_id or 0, up.get("update_id", 0)) + 1
                msg = up.get("message") or up.get("edited_message")
                if not msg or not msg.get("text"):
                    continue
                
                # Filter by chat_id if known
                if chat_id and str(msg.get("chat", {}).get("id")) != str(chat_id):
                    continue

                text = msg.get("text").strip()
                # Basic command handling could go here or in orchestrator
                new_msgs.append({
                    "id": f"tg-{up['update_id']}",
                    "source": "telegram",
                    "sender": msg.get("from", {}).get("username") or "user",
                    "text": text,
                    "timestamp": utc_now(),
                    "raw": up
                })

            if new_msgs:
                # Deduplicate and append
                existing_ids = {m.get("id") for m in mem.get("messages", [])}
                for nm in new_msgs:
                    if nm["id"] not in existing_ids:
                        mem.setdefault("messages", []).append(nm)

                project = mem.get("project", {}) or {}
                pending = project.get("pending_clarification")
                if (
                    isinstance(pending, dict)
                    and not pending.get("resolved")
                    and not pending.get("reply")
                    and (not pending.get("project_id") or str(pending.get("project_id")) == str(project.get("id") or ""))
                ):
                    first_reply = next(
                        (
                            nm.get("text")
                            for nm in new_msgs
                            if isinstance(nm, dict) and isinstance(nm.get("text"), str) and nm.get("text", "").strip() and not nm.get("text", "").strip().startswith("/")
                        ),
                        None,
                    )
                    if first_reply:
                        reply_text = str(first_reply).strip()
                        pending["reply"] = reply_text
                        pending["reply_source"] = "telegram"
                        pending["reply_received_at"] = utc_now()
                        pending["resolved"] = True
                        project["status"] = "in_progress"
                        project["updated_at"] = utc_now()
                        project.setdefault("orchestrator", {})
                        project["orchestrator"].update(
                            {
                                "status": "starting",
                                "phase": "planning",
                                "detail": "Aclaración recibida por Telegram; reanudando planificación",
                                "updated_at": utc_now(),
                            }
                        )
                        mem.setdefault("log", []).append(
                            {
                                "ts": utc_now(),
                                "level": "info",
                                "agent": "telegram",
                                "msg": f"Aclaración recibida por Telegram: {reply_text[:120]}{'...' if len(reply_text) > 120 else ''}",
                                "meta": {"source": "telegram", "auto_resume": True},
                            }
                        )
                        mem["log"].append(
                            {
                                "ts": utc_now(),
                                "level": "info",
                                "agent": "telegram",
                                "msg": "Acuse de recibo: se recibió la aclaración y ARCH retomará la planificación.",
                                "meta": {"source": "telegram", "auto_resume": True},
                            }
                        )
                        mem["log"] = mem["log"][-500:]
                        refresh_project_runtime_state(mem)
                        save_memory(mem)

                        try:
                            send_telegram_message(
                                format_telegram_blocker_message(
                                    "Aclaración recibida",
                                    source="Telegram",
                                    status="running",
                                    detail=reply_text,
                                    reply_hint="Se recibió tu respuesta y ARCH retomará la planificación.",
                                    next_action="Reanudando planificación ahora.",
                                )
                            )
                        except Exception as exc:
                            mem = load_memory()
                            mem.setdefault("log", []).append(
                                {
                                    "ts": utc_now(),
                                    "level": "warning",
                                    "agent": "telegram",
                                    "msg": f"No se pudo enviar el acuse de recibo por Telegram: {exc}",
                                }
                            )
                            mem["log"] = mem["log"][-500:]
                            save_memory(mem)

                        args = [sys.executable, str(BASE_DIR / "orchestrator.py")]
                        if project.get("repo_url"):
                            args.extend(["--repo-url", str(project.get("repo_url"))])
                        if project.get("repo_name"):
                            args.extend(["--repo-name", str(project.get("repo_name"))])
                        if project.get("branch"):
                            args.extend(["--branch", str(project.get("branch"))])
                        if project.get("allow_init_repo"):
                            args.append("--allow-init-repo")
                        args.append(project.get("description") or project.get("name") or "Resume project")
                        _spawn_orchestrator(args)

                # Limit memory
                if len(mem["messages"]) > 200:
                    mem["messages"] = mem["messages"][-200:]
                
                mem["_telegram_offset"] = last_id
                save_memory(mem)
                
                # Notify UI via SSE/WS
                # (Existing WebSocket connections will see the change in next broadcast)
                # broadcast_state_change(mem)  # TODO: implement

        except Exception as e:
            print(f"[Polling Error] {e}")
            await asyncio.sleep(10)
        
        await asyncio.sleep(10) # Base interval between poll batches

@app.get("/api/logs")
def get_logs():
    """Return recent log entries from memory and structured log file."""
    try:
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


def _resolve_output_dir(project: dict[str, Any]) -> Path:
    output_dir = str(project.get("output_dir") or "output").strip()
    candidate = Path(output_dir).expanduser()
    if candidate.is_absolute():
        return candidate
    return (BASE_DIR / candidate).resolve()


def _load_project_artifacts(project: dict[str, Any]) -> dict[str, Any]:
    """Load task and file snapshots from a project's generated artifacts."""
    output_dir = _resolve_output_dir(project)
    manifest_path = output_dir / "PROJECT_MANIFEST.json"
    evidence_path = output_dir / "evidence.json"
    index_path = output_dir / "PROJECT_INDEX.md"

    manifest: dict[str, Any] = {}
    evidence: dict[str, Any] = {}

    if manifest_path.exists():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                manifest = loaded
        except Exception:
            manifest = {}

    if evidence_path.exists():
        try:
            loaded = json.loads(evidence_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                evidence = loaded
        except Exception:
            evidence = {}

    project_snapshot: dict[str, Any] = {}
    if isinstance(manifest.get("project"), dict):
        project_snapshot = manifest["project"]
    elif isinstance(evidence.get("project"), dict):
        project_snapshot = evidence["project"]

    task_entries: list[dict[str, Any]] = []
    if isinstance(manifest.get("tasks"), list) and manifest.get("tasks"):
        task_entries = manifest["tasks"]
    elif isinstance(evidence.get("tasks"), list) and evidence.get("tasks"):
        task_entries = evidence["tasks"]

    file_entries: list[Any] = []
    if isinstance(manifest.get("files"), list) and manifest.get("files"):
        file_entries = manifest["files"]
    elif isinstance(evidence.get("files"), list) and evidence.get("files"):
        file_entries = evidence["files"]

    summary = evidence.get("summary") if isinstance(evidence.get("summary"), dict) else None

    project_id = str(project.get("id") or project_snapshot.get("id") or "").strip() or None
    artifact_tasks: list[dict[str, Any]] = []
    for entry in task_entries:
        if not isinstance(entry, dict):
            continue
        task_id = str(entry.get("id") or "").strip()
        if not task_id:
            continue

        failure_count = entry.get("failure_count") or 0
        if isinstance(failure_count, str):
            try:
                failure_count = int(failure_count)
            except ValueError:
                failure_count = 0

        task: dict[str, Any] = {
            "id": task_id,
            "title": str(entry.get("title") or task_id).strip() or task_id,
            "status": str(entry.get("status") or "pending").strip().lower() or "pending",
            "agent": str(entry.get("agent") or "arch").strip() or "arch",
            "project_id": project_id,
            "failure_count": failure_count,
        }
        if entry.get("retryable") is not None:
            task["retryable"] = entry.get("retryable")
        if isinstance(entry.get("skills"), list) and entry.get("skills"):
            task["skills"] = [str(skill).strip() for skill in entry.get("skills") if str(skill).strip()]
        elif entry.get("skill_family"):
            task["skills"] = [str(entry.get("skill_family")).strip()]
        if isinstance(entry.get("files"), list):
            task["files"] = [str(path).strip() for path in entry.get("files") if str(path).strip()]
        if entry.get("phase") is not None:
            task["phase"] = entry.get("phase")
        if entry.get("description") is not None:
            task["description"] = str(entry.get("description"))
        elif entry.get("notes") is not None:
            task["description"] = str(entry.get("notes"))
        if entry.get("notes") is not None:
            task["notes"] = str(entry.get("notes"))
        if entry.get("next_action") is not None:
            task["next_action"] = entry.get("next_action")
        if entry.get("preview_url") is not None:
            task["preview_url"] = entry.get("preview_url")
        if entry.get("preview_status") is not None:
            task["preview_status"] = entry.get("preview_status")
        if entry.get("created_at") is not None:
            task["created_at"] = entry.get("created_at")
        if entry.get("updated_at") is not None:
            task["updated_at"] = entry.get("updated_at")
        if entry.get("failure_kind") is not None:
            task["failure_kind"] = entry.get("failure_kind")
        artifact_tasks.append(task)

    artifact_files: list[str] = []
    for entry in file_entries:
        path = ""
        if isinstance(entry, dict):
            path = str(entry.get("path") or "").strip()
        elif isinstance(entry, str):
            path = entry.strip()
        if path and path not in artifact_files:
            artifact_files.append(path)

    if not artifact_tasks or not artifact_files:
        fallback = _load_project_snapshot_from_repo_memory(project)
        if fallback:
            if not artifact_tasks:
                artifact_tasks = fallback.get("tasks", [])
            if not artifact_files:
                artifact_files = fallback.get("files", [])
            if not project_snapshot and isinstance(fallback.get("project"), dict):
                project_snapshot = fallback["project"]
            if not manifest.get("generated_at") and fallback.get("generated_at"):
                manifest["generated_at"] = fallback["generated_at"]
            if not summary and isinstance(fallback.get("summary"), dict):
                summary = fallback["summary"]

    return {
        "project": project_snapshot,
        "manifest_path": str(manifest_path) if manifest_path.exists() else None,
        "index_path": str(index_path) if index_path.exists() else None,
        "evidence_path": str(evidence_path) if evidence_path.exists() else None,
        "generated_at": evidence.get("generated_at") or manifest.get("generated_at"),
        "summary": evidence.get("summary") if isinstance(evidence.get("summary"), dict) else None,
        "tasks": artifact_tasks,
        "files": artifact_files,
        "task_count": len(artifact_tasks),
        "file_count": len(artifact_files),
    }


def _load_manifest_file_paths(project: dict[str, Any]) -> list[str]:
    return list(_load_project_artifacts(project)["files"])


def _load_project_snapshot_from_repo_memory(project: dict[str, Any]) -> dict[str, Any] | None:
    """Fallback snapshot loader that reads the repo-side MEMORY.json archive."""
    project_id = str(project.get("id") or "").strip()
    if not project_id:
        return None

    candidate_paths = [BASE_DIR / "MEMORY.json", BASE_DIR / "shared" / "MEMORY.json"]
    for candidate in candidate_paths:
        if not candidate.exists():
            continue
        try:
            snapshot = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(snapshot, dict):
            continue

        source_project = None
        for project_entry in snapshot.get("projects", []) if isinstance(snapshot.get("projects", []), list) else []:
            if not isinstance(project_entry, dict):
                continue
            if str(project_entry.get("id") or "").strip() == project_id:
                source_project = project_entry
                break
        if not source_project:
            continue

        plan_payload: dict[str, Any] = {}
        for message in snapshot.get("messages", []) if isinstance(snapshot.get("messages", []), list) else []:
            if not isinstance(message, dict):
                continue
            if str(message.get("message") or "").strip() not in {"planner_output_ok", "planner_output_replanned_ok"}:
                continue
            raw = message.get("raw") if isinstance(message.get("raw"), dict) else {}
            parsed = raw.get("parsed") if isinstance(raw.get("parsed"), dict) else None
            if isinstance(parsed, dict) and isinstance(parsed.get("plan"), dict):
                plan_payload = parsed
                break
            content = raw.get("content")
            if isinstance(content, str):
                try:
                    plan_payload = json.loads(content)
                except Exception:
                    continue
                if isinstance(plan_payload, dict):
                    break
                plan_payload = {}

        plan = plan_payload.get("plan") if isinstance(plan_payload.get("plan"), dict) else {}
        phases = plan.get("phases") if isinstance(plan.get("phases"), list) else []
        task_skill_summary = (
            project.get("task_skill_summary")
            if isinstance(project.get("task_skill_summary"), dict)
            else source_project.get("task_skill_summary") if isinstance(source_project.get("task_skill_summary"), dict) else {}
        )
        extensions_source = (
            project.get("extensions")
            if isinstance(project.get("extensions"), list)
            else source_project.get("extensions") if isinstance(source_project.get("extensions"), list) else []
        )

        tasks: list[dict[str, Any]] = []
        files: list[str] = []
        task_ids: set[str] = set()

        for phase in phases:
            if not isinstance(phase, dict):
                continue
            for entry in phase.get("tasks", []) if isinstance(phase.get("tasks"), list) else []:
                if not isinstance(entry, dict):
                    continue
                task_id = str(entry.get("id") or "").strip()
                if not task_id:
                    continue
                task_ids.add(task_id)

                task_files = [
                    str(path).strip()
                    for path in (entry.get("files") if isinstance(entry.get("files"), list) else [])
                    if str(path).strip()
                ]
                for path in task_files:
                    if path not in files:
                        files.append(path)

                task: dict[str, Any] = {
                    "id": task_id,
                    "title": str(entry.get("title") or task_id).strip() or task_id,
                    "status": "done",
                    "agent": str(entry.get("agent") or "arch").strip() or "arch",
                    "project_id": project_id,
                    "description": str(entry.get("description") or entry.get("title") or task_id),
                    "files": task_files,
                    "failure_count": 0,
                    "skills": [
                        str(skill).strip()
                        for skill in (entry.get("skills") if isinstance(entry.get("skills"), list) else [])
                        if str(skill).strip()
                    ],
                }
                if not task["skills"] and task_id in task_skill_summary:
                    task["skills"] = [
                        str(skill).strip()
                        for skill in (task_skill_summary.get(task_id) if isinstance(task_skill_summary.get(task_id), list) else [])
                        if str(skill).strip()
                    ]
                tasks.append(task)

        for extension in extensions_source:
            if not isinstance(extension, dict):
                continue
            task_id = str(extension.get("task_id") or "").strip()
            if not task_id or task_id in task_ids:
                continue
            tasks.append(
                {
                    "id": task_id,
                    "title": str(extension.get("title") or task_id).strip() or task_id,
                    "status": "pending",
                    "agent": str(extension.get("agent") or "byte").strip() or "byte",
                    "project_id": project_id,
                    "description": str(extension.get("brief") or extension.get("title") or task_id),
                    "files": [],
                    "failure_count": 0,
                    "retryable": True,
                }
            )

        if not tasks and task_skill_summary:
            for task_id, skills in task_skill_summary.items():
                if not isinstance(task_id, str):
                    continue
                tasks.append(
                    {
                        "id": task_id,
                        "title": task_id,
                        "status": "done",
                        "agent": "byte",
                        "project_id": project_id,
                        "description": task_id,
                        "files": [],
                        "failure_count": 0,
                        "skills": [
                            str(skill).strip()
                            for skill in (skills if isinstance(skills, list) else [])
                            if str(skill).strip()
                        ],
                    }
                )

        return {
            "project": {
                "id": source_project.get("id"),
                "name": source_project.get("name"),
                "description": source_project.get("description"),
                "repo_path": source_project.get("repo_path"),
                "output_dir": source_project.get("output_dir"),
                "repo_url": source_project.get("repo_url"),
                "repo_name": source_project.get("repo_name"),
                "branch": source_project.get("branch"),
                "status": source_project.get("status"),
                "runtime_status": source_project.get("runtime_status"),
                "project_structure": source_project.get("project_structure"),
                "task_skill_summary": task_skill_summary or None,
                "plan_snapshot": plan_payload if plan_payload else None,
            },
            "generated_at": plan_payload.get("generated_at") if isinstance(plan_payload.get("generated_at"), str) else source_project.get("updated_at"),
            "summary": {
                "task_count": len(tasks),
                "file_count": len(files),
                "done_tasks": sum(1 for task in tasks if task.get("status") == "done"),
                "open_tasks": sum(1 for task in tasks if task.get("status") != "done"),
            },
            "tasks": tasks,
            "files": files,
            "task_count": len(tasks),
            "file_count": len(files),
        }


def _normalize_requested_file_path(requested_path: str) -> str:
    normalized = str(requested_path or "").replace("\\", "/").strip()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _guess_file_mime_type(path: str) -> str:
    mime_type, _ = mimetypes.guess_type(path)
    return mime_type or "text/plain"


def _find_related_task_for_file(mem: dict[str, Any], requested_path: str) -> dict[str, Any] | None:
    normalized = _normalize_requested_file_path(requested_path)
    tasks = mem.get("tasks", []) if isinstance(mem.get("tasks", []), list) else []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        files = task.get("files", [])
        if not isinstance(files, list):
            continue
        for file_path in files:
            candidate = _normalize_requested_file_path(str(file_path))
            if not candidate:
                continue
            if (
                candidate == normalized
                or candidate.endswith(normalized)
                or normalized.endswith(candidate)
            ):
                return task
    return None


def _build_archived_file_preview(mem: dict[str, Any], project: dict[str, Any], requested_path: str) -> str | None:
    normalized = _normalize_requested_file_path(requested_path)
    suffix = normalized
    for known_suffix in (
        "models/task.js",
        "controllers/tasks.js",
        "routes/tasks.js",
        "index.js",
        "package.json",
        "README.md",
    ):
        if normalized.endswith(known_suffix):
            suffix = known_suffix
            break

    if suffix not in {"models/task.js", "controllers/tasks.js", "routes/tasks.js"}:
        return None

    project_name = str(project.get("name") or "proyecto").strip() or "proyecto"
    related_task = _find_related_task_for_file(mem, requested_path)
    header_lines = [
        f"// Archivo archivado: {suffix}",
        f"// Proyecto: {project_name}",
    ]
    if related_task:
        header_lines.append(
            f"// Tarea: {related_task.get('id')} - {related_task.get('title')}"
        )
    header_lines.append(
        "// Este archivo ya no está en disco; el dashboard devuelve una reconstrucción legible del snapshot."
    )

    if suffix == "models/task.js":
        return "\n".join(
            header_lines
            + [
                "",
                "const tasks = [];",
                "let nextId = 1;",
                "",
                "function createTask(data) {",
                "  const title = String(data?.title || '').trim();",
                "  if (!title) {",
                "    throw new Error('El campo \"title\" es obligatorio y debe ser una cadena no vacía');",
                "  }",
                "",
                "  const task = {",
                "    id: nextId++,",
                "    title,",
                "    description: String(data?.description || '').trim(),",
                "    completed: false,",
                "    createdAt: new Date().toISOString(),",
                "    updatedAt: new Date().toISOString(),",
                "  };",
                "",
                "  tasks.push(task);",
                "  return task;",
                "}",
                "",
                "function getAllTasks() {",
                "  return [...tasks];",
                "}",
                "",
                "function getTaskById(id) {",
                "  return tasks.find((task) => task.id === Number(id)) || null;",
                "}",
                "",
                "function updateTask(id, updates = {}) {",
                "  const task = getTaskById(id);",
                "  if (!task) return null;",
                "  Object.assign(task, updates, { updatedAt: new Date().toISOString() });",
                "  return task;",
                "}",
                "",
                "function deleteTask(id) {",
                "  const index = tasks.findIndex((task) => task.id === Number(id));",
                "  if (index === -1) return false;",
                "  tasks.splice(index, 1);",
                "  return true;",
                "}",
                "",
                "module.exports = {",
                "  createTask,",
                "  getAllTasks,",
                "  getTaskById,",
                "  updateTask,",
                "  deleteTask,",
                "};",
            ]
        )

    if suffix == "controllers/tasks.js":
        return "\n".join(
            header_lines
            + [
                "",
                "const taskStore = require('../models/task');",
                "",
                "function listTasks(req, res) {",
                "  const tasks = taskStore.getAllTasks();",
                "  res.json({ success: true, data: tasks, count: tasks.length });",
                "}",
                "",
                "function getTask(req, res) {",
                "  const task = taskStore.getTaskById(req.params.id);",
                "  if (!task) {",
                "    return res.status(404).json({ success: false, error: 'Tarea no encontrada' });",
                "  }",
                "  return res.json({ success: true, data: task });",
                "}",
                "",
                "function createTask(req, res) {",
                "  try {",
                "    const task = taskStore.createTask(req.body || {});",
                "    return res.status(201).json({ success: true, data: task, message: 'Tarea creada exitosamente' });",
                "  } catch (error) {",
                "    return res.status(400).json({ success: false, error: error.message });",
                "  }",
                "}",
                "",
                "function updateTask(req, res) {",
                "  const task = taskStore.updateTask(req.params.id, req.body || {});",
                "  if (!task) {",
                "    return res.status(404).json({ success: false, error: 'Tarea no encontrada' });",
                "  }",
                "  return res.json({ success: true, data: task, message: 'Tarea actualizada exitosamente' });",
                "}",
                "",
                "function deleteTask(req, res) {",
                "  const deleted = taskStore.deleteTask(req.params.id);",
                "  if (!deleted) {",
                "    return res.status(404).json({ success: false, error: 'Tarea no encontrada' });",
                "  }",
                "  return res.status(204).send();",
                "}",
                "",
                "module.exports = {",
                "  listTasks,",
                "  getTask,",
                "  createTask,",
                "  updateTask,",
                "  deleteTask,",
                "};",
            ]
        )

    if suffix == "routes/tasks.js":
        return "\n".join(
            header_lines
            + [
                "",
                "const express = require('express');",
                "const router = express.Router();",
                "const tasksController = require('../controllers/tasks');",
                "",
                "router.get('/', tasksController.listTasks);",
                "router.get('/:id', tasksController.getTask);",
                "router.post('/', tasksController.createTask);",
                "router.put('/:id', tasksController.updateTask);",
                "router.delete('/:id', tasksController.deleteTask);",
                "",
                "module.exports = router;",
            ]
        )

    return None


def _path_is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _build_file_view_response(mem: dict[str, Any], requested_path: str) -> dict[str, Any] | None:
    project = mem.get("project", {}) if isinstance(mem.get("project"), dict) else {}
    normalized_requested_path = _normalize_requested_file_path(requested_path)
    if not normalized_requested_path:
        return None

    candidates: list[Path] = []
    raw_path = Path(requested_path)
    output_dir = _resolve_output_dir(project)

    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        candidates.append(output_dir / raw_path)
        candidates.append(output_dir / normalized_requested_path)
        candidates.append(BASE_DIR / raw_path)
        candidates.append(BASE_DIR / normalized_requested_path)
        if normalized_requested_path.startswith("backend/"):
            candidates.append(output_dir / normalized_requested_path.removeprefix("backend/"))

    seen_candidates: set[str] = set()
    for candidate in candidates:
        candidate_key = str(candidate)
        if candidate_key in seen_candidates:
            continue
        seen_candidates.add(candidate_key)
        try:
            if not (
                _path_is_within(candidate, output_dir)
                or _path_is_within(candidate, BASE_DIR)
            ):
                continue
            if not candidate.exists() or not candidate.is_file():
                continue
            content = candidate.read_text(encoding="utf-8", errors="replace")
            stat = candidate.stat()
            return {
                "path": normalized_requested_path,
                "name": candidate.name,
                "content": content,
                "mime": _guess_file_mime_type(candidate.name),
                "size": len(content.encode("utf-8")),
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }
        except Exception:
            continue

    archived_content = _build_archived_file_preview(mem, project, requested_path)
    if archived_content is not None:
        return {
            "path": normalized_requested_path,
            "name": Path(normalized_requested_path).name or normalized_requested_path,
            "content": archived_content,
            "mime": _guess_file_mime_type(normalized_requested_path),
            "size": len(archived_content.encode("utf-8")),
            "modified_at": project.get("updated_at") or mem.get("updated_at") or utc_now(),
            "archived": True,
        }

    return None


@app.get("/api/files/view")
def get_file_view(path: str = ""):
    """Return file content for preview (live or archived)."""
    try:
        mem = load_memory()
        requested_path = str(path or "").strip()
        if not requested_path:
            return JSONResponse({"error": "path es obligatorio"}, status_code=422)

        file_view = _build_file_view_response(mem, requested_path)
        if not file_view:
            return JSONResponse(
                {"error": f"Archivo no encontrado: {requested_path}"},
                status_code=404,
            )

        return {"file": file_view}
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": str(e)},
            status_code=500
        )


@app.get("/api/files")
def get_files():
    """Return file listings for all projects with manifest file counts."""
    try:
        mem = load_memory()
        project = mem.get("project", {}) if isinstance(mem.get("project"), dict) else {}
        current_files = [
            str(path).strip()
            for path in (mem.get("files_produced", []) if isinstance(mem.get("files_produced", []), list) else [])
            if isinstance(path, str) and path.strip()
        ]
        progress_files = [
            str(path).strip()
            for path in (mem.get("progress_files", []) if isinstance(mem.get("progress_files", []), list) else [])
            if isinstance(path, str) and path.strip()
        ]

        produced = list(dict.fromkeys(current_files + progress_files))
        if not produced:
            produced = _load_manifest_file_paths(project)

        project_entries: list[dict[str, Any]] = []
        seen_project_ids: set[str] = set()
        for project_entry in (mem.get("projects", []) if isinstance(mem.get("projects", []), list) else []):
            if not isinstance(project_entry, dict):
                continue
            project_id = str(project_entry.get("id") or "").strip()
            if project_id and project_id in seen_project_ids:
                continue
            project_output_dir = _resolve_output_dir(project_entry)
            manifest_path = project_output_dir / "PROJECT_MANIFEST.json"
            file_count = 0
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    file_count = len(manifest.get("files", [])) if isinstance(manifest.get("files", []), list) else 0
                except Exception:
                    file_count = 0
            project_entries.append(
                {
                    "id": project_entry.get("id"),
                    "name": project_entry.get("name"),
                    "status": project_entry.get("status"),
                    "roots": [],
                    "total_files": file_count,
                }
            )
            if project_id:
                seen_project_ids.add(project_id)

        if project and project.get("id"):
            current_project_id = str(project.get("id") or "").strip()
            if current_project_id and current_project_id in seen_project_ids:
                return {
                    "projects": project_entries,
                    "files_produced": produced,
                    "progress_files": progress_files,
                }
            project_output_dir = _resolve_output_dir(project)
            manifest_path = project_output_dir / "PROJECT_MANIFEST.json"
            file_count = len(produced)
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if isinstance(manifest.get("files", []), list) and manifest.get("files"):
                        file_count = len(manifest.get("files", []))
                except Exception:
                    pass
            project_entries.append(
                {
                    "id": project.get("id"),
                    "name": project.get("name"),
                    "status": project.get("status"),
                    "roots": [],
                    "total_files": file_count,
                }
            )

        return {
            "projects": project_entries,
            "files_produced": produced,
            "progress_files": progress_files,
        }
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": str(e)},
            status_code=500
        )


# ═══════════════════════════════════════════════════════════════════════════════
# STEER & INTERVENTION ENDPOINTS — Dashboard as Co-Pilot Surface
# ═══════════════════════════════════════════════════════════════════════════════

class SteerRequest(BaseModel):
    """Request to send a steering message to an active agent."""
    message: str = Field(..., min_length=1, max_length=1000, description="Steer message content")
    urgent: bool = Field(default=False, description="If true, agent processes immediately on next heartbeat")


class SteerResponse(BaseModel):
    """Response after sending a steer message."""
    ok: bool
    agent_id: str
    message: str
    queued_at: str
    session_key: str | None = None


@app.post("/api/agents/{agent_id}/steer", response_model=SteerResponse)
async def steer_agent(agent_id: str, req: SteerRequest):
    """
    Send a steer message to an active sub-agent session.
    
    ## Design
    
    This endpoint enables **active intervention** by the human operator:
    - The message is queued in MEMORY.json under `messages[].agent_id`
    - On next heartbeat cycle, the agent reads pending messages
    - The agent incorporates the steer into its next planning step
    
    ## Flow
    
    1. Human clicks on active agent in Dashboard
    2. Human types steer message (max 1000 chars)
    3. Frontend calls POST /api/agents/{agent_id}/steer
    4. Backend queues message in MEMORY.json
    5. Agent's next heartbeat reads message from queue
    6. Agent logs: "Received steer: {message[:50]}..."
    7. Agent adjusts plan accordingly
    
    ## Status Codes
    
    - 200: Message queued successfully
    - 404: Agent not found or not active
    - 422: Invalid message (empty or too long)
    """
    mem = load_memory()
    
    # Validate agent exists and is active
    agents = mem.get("agents", {})
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    
    agent = agents[agent_id]
    agent_status = agent.get("status", "offline")
    
    if agent_status not in ("working", "idle", "waiting"):
        # Still queue the message, but warn the caller
        pass
    
    # Queue the steer message
    timestamp = utc_now()
    steer_entry = {
        "type": "steer",
        "agent_id": agent_id,
        "message": req.message,
        "urgent": req.urgent,
        "queued_at": timestamp,
        "read": False,
        "read_at": None,
    }
    
    # Add to messages array
    messages = mem.get("messages", [])
    messages.append(steer_entry)
    mem["messages"] = messages[-100:]  # Keep last 100 messages
    
    # Log the steer action
    log_entry = {
        "ts": timestamp,
        "level": "info",
        "agent": "dashboard",
        "msg": f"Steer sent to {agent_id}: {req.message[:80]}{'...' if len(req.message) > 80 else ''}",
        "meta": {"urgent": req.urgent}
    }
    mem.setdefault("log", []).append(log_entry)
    mem["log"] = mem["log"][-500:]  # Keep last 500 log entries
    
    save_memory(mem)
    
    # Broadcast to connected clients via SSE (if available)
    # broadcast_state_change(mem)  # TODO: implement SSE broadcast
    
    return SteerResponse(
        ok=True,
        agent_id=agent_id,
        message=req.message,
        queued_at=timestamp,
        session_key=agent.get("session_key"),
    )


class TaskPauseResponse(BaseModel):
    """Response after pausing a task."""
    ok: bool
    task_id: str
    status: str
    paused_at: str
    agent_notified: bool


@app.post("/api/tasks/{task_id}/pause", response_model=TaskPauseResponse)
async def pause_task(task_id: str):
    """
    Flag a task as paused in MEMORY.json for ARCH to detect.
    
    ## Design
    
    This enables the human operator to **pause work** on a specific task:
    - The task status is set to "paused" in MEMORY.json
    - ARCH coordinator detects the pause on next heartbeat
    - ARCH reassigns resources or waits for resume signal
    
    ## Flow
    
    1. Human sees a task that needs to pause
    2. Human clicks "Pause" on the task
    3. Frontend calls POST /api/tasks/{task_id}/pause
    4. Backend updates task status to "paused"
    5. ARCH's next heartbeat sees paused status
    6. ARCH logs: "Task {task_id} paused by operator"
    7. ARCH updates plan to work around pause
    
    ## Status Codes
    
    - 200: Task paused successfully
    - 404: Task not found
    - 409: Task already paused
    """
    mem = load_memory()
    
    # Find the task
    tasks = mem.get("tasks", [])
    task = None
    task_index = None
    
    for i, t in enumerate(tasks):
        if t.get("id") == task_id or t.get("task_id") == task_id:
            task = t
            task_index = i
            break
    
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    
    current_status = task.get("status", "pending")
    
    if current_status == "paused":
        raise HTTPException(status_code=409, detail=f"Task '{task_id}' is already paused")
    
    # Update task status
    timestamp = utc_now()
    tasks[task_index]["status"] = "paused"
    tasks[task_index]["paused_at"] = timestamp
    tasks[task_index]["paused_by"] = "operator"
    mem["tasks"] = tasks
    
    # Log the pause action
    log_entry = {
        "ts": timestamp,
        "level": "info",
        "agent": "dashboard",
        "msg": f"Task {task_id} paused by operator",
        "meta": {"previous_status": current_status}
    }
    mem.setdefault("log", []).append(log_entry)
    mem["log"] = mem["log"][-500:]
    
    save_memory(mem)
    # broadcast_state_change(mem)  # TODO: implement SSE broadcast
    
    # Notify ARCH if it has a session
    agent_notified = False
    agents = mem.get("agents", {})
    if "arch" in agents and agents["arch"].get("status") == "working":
        # Queue a notification message for ARCH
        notification = {
            "type": "task_paused",
            "task_id": task_id,
            "timestamp": timestamp,
            "notified_at": utc_now(),
        }
        mem.setdefault("messages", []).append(notification)
        save_memory(mem)
        agent_notified = True
    
    return TaskPauseResponse(
        ok=True,
        task_id=task_id,
        status="paused",
        paused_at=timestamp,
        agent_notified=agent_notified,
    )


class ContextUpdateRequest(BaseModel):
    """Request to update a section of CONTEXT.md."""
    section: str = Field(..., description="Section name to update (e.g., 'Tech Stack', 'Architecture')")
    content: str = Field(..., description="New content for the section")
    reason: str = Field(default="", description="Reason for the change (logged in history)")


class ContextUpdateResponse(BaseModel):
    """Response after updating context."""
    ok: bool
    section: str
    content_length: int
    updated_at: str
    history_entry_id: str


@app.patch("/api/context", response_model=ContextUpdateResponse)
async def update_context(req: ContextUpdateRequest):
    """
    Update a specific section of CONTEXT.md and log the change.
    
    ## Design
    
    This enables the human operator to **modify context** for agents:
    - Updates a specific section in CONTEXT.md
    - Logs the change in plan_history[] for audit
    - Agents pick up changes on next context refresh
    
    ## Flow
    
    1. Human edits a section in the Dashboard
    2. Frontend calls PATCH /api/context
    3. Backend updates CONTEXT.md section
    4. Backend logs change in plan_history
    5. Agents see updated context on next read
    
    ## Supported Sections
    
    - `Tech Stack`: Language, framework, and tool choices
    - `Architecture`: System design decisions
    - `Constraints`: Requirements and limitations
    - `Context`: Project background and goals
    - `Instructions`: Specific agent instructions
    
    ## Status Codes
    
    - 200: Section updated successfully
    - 400: Invalid section name
    - 500: Failed to write CONTEXT.md
    """
    mem = load_memory()
    
    # Validate section name
    valid_sections = ["Tech Stack", "Architecture", "Constraints", "Context", "Instructions", "Notes"]
    if req.section not in valid_sections:
        # Allow custom sections but warn in logs
        print(f"[Context] Unknown section: {req.section}")
    
    # Read current CONTEXT.md
    context_path = CONTEXT_FILE if 'CONTEXT_FILE' in globals() else "/var/www/openclaw-multi-agents/shared/CONTEXT.md"
    
    try:
        context_content = ""
        if os.path.exists(context_path):
            with open(context_path, 'r', encoding='utf-8') as f:
                context_content = f.read()
    except Exception as e:
        print(f"[Context] Error reading CONTEXT.md: {e}")
        context_content = ""
    
    # Update the section
    timestamp = utc_now()
    section_header = f"## {req.section}"
    
    # Find and replace section content
    lines = context_content.split('\n')
    new_lines = []
    in_section = False
    section_start = -1
    
    for i, line in enumerate(lines):
        if line.startswith("## "):
            if in_section:
                # End of current section
                in_section = False
            if line == section_header:
                in_section = True
                section_start = i
                new_lines.append(line)
                new_lines.append(req.content)
                continue
        
        if not in_section:
            new_lines.append(line)
    
    # If section not found, append it
    if section_start == -1:
        new_lines.append("")
        new_lines.append(section_header)
        new_lines.append(req.content)
    
    updated_content = '\n'.join(new_lines)
    
    # Write updated CONTEXT.md
    try:
        os.makedirs(os.path.dirname(context_path), exist_ok=True)
        with open(context_path, 'w', encoding='utf-8') as f:
            f.write(updated_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write CONTEXT.md: {e}")
    
    # Log in plan_history
    history_entry = {
        "id": f"ctx-{timestamp.replace(':', '-').replace('.', '-')}",
        "timestamp": timestamp,
        "type": "context_update",
        "section": req.section,
        "reason": req.reason or f"Updated {req.section} section",
        "content_preview": req.content[:200] + ("..." if len(req.content) > 200 else ""),
        "by": "operator",
    }
    
    mem.setdefault("plan_history", []).append(history_entry)
    mem["plan_history"] = mem["plan_history"][-50:]  # Keep last 50 entries
    
    # Log the action
    log_entry = {
        "ts": timestamp,
        "level": "info",
        "agent": "dashboard",
        "msg": f"Context section '{req.section}' updated: {req.reason or 'No reason provided'}",
        "meta": {"section": req.section, "content_length": len(req.content)}
    }
    mem.setdefault("log", []).append(log_entry)
    mem["log"] = mem["log"][-500:]
    
    save_memory(mem)
    # broadcast_state_change(mem)  # TODO: implement SSE broadcast
    
    return ContextUpdateResponse(
        ok=True,
        section=req.section,
        content_length=len(req.content),
        updated_at=timestamp,
        history_entry_id=history_entry["id"],
    )


# ── OpenAPI Documentation (Tarea 4.2) ────────────────────────────────────────

def custom_openapi():
    """
    Generate custom OpenAPI schema for the Dev Squad Dashboard API.
    
    This provides comprehensive documentation for all endpoints,
    including request/response models and authentication requirements.
    """
    if app.openapi_schema:
        return app.openapi_schema
    
    from fastapi.openapi.utils import get_openapi
    
    openapi_schema = get_openapi(
        title="Dev Squad Multi-Agent Dashboard API",
        version="1.0.0",
        description="""
## Dev Squad Multi-Agent Programming Team

API para orquestar agentes ARCH (Coordinator), BYTE (Programmer) y PIXEL (Designer).

### Autenticación

Todos los endpoints excepto `/health` requieren el header:
```
X-API-Key: <valor de DASHBOARD_API_KEY>
```

### Agentes

| Agente | Rol | Modelo Default |
|--------|-----|----------------|
| ARCH | Coordinator | nvidia/z-ai/glm5 |
| BYTE | Programmer | nvidia/moonshotai/kimi-k2.5 |
| PIXEL | Designer | deepseek/deepseek-chat |

### Endpoints Principales

- **Proyectos**: `/api/project/start`, `/api/project/resume`
- **Modelos**: `/api/models`, `/api/models/agent`
- **Estado**: `/api/state`, `/api/logs`
- **Health**: `/api/health/models`, `/api/health/summary`
- **Streaming**: WebSocket en `/ws/state`
        """,
        routes=app.routes,
        tags=[
            {
                "name": "health",
                "description": "Health checks públicos (sin auth)"
            },
            {
                "name": "models",
                "description": "Gestión de modelos por agente"
            },
            {
                "name": "project",
                "description": "Control de proyectos y orquestador"
            },
            {
                "name": "state",
                "description": "Estado del sistema y logs"
            },
            {
                "name": "streaming",
                "description": "WebSocket y SSE para actualizaciones en tiempo real"
            },
        ],
    )
    
    # Añadir información de seguridad
    openapi_schema["components"]["securitySchemes"] = {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API Key para autenticación"
        }
    }
    
    # Aplicar seguridad global excepto health endpoints
    for path in openapi_schema["paths"]:
        if path not in ["/health", "/api/health"]:
            for method in openapi_schema["paths"][path]:
                openapi_schema["paths"][path][method]["security"] = [
                    {"ApiKeyAuth": []}
                ]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
