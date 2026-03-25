#!/usr/bin/env python3
"""
orchestrator.py - Dev Squad Multi-Agent Orchestrator
----------------------------------------------------
Coordinates ARCH, BYTE, and PIXEL with OpenClaw, shared memory, repository
bootstrap, stack-aware skill routing, Telegram notifications, and Miniverse.
"""

from __future__ import annotations

import argparse
import atexit
import asyncio
import datetime
import json
import os
import subprocess
import sys
import time
import shutil
from pathlib import Path
from typing import Any

from openclaw_sdk import OpenClawClient, ProgressCallback

from coordination import (
    RepositoryApprovalRequired,
    RepositoryBootstrapError,
    bootstrap_repository,
    build_task_skill_profile,
    commit_task_output,
    slugify,
    send_telegram_message,
    write_agent_workspace_files,
)
from shared_state import BASE_DIR, ensure_memory_file, load_memory, save_memory, _pid_is_alive
from skills.shared.miniverse_bridge import get_bridge

OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR = BASE_DIR / "logs"
PROJECTS_DIR = BASE_DIR / "projects"
LOCK_FILE = LOG_DIR / "orchestrator.lock"
JSONL_LOG_FILE = LOG_DIR / "orchestrator.jsonl"
AGENT_IDS = ("arch", "byte", "pixel")
DEFAULT_TASK_TIMEOUT_SEC = 1800
DEFAULT_PHASE_TIMEOUT_SEC = 7200
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SEC = 2.0
DEFAULT_DRY_RUN_SUMMARY_FILE = "dry-run-summary.md"
AGENT_LOG_DIR = LOG_DIR / "agents"
RESUME_FAILURE_THRESHOLD = 2

# Labels shown in Telegram/logs for each progress classification.
_PROGRESS_EMOJI = {
    "tool_use": "\u2699\ufe0f",   # ⚙️
    "thinking": "\U0001f9e0",     # 🧠
    "writing": "\u270d\ufe0f",    # ✍️
    "reading": "\U0001f50d",      # 🔍
    "working": "\U0001f527",      # 🔧
    "done": "\u2705",             # ✅
}


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()


def _append_agent_log(agent_id: str, record: dict[str, Any]) -> None:
    """Append a JSONL record to the per-agent log file."""
    agent_log = AGENT_LOG_DIR / f"{agent_id}.jsonl"
    agent_log.parent.mkdir(parents=True, exist_ok=True)
    with agent_log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def make_progress_callback(
    *,
    notify_telegram: bool = True,
    telegram_throttle_sec: float = 30.0,
) -> ProgressCallback:
    """Build a progress callback that logs, notifies Telegram, and updates heartbeats.

    The callback is throttled internally for Telegram (default every 30s)
    while still logging every line to the per-agent JSONL log.
    """
    _last_tg: dict[str, float] = {}  # agent_id -> last telegram ts

    def _callback(agent_id: str, classification: str, line: str, elapsed_sec: float) -> None:
        emoji = _PROGRESS_EMOJI.get(classification, "\U0001f527")
        short = line[:120]

        # 1. Per-agent JSONL log (every line).
        _append_agent_log(agent_id, {
            "ts": utc_now(),
            "agent": agent_id,
            "type": classification,
            "elapsed_sec": round(elapsed_sec, 1),
            "line": line[:500],
        })

        # 2. Miniverse heartbeat (every line, cheap).
        try:
            bridge = get_bridge(agent_id)
            bridge.heartbeat("working", f"{emoji} {short[:60]}")
        except Exception:
            pass

        # 3. Orchestrator JSONL log.
        _append_jsonl_record({
            "ts": utc_now(),
            "agent": agent_id,
            "level": "debug",
            "msg": f"[progress] {classification}: {short}",
            "elapsed_sec": round(elapsed_sec, 1),
        })

        # 4. Telegram notification (throttled per agent).
        if notify_telegram and classification != "done":
            now = time.monotonic()
            prev = _last_tg.get(agent_id, 0.0)
            if (now - prev) >= telegram_throttle_sec:
                _last_tg[agent_id] = now
                try:
                    send_telegram_message(
                        f"{emoji} *{agent_id.upper()}* ({elapsed_sec:.0f}s): {short}",
                    )
                except Exception:
                    pass

        # 5. "done" always notifies Telegram.
        if classification == "done":
            try:
                send_telegram_message(
                    f"{emoji} *{agent_id.upper()}* terminó — {line}",
                )
            except Exception:
                pass

    return _callback


def ensure_runtime_dirs() -> None:
    """Create runtime directories used by the orchestrator."""
    for path in (OUTPUT_DIR, LOG_DIR, PROJECTS_DIR, BASE_DIR / "shared", BASE_DIR / "workspaces", AGENT_LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)


def resolve_path(raw: str | None, fallback: Path) -> Path:
    """Resolve a stored path, keeping relative values rooted at the repo."""
    if not raw:
        return fallback
    path = Path(raw)
    return path if path.is_absolute() else BASE_DIR / path


def normalize_output_path(path: Path) -> str:
    """Store file paths relative to the repository when possible."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(BASE_DIR.resolve()))
    except ValueError:
        return str(resolved)


def load_progress(progress_path: Path) -> dict[str, Any]:
    """Load a task progress JSON file."""
    if not progress_path.exists():
        return {}
    try:
        return json.loads(progress_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_progress(progress_path: Path, payload: dict[str, Any]) -> None:
    """Persist a task progress JSON file."""
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def append_progress_event(progress_path: Path, event_type: str, message: str, **extra: Any) -> dict[str, Any]:
    """Append a progress event and return the updated payload."""
    payload = load_progress(progress_path)
    payload.setdefault("events", [])
    payload["events"].append(
        {
            "ts": utc_now(),
            "type": event_type,
            "message": message,
            **extra,
        }
    )
    payload["updated_at"] = utc_now()
    for key, value in extra.items():
        if value is not None:
            payload[key] = value
    save_progress(progress_path, payload)
    return payload


def _append_jsonl_record(record: dict[str, Any]) -> None:
    """Append a structured JSONL record for operational logs."""
    JSONL_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with JSONL_LOG_FILE.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, ensure_ascii=False) + "\n")


def log_event(message: str, agent: str = "system", level: str = "info", **extra: Any) -> None:
    """Append a log event to shared memory."""
    record = {
        "ts": utc_now(),
        "agent": agent,
        "level": level,
        "msg": message,
        **{k: v for k, v in extra.items() if v is not None},
    }
    mem = load_memory()
    mem.setdefault("log", [])
    mem["log"].append(record)
    mem.setdefault("project", {})
    mem["project"]["updated_at"] = utc_now()
    save_memory(mem)
    _append_jsonl_record(record)


def update_agent_status(agent_id: str, status: str, task: str | None = None) -> None:
    """Update an agent's live status in shared memory."""
    mem = load_memory()
    mem.setdefault("agents", {})
    mem["agents"].setdefault(agent_id, {})
    mem["agents"][agent_id]["status"] = status
    mem["agents"][agent_id]["last_seen"] = utc_now()
    mem["agents"][agent_id]["current_task"] = task
    mem.setdefault("project", {})
    mem["project"]["updated_at"] = utc_now()
    save_memory(mem)


