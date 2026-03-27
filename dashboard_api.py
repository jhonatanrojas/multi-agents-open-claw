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
from datetime import datetime, timezone
from typing import Any

import requests
import websockets
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
from coordination import send_telegram_message
from shared_state import (
    BASE_DIR,
    DEFAULT_MEMORY,
    _pid_is_alive,
    load_memory,
    refresh_project_runtime_state,
    save_memory,
    utc_now,
)

from websockets.exceptions import ConnectionClosed

MINIVERSE_URL = os.getenv("MINIVERSE_URL", "https://miniverse-public-production.up.railway.app")
MINIVERSE_UI_URL = os.getenv("MINIVERSE_UI_URL", MINIVERSE_URL).strip() or MINIVERSE_URL
MINIVERSE_GITHUB_OWNER = "ianscott313"
MINIVERSE_GITHUB_REPO = "miniverse"
MINIVERSE_GITHUB_API_URL = f"https://api.github.com/repos/{MINIVERSE_GITHUB_OWNER}/{MINIVERSE_GITHUB_REPO}"
MINIVERSE_REQUEST_TIMEOUT_SEC = float(os.getenv("MINIVERSE_REQUEST_TIMEOUT_SEC", "6"))
MINIVERSE_CACHE_TTL_SEC = float(os.getenv("MINIVERSE_CACHE_TTL_SEC", "300"))
MINIVERSE_MOCK_FILE = BASE_DIR / "data" / "miniverse-mock.json"
LOCK_FILE = BASE_DIR / "logs" / "orchestrator.lock"
JSONL_LOG_FILE = BASE_DIR / "logs" / "orchestrator.jsonl"
_MINIVERSE_CACHE: dict[str, Any] = {
    "signature": None,
    "expires_at": 0.0,
    "payload": None,
}

# GAP-1 / P5 — API key auth (empty string = disabled)
_API_KEY: str = os.getenv("DASHBOARD_API_KEY", "")

# Endpoints exempt from auth (public monitoring + streaming)
_AUTH_EXEMPT = {"/health", "/api/health"}
GATEWAY_EVENT_LIMIT = 300
GATEWAY_AGENT_RE = re.compile(r"^agent:(arch|byte|pixel):", re.IGNORECASE)


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
    if isinstance(value, dict):
        return {
            key: _gateway_fingerprint_payload(item)
            for key, item in sorted(value.items())
            if key not in {"timestamp", "ts", "received_at", "_meta", "date"}
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
    asyncio.create_task(_broadcaster.run())
    asyncio.create_task(_gateway_events.run())
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
    save_memory(mem)
    return {"ok": True, "pid": pid, "alive": alive}


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
    return {
        "timestamp": utc_now(),
        **_runtime_process_snapshot(),
    }


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
    snapshot = build_health_snapshot()
    return JSONResponse(snapshot, status_code=200 if snapshot["ok"] else 503)


@app.get("/api/state")
def get_state():
    return load_memory()


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
    limit = max(1, min(int(limit or 100), GATEWAY_EVENT_LIMIT))
    snapshot = _gateway_events.snapshot()
    events = _gateway_consolidate_events(list(snapshot.get("events", [])))[-limit:]
    return {
        "status": snapshot.get("status", {}),
        "events": events,
        "limit": limit,
    }


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


@app.websocket("/ws/gateway-events")
async def ws_gateway_events(websocket: WebSocket):
    """WebSocket endpoint for live OpenClaw Gateway agent events."""
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
                "agents": {"online": 3, "total": 3},
                "theme": "cozy-startup",
            },
            "agents": [
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
    """Spawn orchestrator in background."""
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

    _spawn_orchestrator(args)
    return {
        "status": "started",
        "message": "Orquestador iniciado correctamente",
        "brief": safe_brief,
        "ts": utc_now(),
    }


@app.post("/api/project/resume")
async def resume_project(req: ProjectResumeRequest):
    """Resume failed or pending tasks for the current project."""
    mem = load_memory()
    project = mem.get("project", {}) or {}
    tasks = mem.get("tasks", []) if isinstance(mem.get("tasks", []), list) else []

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
            task["status"] = "pending"
            task.pop("error", None)
            task.pop("failure_kind", None)
            task.pop("retryable", None)
            task.pop("next_action", None)
            task.pop("raw_response", None)
            task.pop("blocked_note", None)
            resumed.append(task_id)
        task_ids.append(task_id)

    if req.task_id and not resumed:
        return JSONResponse({"error": f"No se encontró la tarea {req.task_id} para reanudar"}, status_code=404)

    if not resumed:
        return JSONResponse({"error": "No hay tareas pendientes o fallidas para reanudar"}, status_code=422)

    mem.setdefault("project", {})
    mem["project"]["status"] = "in_progress"
    mem["project"]["updated_at"] = utc_now()
    mem["project"].setdefault("orchestrator", {})
    mem["project"]["orchestrator"].update(
        {
            "status": "starting",
            "phase": "execution",
            "detail": f"Reanudando {len(resumed)} tarea(s)",
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
        "task_ids": task_ids,
        "ts": utc_now(),
    }


@app.post("/api/project/load")
async def load_project(payload: dict[str, Any] | None = None):
    project_id = payload.get("project_id") if isinstance(payload, dict) else None
    if not project_id:
        return JSONResponse({"error": "Se requiere project_id"}, status_code=400)

    mem = load_memory()
    current_proj = mem.get("project", {})
    if current_proj.get("id") == project_id:
        return JSONResponse({"error": "El proyecto ya está activo"}, status_code=400)

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
    mem["project"] = project_to_load
    mem["project"]["status"] = "in_progress"
    mem["project"]["updated_at"] = utc_now()
    
    # Reset temporal de tasks/logs (se pueden repoblar si orchestrator.py reconstruye desde repo)
    mem["tasks"] = []
    mem["plan"] = defaults["plan"]
    mem["log"] = []
    mem["blockers"] = []
    
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
                
                # Limit memory
                if len(mem["messages"]) > 200:
                    mem["messages"] = mem["messages"][-200:]
                
                mem["_telegram_offset"] = last_id
                save_memory(mem)
                
                # Notify UI via SSE/WS
                # (Existing WebSocket connections will see the change in next broadcast)
                broadcast_state_change(mem)

        except Exception as e:
            print(f"[Polling Error] {e}")
            await asyncio.sleep(10)
        
        await asyncio.sleep(10) # Base interval between poll batches

@app.get("/api/logs")
def get_logs():
    mem = load_memory()
    return {
        "log": mem.get("log", [])[-100:],
        "structured_log": _read_jsonl_tail(JSONL_LOG_FILE, 100),
    }