def update_orchestrator_state(
    status: str,
    phase: str | None = None,
    task_id: str | None = None,
    detail: str | None = None,
    dry_run: bool | None = None,
) -> None:
    """Persist the orchestrator runtime state for health checks and dashboards."""
    mem = load_memory()
    mem.setdefault("project", {})
    orchestrator_state = mem["project"].setdefault("orchestrator", {})
    orchestrator_state.update(
        {
            "status": status,
            "phase": phase,
            "task_id": task_id,
            "detail": detail,
            "pid": os.getpid(),
            "updated_at": utc_now(),
        }
    )
    if "started_at" not in orchestrator_state or orchestrator_state["started_at"] is None:
        orchestrator_state["started_at"] = utc_now()
    if dry_run is not None:
        orchestrator_state["dry_run"] = dry_run
    mem["project"]["updated_at"] = utc_now()
    _update_project_history(mem)
    save_memory(mem)


def _ensure_project_id(project: dict[str, Any]) -> str:
    pid = project.get("id")
    if pid:
        return pid
    name = project.get("name") or "project"
    return f"{slugify(name)}-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')}"


def _update_project_history(mem: dict[str, Any]) -> None:
    project = mem.get("project") or {}
    if not isinstance(project, dict):
        return
    project_id = project.get("id")
    if not project_id:
        return
    mem.setdefault("projects", [])
    entry = {
        "id": project_id,
        "name": project.get("name"),
        "description": project.get("description"),
        "status": project.get("status"),
        "created_at": project.get("created_at"),
        "updated_at": project.get("updated_at"),
        "repo_url": project.get("repo_url"),
        "repo_path": project.get("repo_path"),
        "branch": project.get("branch"),
        "output_dir": project.get("output_dir"),
    }
    for existing in mem["projects"]:
        if existing.get("id") == project_id:
            existing.update(entry)
            return
    mem["projects"].append(entry)


def record_blocker(
    message: str,
    source: str = "system",
    *,
    task_id: str | None = None,
    agent_id: str | None = None,
    retryable: bool | None = None,
) -> None:
    """Store a blocker in shared memory."""
    mem = load_memory()
    mem.setdefault("blockers", [])
    mem["blockers"].append(
        {
            "id": f"blk-{abs(hash((source, task_id, agent_id, message, utc_now()))) % 1_000_000}",
            "ts": utc_now(),
            "source": source,
            "msg": message,
            "task_id": task_id,
            "agent_id": agent_id,
            "retryable": retryable,
        }
    )
    save_memory(mem)


def _has_open_tasks(tasks: list[dict[str, Any]]) -> bool:
    return any(task.get("status") != "done" for task in tasks if isinstance(task, dict))


def _fallback_agent_for(task: dict[str, Any], agent_id: str) -> str | None:
    family = str(task.get("skill_family") or "").lower()
    if agent_id == "pixel" and family in {"vanilla-frontend", "frontend"}:
        return "byte"
    return None


def acquire_run_lock() -> dict[str, Any]:
    """Acquire an exclusive lock for the orchestrator process."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": os.getpid(),
        "started_at": utc_now(),
        "argv": sys.argv,
    }
    if LOCK_FILE.exists():
        try:
            existing = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
        existing_pid = existing.get("pid")
        if _pid_is_alive(existing_pid) and existing_pid != os.getpid():
            raise RuntimeError(
                f"Ya hay otro orquestador en ejecución con PID {existing_pid}."
            )
    LOCK_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _release() -> None:
        release_run_lock()

    atexit.register(_release)
    return payload


def release_run_lock() -> None:
    """Release the orchestrator lock if owned by the current process."""
    if not LOCK_FILE.exists():
        return
    try:
        existing = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    except Exception:
        existing = {}
    if existing.get("pid") in {None, os.getpid()}:
        try:
            LOCK_FILE.unlink()
        except FileNotFoundError:
            pass


async def retry_async(
    label: str,
    factory: Any,
    *,
    timeout_sec: int,
    retries: int,
    delay_sec: float,
    agent: str = "system",
) -> Any:
    """Run an async factory with timeout and exponential backoff retries."""
    attempt_delay = max(0.5, float(delay_sec))
    last_exc: Exception | None = None

    for attempt in range(1, max(1, retries) + 1):
        try:
            return await asyncio.wait_for(factory(), timeout=timeout_sec)
        except Exception as exc:
            last_exc = exc
            log_event(
                f"{label} falló en el intento {attempt}/{max(1, retries)}: {exc}",
                agent,
                level="warning",
                attempt=attempt,
                retries=max(1, retries),
                timeout_sec=timeout_sec,
            )
            if attempt < max(1, retries):
                await asyncio.sleep(attempt_delay)
                attempt_delay *= 2

    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"{label} failed without a captured exception")


def normalize_message(agent_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Miniverse inbox payload."""
    sender = raw.get("from") or raw.get("sender") or raw.get("agent") or "unknown"
    message = raw.get("message") or raw.get("text") or raw.get("body") or ""
    message_id = raw.get("id") or raw.get("message_id") or f"{agent_id}-{abs(hash(message)) % 1_000_000}"
    return {
        "id": message_id,
        "from": sender,
        "to": agent_id,
        "message": message,
        "raw": raw,
        "received_at": utc_now(),
    }


def infer_tech_stack_from_brief(brief: str) -> dict[str, str]:
    """Infer a coarse tech stack from the project brief for dry-run validation."""
    text = brief.lower()
    if any(token in text for token in ("laravel", "php", "artisan", "eloquent")):
        return {"frontend": "Blade", "backend": "Laravel", "database": "MySQL"}
    if any(token in text for token in ("express", "node", "nestjs", "fastify", "npm")):
        return {"frontend": "Web UI", "backend": "Node/Express", "database": "SQLite"}
    if any(token in text for token in ("react", "typescript", "vite", "next.js", "nextjs")):
        return {"frontend": "React/TypeScript", "backend": "API", "database": "SQLite"}
    if any(token in text for token in ("devops", "apache", "nginx", "backup", "cron")):
        return {"frontend": "Admin UI", "backend": "Operations", "database": "N/A"}
    return {"frontend": "Frontend", "backend": "Backend", "database": "SQLite"}


def build_dry_run_plan(brief: str) -> dict[str, Any]:
    """Create a deterministic local plan used for dry-run validation."""
    stack = infer_tech_stack_from_brief(brief)
    project_name = brief[:60].strip() or "Dry Run Project"
    project = {
        "name": project_name,
        "description": brief,
        "tech_stack": stack,
    }

    base_tasks = [
        {
            "id": "T-001",
            "agent": "byte",
            "title": "Audit project structure and integration points",
            "description": "Inspect the repository, identify the main modules, and map the integration surface.",
            "acceptance": [
                "Repository layout is documented",
                "Integration points are listed",
                "Risks and dependencies are identified",
            ],
            "depends_on": [],
        },
        {
            "id": "T-002",
            "agent": "byte",
            "title": "Implement core orchestration safeguards",
            "description": "Add lockfile, health, retries, and timeout handling around the orchestrator flow.",
            "acceptance": [
                "Only one orchestrator process can run at a time",
                "Health state is exposed in shared memory",
                "Retries and timeouts are configurable",
            ],
            "depends_on": ["T-001"],
        },
        {
            "id": "T-003",
            "agent": "pixel",
            "title": "Validate dashboard and operational reporting",
            "description": "Confirm the dashboard can surface state and logs without requiring the UI.",
            "acceptance": [
                "Health endpoint is available",
                "Structured logs are accessible",
                "State payload is consistent",
            ],
            "depends_on": ["T-002"],
        },
    ]

    plan = {
        "project": project,
        "plan": {"phases": [{"id": "phase-1", "name": "Dry-run validation", "tasks": base_tasks}]},
        "milestones": ["Dry-run validation complete"],
    }
    return plan


def _load_json_loose(content: str) -> Any:
    """Parse JSON from plain text, fenced markdown, or mixed wrapper text."""
    text = (content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _parse_agent_json_payload(content: str) -> dict[str, Any]:
    """Parse agent JSON output and unwrap OpenClaw payload envelopes."""
    parsed = _load_json_loose(content)
    if isinstance(parsed, dict) and isinstance(parsed.get("plan"), dict):
        return parsed

    if isinstance(parsed, dict):
        payloads = parsed.get("payloads")
        if isinstance(payloads, list):
            for payload in payloads:
                if not isinstance(payload, dict):
                    continue
                payload_text = payload.get("text")
                if not isinstance(payload_text, str) or not payload_text.strip():
                    continue
                try:
                    return _parse_agent_json_payload(payload_text)
                except Exception:
                    continue

        embedded_text = parsed.get("text")
        if isinstance(embedded_text, str) and embedded_text.strip():
            return _parse_agent_json_payload(embedded_text)

    raise ValueError("No se encontró un plan JSON válido en la respuesta del agente")


def _parse_task_json_payload(content: str) -> dict[str, Any]:
    """Parse task output from BYTE or PIXEL, tolerating common wrapper formats."""
    parsed = _load_json_loose(content)
    if isinstance(parsed, dict) and isinstance(parsed.get("files"), list):
        return parsed

    if isinstance(parsed, dict):
        payloads = parsed.get("payloads")
        if isinstance(payloads, list):
            for payload in payloads:
                if not isinstance(payload, dict):
                    continue
                payload_text = payload.get("text")
                if not isinstance(payload_text, str) or not payload_text.strip():
                    continue
                try:
                    return _parse_task_json_payload(payload_text)
                except Exception:
                    continue

        embedded_text = parsed.get("text")
        if isinstance(embedded_text, str) and embedded_text.strip():
            return _parse_task_json_payload(embedded_text)

    raise ValueError("No se encontró una salida JSON válida de la tarea")


def _count_planned_tasks(plan_json: dict[str, Any]) -> int:
    """Return the number of task entries in plan phases."""
    plan = plan_json.get("plan", {}) if isinstance(plan_json, dict) else {}
    phases = plan.get("phases", []) if isinstance(plan, dict) else []
    total = 0
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        tasks = phase.get("tasks", [])
        if isinstance(tasks, list):
            total += sum(1 for task in tasks if isinstance(task, dict))
    return total


def _save_planner_message(raw_content: str, parsed: dict[str, Any] | None, status: str) -> None:
    """Persist planner payload in memory.messages for dashboard diagnostics."""
    mem = load_memory()
    mem.setdefault("messages", [])
    mem["messages"].append(
        {
            "id": f"planner-{int(time.time() * 1000)}",
            "from": "arch",
            "to": "system",
            "message": f"planner_output_{status}",
            "raw": {
                "status": status,
                "content": (raw_content or "")[:20000],
                "parsed": parsed,
            },
            "received_at": utc_now(),
        }
    )
    save_memory(mem)


def build_project_context(mem: dict[str, Any], repo_state: dict[str, Any]) -> str:
    """Build a JSON context string for agent prompts."""
    task_skill_map = {
        task["id"]: {
            "skills": task.get("skills", []),
            "skill_family": task.get("skill_family"),
            "workspace_notes": task.get("workspace_notes", []),
        }
        for task in mem.get("tasks", [])
    }
    context = {
        "project": mem.get("project", {}),
        "repo": repo_state,
        "milestones": mem.get("milestones", []),
        "task_skill_map": task_skill_map,
        "output_dir": mem.get("project", {}).get("output_dir", "./output"),
    }
    return json.dumps(context, indent=2, ensure_ascii=False)


async def relay_team_messages(client: OpenClawClient) -> None:
    """Drain team inboxes, update memory, and let ARCH answer blockers."""
    bridges = {agent_id: get_bridge(agent_id) for agent_id in AGENT_IDS}
    mem = load_memory()
    existing_message_ids: set[str] = {m.get("id", "") for m in mem.get("messages", [])}
    arch_messages: list[dict[str, Any]] = []

    for blocker in mem.get("blockers", []) or []:
        if not isinstance(blocker, dict):
            continue
        blocker_id = blocker.get("id") or ""
        if not blocker_id or blocker.get("arch_notified_at"):
            continue
        arch_messages.append(
            {
                "id": blocker_id,
                "from": blocker.get("source") or "system",
                "to": "arch",
                "message": f"BLOCKER:{blocker.get('task_id') or 'unknown'} {blocker.get('msg') or ''}".strip(),
                "received_at": blocker.get("ts") or utc_now(),
                "raw": blocker,
            }
        )
        blocker["arch_notified_at"] = utc_now()

    for agent_id, bridge in bridges.items():
        try:
            inbox = bridge.check_inbox()
        except Exception as exc:
            log_event(f"Inbox read failed for {agent_id}: {exc}", "system")
            continue

        for raw in inbox or []:
            normalized = normalize_message(agent_id, raw)
            if normalized["id"] in existing_message_ids:
                continue
            existing_message_ids.add(normalized["id"])
            mem.setdefault("messages", [])
            mem["messages"].append(normalized)
            log_event(
                f"Message for {agent_id} from {normalized['from']}: {normalized['message']}",
                normalized["from"],
            )

            message_upper = normalized["message"].upper()
            if "BLOCKER:" in message_upper:
                record_blocker(
                    normalized["message"],
                    normalized["from"],
                    task_id=normalized.get("task_id"),
                    agent_id=normalized.get("from"),
                )
                try:
                    send_telegram_message(f"BLOQUEO de {normalized['from']}: {normalized['message']}")
                except Exception as exc:
                    log_event(f"Falló la notificación por Telegram: {exc}", "system")

            if agent_id == "arch" and normalized["from"] in {"byte", "pixel"}:
                arch_messages.append(normalized)

    save_memory(mem)

    if not arch_messages:
        return

    arch = client.get_agent("arch")
    coord_cb = make_progress_callback(notify_telegram=False)
    result = await arch.execute(
        COORDINATION_PROMPT.format(
            messages=json.dumps(arch_messages, indent=2, ensure_ascii=False),
        ),
        on_progress=coord_cb,
    )

    try:
        payload = json.loads(result.content)
    except json.JSONDecodeError:
        log_event(f"ARCH coordination reply was not valid JSON: {result.content[:200]}", "arch")
        return

    responses = payload.get("responses", [])
    for response in responses:
        target = response.get("to")
        message = (response.get("message") or "").strip()
        if target not in {"byte", "pixel"} or not message:
            continue

        bridges["arch"].message_agent(target, message)
        mem = load_memory()
        mem.setdefault("messages", [])
        mem["messages"].append(
            {
                "id": f"arch-reply-{abs(hash(message)) % 1_000_000}",
                "from": "arch",
                "to": target,
                "message": message,
                "raw": response,
                "received_at": utc_now(),
            }
        )
        save_memory(mem)
        log_event(f"ARCH -> {target}: {message}", "arch")


# ── Gateway health check ───────────────────────────────────────────────────────


async def _check_gateway_health(client: "OpenClawClient") -> None:
    """Raise RuntimeError with a clear message if the gateway is unreachable.

    Tries to resolve each registered agent; any failure is treated as a
    gateway connectivity problem so the operator gets an actionable error
    before any API credits are consumed (GAP-6).
    """
    try:
        for agent_id in AGENT_IDS:
            client.get_agent(agent_id)
    except Exception as exc:
        raise RuntimeError(
            f"Gateway OpenClaw no responde. "
            f"Verifica que el proceso openclaw-gateway esté activo y que "
            f"gateway.yml sea accesible. Detalle: {exc}"
        ) from exc


# ── Fase 1: Planificación ──────────────────────────────────────────────────────

PLANNER_PROMPT = """
Eres ARCH, el coordinador senior de un equipo multiagente de ingeniería.
Analiza la descripción del proyecto y produce un plan JSON estructurado que pueda ser
ejecutado por BYTE y PIXEL.

Requisitos:
- Divide el trabajo en tareas atómicas con criterios de aceptación claros.
- Asigna el trabajo de código a BYTE y el trabajo de UI/diseño a PIXEL.
- Cuando el stack sea evidente, haz que las tareas sean conscientes del stack
  (por ejemplo Laravel/PHP, Node/Express, React/TypeScript, DevOps o documentación).
- Incluye de forma opcional los arreglos "skills" y "workspace_notes" en cada tarea cuando
  ayuden a especializar al agente downstream.

Responde SOLO con JSON válido. No uses fences de markdown.

Schema:
{{
  "project": {{
    "name": "...",
    "description": "...",
    "tech_stack": {{
      "frontend": "...",
      "backend": "...",
      "database": "..."
    }}
  }},
  "plan": {{
    "phases": [
      {{
        "id": "phase-1",
        "name": "...",
        "tasks": [
          {{
            "id": "T-001",
            "agent": "byte|pixel",
            "title": "...",
            "description": "...",
            "acceptance": ["...", "..."],
            "depends_on": [],
            "skills": ["optional", "skill", "list"],
            "workspace_notes": ["optional", "notes"]
          }}
        ]
      }}
    ]
  }},
  "milestones": ["..."]
}}

SOLICITUD DEL PROYECTO: {project_brief}
"""

COORDINATION_PROMPT = """
Eres ARCH, coordinando al equipo.
Responde a los mensajes entrantes de BYTE y PIXEL.

Devuelve solo JSON válido con este esquema:
{{
  "responses": [
    {{
      "to": "byte|pixel",
      "message": "respuesta breve y accionable",
      "in_reply_to": "id de mensaje opcional"
    }}
  ]
}}

MENSAJES:
{messages}
"""

BYTE_TASK_PROMPT = """
Eres BYTE, un ingeniero senior full-stack. Implementa la siguiente tarea.
Lee el contexto del proyecto y los archivos del workspace antes de programar.

CONTEXTO DEL PROYECTO:
{context}

CONTEXTO DEL REPOSITORIO:
{repo_context}

PERFIL DE HABILIDADES:
- Familia: {skill_family}
- Enfoque: {skill_focus}
- Habilidades:
{skill_list}
- Instrucciones:
{instruction_list}

ARCHIVOS DEL WORKSPACE:
- Markdown context: {workspace_md_path}
- JSON context: {workspace_json_path}
- Progress JSON: {progress_path}

TU TAREA:
ID: {task_id}
Título: {title}
Descripción: {description}
Criterios de aceptación:
{acceptance}

PROTOCOLO DE COORDINACIÓN:
- Si te bloqueas, envía a ARCH `BLOCKER:{task_id} <problema>`.
- Si necesitas aclaración, envía a ARCH `QUESTION:{task_id} <pregunta>`.
- Mantén actualizado el JSON de progreso cuando tu entorno permita escribir.

Devuelve el contenido completo de los archivos en este formato JSON:
{{
  "files": [
    {{"path": "relative/path/file.py", "content": "..."}}
  ],
  "notes": "..."
}}
Responde solo con JSON válido.
"""

PIXEL_TASK_PROMPT = """
Eres PIXEL, un diseñador UI/UX senior e ingeniero frontend. Crea los
artefactos de diseño para la siguiente tarea.
Lee el contexto del proyecto y los archivos del workspace antes de diseñar.

CONTEXTO DEL PROYECTO:
{context}

CONTEXTO DEL REPOSITORIO:
{repo_context}

PERFIL DE HABILIDADES:
- Familia: {skill_family}
- Enfoque: {skill_focus}
- Habilidades:
{skill_list}
- Instrucciones:
{instruction_list}

ARCHIVOS DEL WORKSPACE:
- Markdown context: {workspace_md_path}
- JSON context: {workspace_json_path}
- Progress JSON: {progress_path}

TU TAREA:
ID: {task_id}
Título: {title}
Descripción: {description}
Criterios de aceptación:
{acceptance}

PROTOCOLO DE COORDINACIÓN:
- Si te bloqueas, envía a ARCH `BLOCKER:{task_id} <problema>`.
- Si necesitas aclaración, envía a ARCH `QUESTION:{task_id} <pregunta>`.
- Mantén actualizado el JSON de progreso cuando tu entorno permita escribir.

Devuelve los artefactos de diseño en este formato JSON:
{{
  "files": [
    {{"path": "design/{task_id}/component.tsx", "content": "..."}},
    {{"path": "design/{task_id}/spec.md", "content": "..."}}
  ],
  "notes": "..."
}}
Si no puedes completar todos los artefactos, devuelve igualmente JSON válido con
`files` como lista vacía y explica el bloqueo solo en `notes`.
Responde solo con JSON válido.
"""

REVIEW_PROMPT = """
Eres ARCH. Todas las tareas están completas. Revisa el resultado del proyecto y
produce un resumen final de entrega.

ESTADO DE MEMORIA:
{memory}

Escribe un resumen en markdown (## Resumen de entrega) que cubra:
1. Qué se construyó
2. Archivos producidos (listarlos)
3. Cómo ejecutar el proyecto
4. Limitaciones conocidas o siguientes pasos
"""


async def plan_project(
    client: OpenClawClient | None,
    brief: str,
    *,
    dry_run: bool = False,
    retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
    retry_delay_sec: float = DEFAULT_RETRY_DELAY_SEC,
    phase_timeout_sec: int = DEFAULT_PHASE_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Ask ARCH to produce a plan and persist it to shared memory."""
    arch_bridge = get_bridge("arch")
    arch_bridge.heartbeat("thinking", f"Planificando: {brief[:60]}")
    update_agent_status("arch", "thinking", "initial_planning")
    update_orchestrator_state("planning", phase="planning", detail="Creando el plan del proyecto", dry_run=dry_run)
    log_event(f"Planificando proyecto: {brief}", "arch")

    if dry_run:
        plan_json = build_dry_run_plan(brief)
    else:
        if client is None:
            raise RuntimeError("Se requiere un cliente OpenClaw fuera del modo dry-run")
        arch = client.get_agent("arch")
        progress_cb = make_progress_callback(notify_telegram=True, telegram_throttle_sec=30.0)
        planner_prompt = PLANNER_PROMPT.format(project_brief=brief)
        result = await retry_async(
            "Planner execution",
            lambda: arch.execute(planner_prompt, on_progress=progress_cb),
            timeout_sec=phase_timeout_sec,
            retries=retry_attempts,
            delay_sec=retry_delay_sec,
            agent="arch",
        )
        log_event(
            f"ARCH respondió en {result.elapsed_sec:.0f}s "
            f"(content_len={len(result.content)}, stderr_lines={len(result.stderr_lines)})",
            "arch",
        )
        planner_content = result.content or ""

        log_event(
            f"ARCH respondió en {result.elapsed_sec:.0f}s "
            f"(content_len={len(result.content)}, stderr_lines={len(result.stderr_lines)})",
            "arch",
        )

        try:
            plan_json = _parse_agent_json_payload(planner_content)
        except (json.JSONDecodeError, ValueError) as exc:
            _save_planner_message(planner_content, parsed=None, status="invalid_json")
            update_agent_status("arch", "error", "planning_failed")
            log_event(
                f"El planificador devolvió JSON inválido: {exc} — "
                f"content[:300]={result.content[:300]}",
                "arch",
                level="error",
            )
            update_orchestrator_state("error", phase="planning", detail="El planificador devolvió JSON inválido", dry_run=dry_run)
            raise RuntimeError("El planificador devolvió JSON inválido") from exc

        planned_tasks = _count_planned_tasks(plan_json)
        _save_planner_message(planner_content, parsed=plan_json, status="ok")
        if planned_tasks == 0:
            update_agent_status("arch", "error", "planning_empty")
            log_event("El planificador devolvió 0 tareas; se cancela la ejecución para revisión.", "arch", level="error")
            update_orchestrator_state(
                "error",
                phase="planning",
                detail="El planificador devolvió 0 tareas",
                dry_run=dry_run,
            )
            raise RuntimeError("El planificador devolvió 0 tareas. Revisa memory.messages para el payload crudo.")

    mem = load_memory()
    project_patch = plan_json.get("project", {})
    mem.setdefault("project", {})
    mem["project"].update(
        {
            **project_patch,
            "id": project_patch.get("id") or _ensure_project_id(project_patch),
            "status": "planned",
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
    )
    mem["plan"] = plan_json.get("plan", {"phases": []})
    mem["milestones"] = plan_json.get("milestones", [])
    _update_project_history(mem)

    all_tasks: list[dict[str, Any]] = []
    task_skill_summary: dict[str, list[str]] = {}
    for phase in mem["plan"].get("phases", []):
        for task in phase.get("tasks", []):
            task["phase"] = phase.get("id")
            task["status"] = "pending"
            profile = build_task_skill_profile(mem["project"], task)
            task["skill_family"] = profile["family"]
            task["skill_profile"] = profile
            task["skills"] = profile["skills"]
            task["workspace_notes"] = profile["instructions"]
            task_skill_summary[task["id"]] = profile["skills"]
            all_tasks.append(task)

    mem["tasks"] = all_tasks
    mem["project"]["task_skill_summary"] = task_skill_summary
    save_memory(mem)

    arch_bridge.speak(
        f"Plan listo. {len(all_tasks)} tareas en {len(mem['plan'].get('phases', []))} fases."
    )
    log_event(f"Plan creado: {len(all_tasks)} tareas", "arch")
    update_agent_status("arch", "idle", None)
    update_orchestrator_state("planned", phase="planning", detail=f"{len(all_tasks)} tareas planificadas", dry_run=dry_run)
    return plan_json


# ── Phase 2: Execution ─────────────────────────────────────────────────────────


async def execute_task(
    client: OpenClawClient | None,
    task: dict[str, Any],
    project_context: str,
    repo_state: dict[str, Any],
    *,
    dry_run: bool = False,
    task_timeout_sec: int = DEFAULT_TASK_TIMEOUT_SEC,
    retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
    retry_delay_sec: float = DEFAULT_RETRY_DELAY_SEC,
) -> None:
    """Execute one task with the assigned agent and persist progress."""
    agent_id = task["agent"]
    task_id = task["id"]
    bridge = get_bridge(agent_id)
    mem = load_memory()
    project = mem.get("project", {})
    output_dir = resolve_path(project.get("output_dir"), OUTPUT_DIR)
    if dry_run:
        output_dir = OUTPUT_DIR / "dry-run" / task_id
    output_dir.mkdir(parents=True, exist_ok=True)

    skill_profile = task.get("skill_profile") or build_task_skill_profile(project, task)
    workspace_files = write_agent_workspace_files(agent_id, task, project, skill_profile, repo_state)
    progress_path = workspace_files["progress_path"]

    update_agent_status(agent_id, "working", task_id)
    update_orchestrator_state("executing", phase="execution", task_id=task_id, detail=f"Ejecutando {task_id}", dry_run=dry_run)
    bridge.heartbeat("working", f"Tarea {task_id}: {task['title'][:50]}")
    bridge.speak(f"Iniciando {task_id}: {task['title']}")
    log_event(f"Iniciando tarea {task_id}", agent_id)

    mem = load_memory()
    for t in mem.get("tasks", []):
        if t.get("id") == task_id:
            t["status"] = "in_progress"
            t["progress_file"] = str(progress_path)
            t["workspace_context"] = str(workspace_files["context_md"])
            t["skills"] = skill_profile["skills"]
            t["skill_family"] = skill_profile["family"]
    if str(progress_path) not in mem.get("progress_files", []):
        mem.setdefault("progress_files", []).append(str(progress_path))
    save_memory(mem)

    append_progress_event(
        progress_path,
        "started",
        "Tarea iniciada",
        status="in_progress",
        skill_profile=skill_profile,
        repo_state=repo_state,
        dry_run=dry_run,
    )

    acceptance_str = "\n".join(f"- {a}" for a in task.get("acceptance", []))
    skill_list = "\n".join(f"- {item}" for item in skill_profile.get("skills", []) or ["General engineering"])
    instruction_list = "\n".join(
        f"- {item}" for item in skill_profile.get("instructions", []) or ["Follow the repository stack."]
    )
    prompt_kwargs = {
        "context": project_context,
        "repo_context": json.dumps(repo_state, indent=2, ensure_ascii=False),
        "skill_family": skill_profile.get("family", "general"),
        "skill_focus": skill_profile.get("prompt_focus", "General engineering specialist"),
        "skill_list": skill_list,
        "instruction_list": instruction_list,
        "workspace_md_path": str(workspace_files["context_md"]),
        "workspace_json_path": str(workspace_files["context_json"]),
        "progress_path": str(progress_path),
        "task_id": task_id,
        "title": task["title"],
        "description": task["description"],
        "acceptance": acceptance_str,
    }

    if agent_id == "byte":
        prompt = BYTE_TASK_PROMPT.format(**prompt_kwargs)
    else:
        prompt = PIXEL_TASK_PROMPT.format(**prompt_kwargs)

    def mark_task_failure(
        detail: str,
        *,
        progress_message: str,
        retryable: bool = True,
        raw_response: str | None = None,
    ) -> None:
        append_progress_event(
            progress_path,
            "error",
            progress_message,
            status="error",
            raw_response=(raw_response[:1000] if isinstance(raw_response, str) else None),
        )
        mem = load_memory()
        fallback_agent: str | None = None
        for t in mem.get("tasks", []):
            if t.get("id") == task_id:
                failure_count = int(t.get("failure_count") or 0) + 1
                t["status"] = "error"
                t["error"] = detail
                t["retryable"] = retryable
                t["next_action"] = "review" if not retryable else "retry_or_reassign"
                t["failure_count"] = failure_count
                t["last_failure_at"] = utc_now()
                if raw_response:
                    t["raw_response"] = raw_response[:2000]
                fallback_agent = _fallback_agent_for(t, agent_id)
                if retryable and fallback_agent and failure_count >= RESUME_FAILURE_THRESHOLD:
                    t["previous_agent"] = agent_id
                    t["agent"] = fallback_agent
                    t["status"] = "pending"
                    t["next_action"] = f"reassigned_to_{fallback_agent}"
                    t["suggested_agent"] = fallback_agent
                    t["reassigned_at"] = utc_now()
        save_memory(mem)
        record_blocker(
            f"Tarea {task_id} ({agent_id}) falló: {detail}",
            source=agent_id,
            task_id=task_id,
            agent_id=agent_id,
            retryable=retryable,
        )
        if fallback_agent and retryable and failure_count >= RESUME_FAILURE_THRESHOLD:
            log_event(
                f"Tarea {task_id} reasignada automáticamente a {fallback_agent} tras {failure_count} fallos",
                "system",
                level="warning",
            )
        bridge.heartbeat("error", f"Error en {task_id}")
        update_agent_status(agent_id, "error", task_id)
        update_orchestrator_state("error", phase="execution", task_id=task_id, detail=detail, dry_run=dry_run)
        log_event(f"La tarea {task_id} FALLÓ: {detail}", agent_id, level="error")

    if dry_run:
        data = {
            "files": [
                {
                    "path": f"{task_id.lower()}/dry-run-summary.md",
                    "content": "\n".join(
                        [
                            f"# Resultado de dry-run para {task_id}",
                            "",
                            f"- Agent: {agent_id}",
                            f"- Title: {task['title']}",
                            f"- Family: {skill_profile.get('family', 'general')}",
                            "",
                            "Esta tarea se ejecutó en modo dry-run.",
                            "No se ejecutó ningún agente externo ni se modificó el repositorio.",
                        ]
                    ),
                }
            ],
            "notes": "Dry-run completado correctamente.",
        }
    else:
        if client is None:
            raise RuntimeError("Se requiere un cliente OpenClaw fuera del modo dry-run")
        agent = client.get_agent(agent_id)

    task_progress_cb = make_progress_callback(notify_telegram=True, telegram_throttle_sec=30.0)

    try:
        if dry_run:
            result = None
        else:
            result = await retry_async(
                f"Ejecución de tarea del agente {agent_id}",
                (lambda _a=agent, _p=prompt, _cb=task_progress_cb: lambda: _a.execute(_p, on_progress=_cb))(),
                timeout_sec=task_timeout_sec,
                retries=retry_attempts,
                delay_sec=retry_delay_sec,
                agent=agent_id,
            )
    except Exception as exc:
        mark_task_failure(
            f"error de ejecución del agente: {exc}",
            progress_message=f"Falló la ejecución del agente: {exc}",
            retryable=True,
        )
        return

    if not dry_run and result is not None:
        log_event(
            f"{agent_id.upper()} respondió en {result.elapsed_sec:.0f}s "
            f"(content_len={len(result.content)}, stderr_lines={len(result.stderr_lines)})",
            agent_id,
        )

    try:
        if not dry_run:
            data = _parse_task_json_payload(result.content)
    except Exception:
        mark_task_failure(
            "Invalid JSON response",
            progress_message="Respuesta JSON inválida del agente",
            retryable=True,
            raw_response=result.content,
        )
        return

    try:
        files_written: list[str] = []
        for f in data.get("files", []):
            fpath = output_dir / f["path"]
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(f["content"], encoding="utf-8")
            files_written.append(normalize_output_path(fpath))

        mem = load_memory()
        for t in mem.get("tasks", []):
            if t.get("id") == task_id:
                t["status"] = "done"
                t["files"] = files_written
                t["notes"] = data.get("notes", "")
                t["progress_file"] = str(progress_path)
                t["skill_family"] = skill_profile["family"]
                t["skills"] = skill_profile["skills"]
        mem.setdefault("files_produced", [])
        mem["files_produced"].extend([f for f in files_written if f not in mem["files_produced"]])
        save_memory(mem)

        append_progress_event(
            progress_path,
            "completed",
            "Tarea completada correctamente",
            status="done",
            files=files_written,
            notes=data.get("notes", ""),
            dry_run=dry_run,
        )

        # Git auto-commit (GAP-7 / P4) — non-fatal if repo has no changes
        if repo_state.get("action") not in ("dry-run", None) and files_written:
            try:
                committed = commit_task_output(
                    Path(repo_state["repo_path"]),
                    agent_id,
                    task_id,
                    task.get("title", task_id),
                )
                if committed:
                    log_event(f"Git commit creado para {task_id}", agent_id)
            except Exception as exc:
                log_event(f"Git commit falló (no crítico): {exc}", agent_id, level="warning")

        bridge.heartbeat("idle", f"Done: {task_id}")
        bridge.speak(f"Completada {task_id}: se escribieron {len(files_written)} archivo(s).")
        log_event(f"Tarea {task_id} completada. Archivos: {files_written}", agent_id)
        update_agent_status(agent_id, "idle", None)
        update_orchestrator_state("idle", phase="execution", task_id=None, detail=f"Completed {task_id}", dry_run=dry_run)
        try:
            send_telegram_message(
                f"Tarea completada: {task_id} ({agent_id}) - se escribieron {len(files_written)} archivo(s)."
            )
        except Exception as exc:
            log_event(f"Falló la notificación por Telegram: {exc}", "system")
    except Exception as exc:
        mark_task_failure(
            f"error al escribir archivos: {exc}",
            progress_message=f"Falló la escritura de archivos: {exc}",
            retryable=False,
        )


# ── Fase 3: Revisión final ─────────────────────────────────────────────────────


async def final_review(
    client: OpenClawClient | None,
    *,
    dry_run: bool = False,
    phase_timeout_sec: int = DEFAULT_PHASE_TIMEOUT_SEC,
    retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
    retry_delay_sec: float = DEFAULT_RETRY_DELAY_SEC,
) -> None:
    """Ask ARCH for the delivery summary and persist it."""
    arch_bridge = get_bridge("arch")

    arch_bridge.heartbeat("thinking", "Revisando todo el trabajo completado")
    mem = load_memory()
    update_orchestrator_state("review", phase="review", detail="Revisión final en progreso", dry_run=dry_run)

    if dry_run:
        result_content = "\n".join(
            [
                "# Delivery Summary",
                "",
                "Dry-run completado correctamente.",
                "",
                "No se ejecutaron agentes externos ni se modificó el repositorio.",
            ]
        )
    else:
        if client is None:
            raise RuntimeError("Se requiere un cliente OpenClaw fuera del modo dry-run")
        arch = client.get_agent("arch")
        review_cb = make_progress_callback(notify_telegram=True, telegram_throttle_sec=30.0)
        review_prompt = REVIEW_PROMPT.format(memory=json.dumps(mem, indent=2, ensure_ascii=False))
        result = await retry_async(
            "Final review",
            lambda: arch.execute(review_prompt, on_progress=review_cb),
            timeout_sec=phase_timeout_sec,
            retries=retry_attempts,
            delay_sec=retry_delay_sec,
            agent="arch",
        )
        log_event(
            f"Review completado en {result.elapsed_sec:.0f}s "
            f"(content_len={len(result.content)}, stderr_lines={len(result.stderr_lines)})",
            "arch",
        )
        result_content = result.content

    if _has_open_tasks(mem.get("tasks", [])):
        mem = load_memory()
        mem.setdefault("project", {})
        mem["project"]["status"] = "in_progress"
        mem["project"]["updated_at"] = utc_now()
        save_memory(mem)
        update_orchestrator_state(
            "paused",
            phase="review",
            detail="Revisión detenida: existen tareas pendientes o con error",
            dry_run=dry_run,
        )
        log_event(
            "La revisión final detectó tareas pendientes o con error; no se marcará como entregado",
            "system",
            level="warning",
        )
        return

    project_output_dir = resolve_path(mem.get("project", {}).get("output_dir"), OUTPUT_DIR)
    project_output_dir.mkdir(parents=True, exist_ok=True)
    delivery_path = project_output_dir / "DELIVERY.md"
    delivery_path.write_text(result_content, encoding="utf-8")

    if delivery_path.resolve() != (OUTPUT_DIR / "DELIVERY.md").resolve():
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "DELIVERY.md").write_text(result_content, encoding="utf-8")

    mem = load_memory()
    mem.setdefault("project", {})
    mem["project"]["status"] = "delivered"
    mem["project"]["updated_at"] = utc_now()
    mem.setdefault("milestones", [])
    mem["milestones"].append(f"Proyecto entregado en {utc_now()}")
    save_memory(mem)

    arch_bridge.speak("Proyecto entregado. Revisa DELIVERY.md")
    log_event("Proyecto entregado. Revisa DELIVERY.md", "arch")
    try:
        send_telegram_message(f"Proyecto entregado: {mem.get('project', {}).get('name') or 'proyecto sin nombre'}")
    except Exception as exc:
        log_event(f"Falló la notificación por Telegram: {exc}", "system")
    update_orchestrator_state("idle", phase="review", detail="Proyecto entregado", dry_run=dry_run)

    print("\n" + "=" * 60)
    print(result_content)
    print("=" * 60)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Ejecutar el orquestador de Dev Squad.")
    parser.add_argument("brief", nargs="*", help="Descripción del proyecto")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reanudar ejecución usando el proyecto y tareas ya guardados en MEMORY.json",
    )
    parser.add_argument("--repo-url", dest="repo_url", help="URL del repositorio existente para clonar")
    parser.add_argument("--repo-name", dest="repo_name", help="Nombre del repositorio para creación local")
    parser.add_argument("--branch", dest="branch", help="Nombre de la rama a crear o usar")
    parser.add_argument(
        "--allow-init-repo",
        action="store_true",
        help="Inicializar un repositorio git local cuando no se provee URL",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validar la orquestación sin llamar a OpenClaw ni modificar el repositorio",
    )
    parser.add_argument(
        "--task-timeout-sec",
        type=int,
        default=DEFAULT_TASK_TIMEOUT_SEC,
        help="Tiempo máximo por intento de ejecución de tarea",
    )
    parser.add_argument(
        "--phase-timeout-sec",
        type=int,
        default=DEFAULT_PHASE_TIMEOUT_SEC,
        help="Tiempo máximo para las fases de planificación y revisión",
    )
    parser.add_argument(
        "--retry-attempts",
        type=int,
        default=DEFAULT_RETRY_ATTEMPTS,
        help="Número de reintentos para agentes y operaciones de red",
    )
    parser.add_argument(
        "--retry-delay-sec",
        type=float,
        default=DEFAULT_RETRY_DELAY_SEC,
        help="Retraso inicial entre reintentos en segundos",
    )
    # GAP-8 / P8 — configurable parallelism
    parser.add_argument(
        "--max-parallel-byte",
        type=int,
        default=1,
        dest="max_parallel_byte",
        help="Número máximo de tareas BYTE en paralelo (default 1)",
    )
    parser.add_argument(
        "--max-parallel-pixel",
        type=int,
        default=1,
        dest="max_parallel_pixel",
        help="Número máximo de tareas PIXEL en paralelo (default 1)",
    )
    # P9 — webhook post-entrega
    parser.add_argument(
        "--webhook-url",
        dest="webhook_url",
        default=None,
        help="URL para enviar un POST con el estado final cuando el proyecto se entrega",
    )
    return parser.parse_args()


async def main(args: argparse.Namespace) -> None:
    """Run the full orchestration lifecycle."""
    project_brief = " ".join(args.brief).strip() or (
        "Construye una aplicación simple de tareas con frontend en React + TypeScript, "
        "backend en FastAPI, base de datos SQLite, API REST y una interfaz limpia."
    )

    ensure_runtime_dirs()
    ensure_memory_file()
    success = False

    try:
        acquire_run_lock()
        update_orchestrator_state("starting", phase="startup", detail="Secuencia de arranque iniciada", dry_run=args.dry_run)
        print(f"\nDev Squad iniciando - Proyecto: {project_brief}\n")
        log_event(f"Orquestador iniciando. dry_run={args.dry_run}", "system")

        # GAP-3 / P3 — recover tasks that were in_progress when the last run crashed
        mem = load_memory()
        stale = [t for t in mem.get("tasks", []) if t.get("status") == "in_progress"]
        if stale:
            for task in mem["tasks"]:
                if task.get("status") == "in_progress":
                    task["status"] = "pending"
            save_memory(mem)
            log_event(
                f"Recuperadas {len(stale)} tarea(s) bloqueadas en in_progress → pending",
                "system",
                level="warning",
            )
            print(f"[recovery] {len(stale)} tarea(s) reseteadas a pending.")

        for agent_id in AGENT_IDS:
            bridge = get_bridge(agent_id)
            bridge.heartbeat("idle", "Preparando entorno")

        if args.resume:
            mem = load_memory()
            project_brief = mem.get("project", {}).get("description") or project_brief

        if args.dry_run:
            print("Fase 1: Planificación (dry-run)...")
            await plan_project(
                None,
                project_brief,
                dry_run=True,
                retry_attempts=args.retry_attempts,
                retry_delay_sec=args.retry_delay_sec,
                phase_timeout_sec=args.phase_timeout_sec,
            )
            mem = load_memory()
            mem.setdefault("project", {})
            mem["project"]["output_dir"] = str(OUTPUT_DIR / "dry-run")
            mem["project"]["updated_at"] = utc_now()
            save_memory(mem)
            repo_state = {
                "repo_url": args.repo_url,
                "repo_name": args.repo_name,
                "repo_path": args.repo_name or "dry-run-repo",
                "branch": args.branch or "codex/dry-run",
                "action": "dry-run",
                "git_available": shutil.which("git") is not None,
            }
            project_context = build_project_context(mem, repo_state)
            for task in list(mem.get("tasks", [])):
                if task.get("status") == "pending":
                    await execute_task(
                        None,
                        task,
                        project_context,
                        repo_state,
                        dry_run=True,
                        task_timeout_sec=args.task_timeout_sec,
                        retry_attempts=args.retry_attempts,
                        retry_delay_sec=args.retry_delay_sec,
                    )
            print("\nFase 3: Revisión final...")
            await final_review(
                None,
                dry_run=True,
                phase_timeout_sec=args.phase_timeout_sec,
                retry_attempts=args.retry_attempts,
                retry_delay_sec=args.retry_delay_sec,
            )
        else:
            async with OpenClawClient.connect() as client:
                # GAP-6 — verify gateway is reachable before consuming any tokens
                try:
                    await _check_gateway_health(client)
                    log_event("Gateway OpenClaw verificado correctamente", "system")
                except RuntimeError as exc:
                    log_event(str(exc), "system", level="error")
                    update_orchestrator_state("error", phase="startup", detail=str(exc), dry_run=args.dry_run)
                    print(f"\n{exc}")
                    return

                if args.resume:
                    print("Fase 2: Reanudando tareas...")
                    mem = load_memory()
                    repo_state = {
                        "repo_url": mem.get("project", {}).get("repo_url"),
                        "repo_name": mem.get("project", {}).get("repo_name") or mem.get("project", {}).get("name"),
                        "repo_path": mem.get("project", {}).get("repo_path") or mem.get("project", {}).get("output_dir"),
                        "branch": mem.get("project", {}).get("branch"),
                        "action": "resume",
                        "git_available": shutil.which("git") is not None,
                    }
                    mem.setdefault("project", {})
                    mem["project"]["status"] = "in_progress"
                    mem["project"]["updated_at"] = utc_now()
                    save_memory(mem)
                else:
                    print("Fase 1: Planificación...")
                    try:
                        await plan_project(
                            client,
                            project_brief,
                            dry_run=False,
                            retry_attempts=args.retry_attempts,
                            retry_delay_sec=args.retry_delay_sec,
                            phase_timeout_sec=args.phase_timeout_sec,
                        )
                    except Exception as exc:
                        log_event(f"Falló la planificación: {exc}", "arch", level="error")
                        try:
                            send_telegram_message(f"Falló la planificación: {exc}")
                        except Exception:
                            pass
                        update_orchestrator_state("error", phase="planning", detail=str(exc), dry_run=args.dry_run)
                        print(f"Falló la planificación: {exc}")
                        return

                    mem = load_memory()
                    try:
                        repo_state = bootstrap_repository(
                            mem.get("project", {}),
                            repo_url=args.repo_url,
                            repo_name=args.repo_name,
                            branch=args.branch,
                            allow_init_repo=args.allow_init_repo,
                        )
                        mem = load_memory()
                        mem.setdefault("project", {})
                        mem["project"]["bootstrap_status"] = repo_state.get("action")
                        mem["project"]["repo_path"] = repo_state.get("repo_path")
                        mem["project"]["branch"] = repo_state.get("branch")
                        mem["project"]["output_dir"] = repo_state.get("repo_path")
                        mem["project"]["updated_at"] = utc_now()
                        save_memory(mem)
                        log_event(
                            f"Repositorio listo: {repo_state.get('action')} -> {repo_state.get('repo_path')} @ {repo_state.get('branch')}",
                            "arch",
                        )
                        try:
                            send_telegram_message(
                                f"Repositorio listo: {repo_state.get('action')} -> {repo_state.get('repo_path')} @ {repo_state.get('branch')}"
                            )
                        except Exception as exc:
                            log_event(f"Falló la notificación por Telegram: {exc}", "system", level="warning")
                    except RepositoryApprovalRequired as exc:
                        mem = load_memory()
                        mem.setdefault("project", {})
                        mem["project"]["bootstrap_status"] = "approval_required"
                        mem["project"]["updated_at"] = utc_now()
                        mem.setdefault("blockers", [])
                        mem["blockers"].append(
                            {
                                "ts": utc_now(),
                                "source": "arch",
                                "msg": str(exc),
                            }
                        )
                        save_memory(mem)
                        log_event(f"Se requiere aprobación del repositorio: {exc}", "arch", level="warning")
                        try:
                            send_telegram_message(f"Se requiere aprobación del repositorio: {exc}")
                        except Exception:
                            pass
                        print(str(exc))
                        return
                    except RepositoryBootstrapError as exc:
                        log_event(f"Falló el bootstrap del repositorio: {exc}", "arch", level="error")
                        try:
                            send_telegram_message(f"Falló el bootstrap del repositorio: {exc}")
                        except Exception:
                            pass
                        print(f"Falló el bootstrap del repositorio: {exc}")
                        return

                print("\nFase 2: Ejecutando tareas...")
                mem = load_memory()
                completed_ids: set[str] = set()
                pending_tasks = [task for task in mem.get("tasks", [])]
                max_rounds = len(pending_tasks) + 8
                rounds = 0
                project_context = build_project_context(mem, repo_state)
                phase_deadline = time.monotonic() + max(60, args.phase_timeout_sec)
                update_orchestrator_state("executing", phase="execution", detail="Ejecutando tareas", dry_run=args.dry_run)

                while pending_tasks and rounds < max_rounds:
                    if time.monotonic() > phase_deadline:
                        raise TimeoutError("La fase de ejecución excedió el tiempo permitido")
                    rounds += 1
                    await relay_team_messages(client)

                    ready = [
                        task
                        for task in pending_tasks
                        if all(dep in completed_ids for dep in task.get("depends_on", []))
                        and task.get("status") == "pending"
                    ]

                    if not ready:
                        await asyncio.sleep(2)
                        mem = load_memory()
                        pending_tasks = [
                            task for task in mem.get("tasks", []) if task.get("status") not in ("done", "error")
                        ]
                        completed_ids = {task["id"] for task in mem.get("tasks", []) if task.get("status") == "done"}
                        continue

                    byte_tasks = [task for task in ready if task["agent"] == "byte"]
                    pixel_tasks = [task for task in ready if task["agent"] == "pixel"]

                    # GAP-8 / P8 — run up to N tasks per agent type in parallel
                    _task_kwargs = dict(
                        project_context=project_context,
                        repo_state=repo_state,
                        dry_run=args.dry_run,
                        task_timeout_sec=args.task_timeout_sec,
                        retry_attempts=args.retry_attempts,
                        retry_delay_sec=args.retry_delay_sec,
                    )
                    coros = [
                        execute_task(client, t, **_task_kwargs)
                        for t in byte_tasks[: args.max_parallel_byte]
                    ] + [
                        execute_task(client, t, **_task_kwargs)
                        for t in pixel_tasks[: args.max_parallel_pixel]
                    ]
                    if not coros and ready:
                        coros.append(execute_task(client, ready[0], **_task_kwargs))

                    await asyncio.gather(*coros)
                    await relay_team_messages(client)

                    mem = load_memory()
                    pending_tasks = [
                        task for task in mem.get("tasks", []) if task.get("status") not in ("done", "error")
                    ]
                    completed_ids = {
                        task["id"] for task in mem.get("tasks", []) if task.get("status") == "done"
                    }

                mem = load_memory()
                remaining_tasks = [task for task in mem.get("tasks", []) if task.get("status") != "done"]
                if remaining_tasks:
                    mem.setdefault("project", {})
                    mem["project"]["status"] = "in_progress"
                    mem["project"]["updated_at"] = utc_now()
                    save_memory(mem)
                    update_orchestrator_state(
                        "paused",
                        phase="execution",
                        detail=f"Quedan {len(remaining_tasks)} tarea(s) pendientes o con error",
                        dry_run=args.dry_run,
                    )
                    log_event(
                        f"Se detuvo la entrega con {len(remaining_tasks)} tarea(s) pendientes o con error; usa resume para continuar",
                        "system",
                        level="warning",
                    )
                    print("\nEjecución incompleta: quedan tareas pendientes o con error. Reanuda para continuar.")
                    return

                print("\nFase 3: Revisión final...")
                await relay_team_messages(client)
                await final_review(
                    client,
                    dry_run=args.dry_run,
                    phase_timeout_sec=args.phase_timeout_sec,
                    retry_attempts=args.retry_attempts,
                    retry_delay_sec=args.retry_delay_sec,
                )

        # P9 — webhook post-entrega
        if getattr(args, "webhook_url", None):
            try:
                import requests as _req
                _req.post(
                    args.webhook_url,
                    json=load_memory(),
                    timeout=15,
                )
                log_event(f"Webhook enviado a {args.webhook_url}", "system")
            except Exception as exc:
                log_event(f"Webhook falló (no crítico): {exc}", "system", level="warning")

        print("\nDev Squad finalizado. Revisa ./output/ para ver todos los archivos.")
        success = True
    except Exception as exc:
        if isinstance(exc, RuntimeError) and "Ya hay otro orquestador en ejecución" in str(exc):
            print(str(exc))
            return
        log_event(f"El orquestador falló: {exc}", "system", level="error")
        update_orchestrator_state("error", phase="runtime", detail=str(exc), dry_run=args.dry_run)
        raise
    finally:
        if success:
            update_orchestrator_state("idle", phase="shutdown", detail="Orquestador detenido", dry_run=args.dry_run)
        release_run_lock()


if __name__ == "__main__":
    try:
        asyncio.run(main(parse_args()))
    except RuntimeError as exc:
        print(str(exc))
