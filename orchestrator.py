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
import hashlib
import json
import os
import subprocess
import sys
import time
import shutil
import re
from uuid import uuid4
from pathlib import Path
from typing import Any

from openclaw_sdk import OpenClawClient, ProgressCallback, _infer_failure_kind, FailureKind

from coordination import (
    LOG_DIR,
    OUTPUT_DIR,
    RepositoryApprovalRequired,
    RepositoryBootstrapError,
    ProjectClarificationRequired,
    bootstrap_repository,
    build_task_skill_profile,
    commit_task_output,
    fetch_telegram_updates,
    get_telegram_credentials,
    infer_task_execution_dir,
    infer_project_structure,
    needs_planning_clarification,
    slugify,
    send_telegram_message,
    apply_session_diagnostics_to_workspace,
    finalize_repo_after_task,
    refresh_agent_workspace_files,
    write_agent_workspace_files,
    validate_project_structure,  # Fase 0
    check_existing_task_artifacts,  # Fase 3
    resolve_path,
    normalize_output_path,
    check_task_content,
    _safe_workspace_path,
    _resolve_task_artifact_path,
    _read_text_if_exists,
    _task_files_for_review,
)
from shared_state import (
    BASE_DIR,
    ensure_memory_file,
    load_memory,
    refresh_project_runtime_state,
    save_memory,
    _pid_is_alive,
)
from skills.shared.miniverse_bridge import get_bridge

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
DEFAULT_TELEGRAM_POLL_INTERVAL_SEC = 20
MAX_REVIEW_ROUNDS = 2

# Labels shown in Telegram/logs for each progress classification.
_PROGRESS_EMOJI = {
    "tool_use": "\u2699\ufe0f",   # ⚙️
    "thinking": "\U0001f9e0",     # 🧠
    "writing": "\u270d\ufe0f",    # ✍️
    "reading": "\U0001f50d",      # 🔍
    "working": "\U0001f527",      # 🔧
    "done": "\u2705",             # ✅
}


# ---------------------------------------------------------------------------
# Prompts (Externalized)
# ---------------------------------------------------------------------------


def load_prompt(name: str) -> str:
    """Load a prompt from the prompts/ directory."""
    path = BASE_DIR / "prompts" / name
    if not path.exists():
        return f"MISSING_PROMPT: {name} (Expected at {path})"
    return path.read_text(encoding="utf-8").strip()


PLANNER_PROMPT = load_prompt("planner.md")
COORDINATION_PROMPT = load_prompt("coordination.md")
BYTE_TASK_PROMPT = load_prompt("byte.md")
PIXEL_TASK_PROMPT = load_prompt("pixel.md")
REVIEW_PROMPT = load_prompt("review.md")


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()


def _stable_session_id(*parts: str) -> str:
    cleaned = [slugify(p or "")[:24] for p in parts if p]
    base = "-".join(part for part in cleaned if part).strip("-")
    digest = hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest()[:12]
    if base:
        return f"{base}-{digest}"
    return f"session-{digest}"


def _is_valid_session_id(value: str | None) -> bool:
    if not value:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_-]+", value))


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



# (Path helpers moved to coordination.py)


def _normalize_task_output(data: dict[str, Any], *, agent_id: str, task_id: str) -> tuple[list[dict[str, str]], str]:
    """Validate the JSON returned by a task agent before writing files."""
    files = data.get("files")
    if not isinstance(files, list):
        raise ValueError("La respuesta JSON no incluye una lista válida de archivos")

    normalized_files: list[dict[str, str]] = []
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise ValueError(f"El archivo #{index + 1} no es un objeto JSON válido")
        path = item.get("path")
        content = item.get("content")
        if not isinstance(path, str) or not path.strip():
            raise ValueError(f"El archivo #{index + 1} no tiene una ruta válida")
        if not isinstance(content, str):
            raise ValueError(f"El archivo #{index + 1} no tiene contenido de texto válido")
        normalized_files.append({"path": Path(path).as_posix(), "content": content})

    notes = data.get("notes", "")
    if notes is None:
        notes = ""
    elif not isinstance(notes, str):
        notes = str(notes)

    if not normalized_files:
        note_upper = notes.upper()
        if "BLOCKER:" in note_upper or "QUESTION:" in note_upper:
            raise TaskOutputBlocked(notes.strip() or f"BLOCKER:{task_id} bloqueo sin detalle")
        raise ValueError(
            f"{agent_id.upper()} devolvió JSON válido sin archivos para {task_id}; "
            "la tarea no puede marcarse como completada"
        )

    return normalized_files, notes


class TaskOutputBlocked(ValueError):
    """Task agent reported a BLOCKER/QUESTION with valid JSON but no files."""


# (_classify_task_failure delegado a _infer_failure_kind del SDK)


def _sync_project_status(mem: dict[str, Any]) -> None:
    """Keep the project status aligned with the task graph."""
    project = mem.setdefault("project", {})
    if project.get("status") == "delivered":
        return

    tasks = [task for task in mem.get("tasks", []) if isinstance(task, dict)]
    if not tasks:
        return

    if any(task.get("status") == "error" for task in tasks):
        project["status"] = "blocked"
    elif any(task.get("status") in {"pending", "in_progress"} for task in tasks):
        project["status"] = "in_progress"
    else:
        project["status"] = "in_progress"
    project["updated_at"] = utc_now()


def _task_files_for_manifest(task: dict[str, Any]) -> list[str]:
    files: list[str] = []
    project = load_memory().get("project", {}) or {}
    for raw_path in task.get("files", []) or []:
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        candidate = _resolve_task_artifact_path(raw_path, project)
        if candidate is not None:
            files.append(normalize_output_path(candidate))
    return files


def _synchronize_project_artifacts(mem: dict[str, Any]) -> None:
    """Write a consolidated project manifest and index for the dashboard."""
    project = mem.setdefault("project", {})
    output_dir = resolve_path(project.get("output_dir"), OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    tasks = [task for task in mem.get("tasks", []) if isinstance(task, dict)]
    task_entries: list[dict[str, Any]] = []
    file_entries: list[dict[str, Any]] = []

    for task in tasks:
        task_files = _task_files_for_manifest(task)
        task_entries.append(
            {
                "id": task.get("id"),
                "title": task.get("title"),
                "agent": task.get("agent"),
                "status": task.get("status"),
                "skill_family": task.get("skill_family"),
                "failure_count": task.get("failure_count", 0),
                "next_action": task.get("next_action"),
                "files": task_files,
                "notes": task.get("notes"),
            }
        )
        for path in task_files:
            file_entries.append(
                {
                    "task_id": task.get("id"),
                    "agent": task.get("agent"),
                    "path": path,
                }
            )

    manifest = {
        "project": {
            "id": project.get("id"),
            "name": project.get("name"),
            "status": project.get("status"),
            "runtime_status": project.get("runtime_status"),
            "repo_path": project.get("repo_path"),
            "output_dir": project.get("output_dir"),
            "branch": project.get("branch"),
            "updated_at": project.get("updated_at"),
        },
        "generated_at": utc_now(),
        "task_count": len(task_entries),
        "file_count": len(file_entries),
        "tasks": task_entries,
        "files": file_entries,
    }

    manifest_path = output_dir / "PROJECT_MANIFEST.json"
    index_path = output_dir / "PROJECT_INDEX.md"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"# {project.get('name') or project.get('id') or 'Project'}",
        "",
        f"- Project ID: {project.get('id') or 'N/A'}",
        f"- Runtime status: {project.get('runtime_status') or project.get('status') or 'idle'}",
        f"- Tasks: {len(task_entries)}",
        f"- Files: {len(file_entries)}",
        "",
        "## Task Map",
        "",
    ]
    for entry in task_entries:
        lines.append(f"### {entry['id']} - {entry['title'] or 'Sin título'}")
        lines.append(f"- Agent: {entry.get('agent') or 'N/A'}")
        lines.append(f"- Status: {entry.get('status') or 'N/A'}")
        if entry.get("skill_family"):
            lines.append(f"- Skill family: {entry.get('skill_family')}")
        if entry.get("next_action"):
            lines.append(f"- Next action: {entry.get('next_action')}")
        if entry.get("files"):
            lines.append("- Files:")
            for path in entry["files"]:
                lines.append(f"  - {path}")
        else:
            lines.append("- Files: none")
        lines.append("")

    if file_entries:
        lines.extend(["## Unified Files", ""])
        for item in file_entries:
            lines.append(f"- {item['path']}  ({item.get('task_id')})")
    else:
        lines.extend(["## Unified Files", "", "- No files produced yet."])

    index_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    project["artifact_manifest"] = str(manifest_path)
    project["artifact_index"] = str(index_path)
    project["artifacts_updated_at"] = utc_now()
    project["artifact_file_count"] = len(file_entries)
    project["artifact_task_count"] = len(task_entries)
    refresh_project_runtime_state(mem)
    save_memory(mem)


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
    refresh_project_runtime_state(mem)
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
    refresh_project_runtime_state(mem)
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
) -> dict[str, Any]:
    """Store a blocker in shared memory."""
    entry = {
        "id": f"blk-{abs(hash((source, task_id, agent_id, message, utc_now()))) % 1_000_000}",
        "ts": utc_now(),
        "source": source,
        "msg": message,
        "task_id": task_id,
        "agent_id": agent_id,
        "retryable": retryable,
    }
    mem = load_memory()
    mem.setdefault("blockers", [])
    mem["blockers"].append(entry)
    refresh_project_runtime_state(mem)
    save_memory(mem)
    return entry


def _has_open_tasks(tasks: list[dict[str, Any]]) -> bool:
    return any(task.get("status") != "done" for task in tasks if isinstance(task, dict))


def _has_tasks_needing_correction(tasks: list[dict[str, Any]]) -> bool:
    return any(task.get("review_status") == "needs_correction" for task in tasks if isinstance(task, dict))


def _fallback_agent_for(task: dict[str, Any], agent_id: str) -> str | None:
    family = str(task.get("skill_family") or "").lower()
    if agent_id == "pixel" and family in {"vanilla-frontend", "frontend"}:
        return "byte"
    return None


# (Task file collection helpers moved to coordination.py)


# (Validation helpers moved to coordination.py)


def _task_matches_acceptance(task: dict[str, Any], project: dict[str, Any]) -> tuple[bool, list[str]]:
    """Lightweight final validation to catch obvious mismatches before delivery."""
    acceptance = [str(item).lower() for item in (task.get("acceptance") or []) if isinstance(item, str)]
    notes = [str(task.get("notes") or "").lower(), str(task.get("raw_response") or "").lower()]
    files = [str(path).lower() for path in _task_files_for_review(task, project)]
    observations: list[str] = []

    if not files:
        observations.append(f"{task.get('id')}: sin archivos escritos")

    for requirement in acceptance:
        if "backend/" in requirement and not any("backend/" in f for f in files):
            observations.append("falta backend/")
        if "requirements.txt" in requirement and not any("requirements.txt" in f for f in files):
            observations.append("falta requirements.txt")
        if "main.py" in requirement and not any("main.py" in f for f in files):
            observations.append("falta main.py")
        if "database.py" in requirement and not any("database.py" in f for f in files):
            observations.append("falta database.py")
        if "models/" in requirement and not any("models/" in f for f in files):
            observations.append("falta models/")
        if "schemas/" in requirement and not any("schemas/" in f for f in files):
            observations.append("falta schemas/")
        if "routes/" in requirement and not any("routes/" in f for f in files):
            observations.append("falta routes/")

    if any(re.search(r"\b(todo|placeholder|ok)\b", note) for note in notes if note):
        observations.append("notes/resultado demasiado genérico")

    # Content-specific checks (externalized to coordination.py)
    observations.extend(check_task_content(task, project))

    # Phase 3 Structure Validation: ensure written files match execution rules
    execution_dir = str(task.get("execution_dir") or "")
    if files:
        structure_violations = validate_project_structure(execution_dir, project, task, files_written=files)
        observations.extend(structure_violations)

    return (not observations, observations)


def _record_task_review(task_id: str, review_round: int, issues: list[str]) -> None:
    mem = load_memory()
    for task in mem.get("tasks", []):
        if task.get("id") != task_id:
            continue
        task["review_round"] = review_round
        task["review_issues"] = issues
        task["review_status"] = "needs_correction" if issues else "passed"
        task["updated_at"] = utc_now()
    refresh_project_runtime_state(mem)
    save_memory(mem)


def _proposal_id(kind: str, task_id: str, title: str) -> str:
    return f"prop-{kind}-{abs(hash((kind, task_id, title, utc_now()))) % 1_000_000}"


def propose_follow_up_task(
    *,
    title: str,
    description: str,
    rationale: str,
    agent: str,
    kind: str = "improvement",
    execution_dir: str | None = None,
    acceptance: list[str] | None = None,
) -> dict[str, Any]:
    """Store a proposed follow-up task that can later be approved into the queue."""
    mem = load_memory()
    proposal = {
        "id": _proposal_id(kind, agent, title),
        "ts": utc_now(),
        "kind": kind,
        "status": "proposed",
        "agent": agent,
        "title": title,
        "description": description,
        "rationale": rationale,
        "execution_dir": execution_dir,
        "acceptance": acceptance or [],
    }
    mem.setdefault("proposals", [])
    mem["proposals"].append(proposal)
    refresh_project_runtime_state(mem)
    save_memory(mem)
    return proposal


def approve_proposal(proposal_id: str) -> dict[str, Any] | None:
    """Convert a proposed follow-up into a queued task in the current project."""
    mem = load_memory()
    project = mem.get("project", {}) or {}
    tasks = mem.get("tasks", []) if isinstance(mem.get("tasks", []), list) else []
    proposals = mem.get("proposals", []) if isinstance(mem.get("proposals", []), list) else []

    proposal = next((p for p in proposals if isinstance(p, dict) and p.get("id") == proposal_id), None)
    if not proposal:
        return None

    existing_ids = {str(task.get("id")) for task in tasks if isinstance(task, dict)}
    next_num = 1
    while f"T-{next_num:03d}" in existing_ids:
        next_num += 1
    task_id = f"T-{next_num:03d}"

    new_task = {
        "id": task_id,
        "agent": proposal.get("agent") or "byte",
        "title": proposal.get("title"),
        "description": proposal.get("description"),
        "acceptance": proposal.get("acceptance") or [],
        "depends_on": [],
        "skills": [],
        "workspace_notes": [],
        "phase": "follow-up",
        "status": "pending",
        "skill_family": "general",
        "skill_profile": build_task_skill_profile(project, {
            "agent": proposal.get("agent") or "byte",
            "title": proposal.get("title"),
            "description": proposal.get("description"),
            "acceptance": proposal.get("acceptance") or [],
        }),
        "execution_dir": proposal.get("execution_dir") or infer_task_execution_dir(project, proposal, mem.get("repo_state") or {}),
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "source_proposal_id": proposal_id,
    }
    new_task["skill_family"] = new_task["skill_profile"]["family"]
    new_task["skills"] = new_task["skill_profile"]["skills"]
    new_task["workspace_notes"] = new_task["skill_profile"]["instructions"]

    tasks.append(new_task)
    mem["tasks"] = tasks
    mem["proposals"] = [p for p in proposals if p.get("id") != proposal_id]
    mem.setdefault("milestones", [])
    mem["milestones"].append(f"Propuesta aprobada y encolada: {task_id}")
    refresh_project_runtime_state(mem)
    save_memory(mem)
    return new_task


def _notify_proposal_by_telegram(proposal: dict[str, Any]) -> None:
    message = "\n".join(
        [
            f"Propuesta: {proposal.get('title')}",
            f"Agente: {proposal.get('agent')}",
            f"Motivo: {proposal.get('rationale')}",
            f"ID: {proposal.get('id')}",
            "Responde APROBAR <ID> para encolarla como nueva tarea.",
        ]
    )
    send_telegram_message(message)


def _append_proposal_to_memory(proposal: dict[str, Any]) -> None:
    mem = load_memory()
    mem.setdefault("proposals", [])
    mem["proposals"].append(proposal)
    refresh_project_runtime_state(mem)
    save_memory(mem)


def _telegram_task_summary(task: dict[str, Any], *, status: str, issues: list[str] | None = None) -> str:
    files = task.get("files", []) or []
    summary_lines = [
        f"Tarea {task.get('id')} ({task.get('agent')}) {status}",
        f"Título: {task.get('title')}",
        f"Archivos: {len(files)}",
    ]
    if issues:
        summary_lines.append("Revisión: " + "; ".join(issues[:4]))
    notes = str(task.get("notes") or "").strip()
    if notes:
        summary_lines.append(f"Notas: {notes[:260]}")
    return "\n".join(summary_lines)


def _telegram_project_summary(mem: dict[str, Any]) -> str:
    project = mem.get("project", {}) if isinstance(mem, dict) else {}
    counts = project.get("task_counts", {}) if isinstance(project, dict) else {}
    issues = []
    for task in mem.get("tasks", []) or []:
        if not isinstance(task, dict):
            continue
        if task.get("review_status") == "needs_correction":
            issues.extend(task.get("review_issues", []) or [])
    lines = [
        f"Proyecto: {project.get('name') or 'sin nombre'}",
        f"Estado: {project.get('status') or 'idle'}",
        f"Done/Open/Error: {counts.get('done', 0)}/{counts.get('open', 0)}/{counts.get('error', 0)}",
    ]
    if issues:
        lines.append("Revisión: " + "; ".join(issues[:5]))
    if project.get("repo_path"):
        lines.append(f"Repo: {project.get('repo_path')}")
    return "\n".join(lines)


def _active_task_for_agent(mem: dict[str, Any], agent_id: str) -> dict[str, Any] | None:
    """Return the most relevant unfinished task currently assigned to *agent_id*."""
    tasks = mem.get("tasks", []) if isinstance(mem.get("tasks", []), list) else []
    for task in reversed(tasks):
        if not isinstance(task, dict):
            continue
        if task.get("agent") != agent_id:
            continue
        if task.get("status") in {"done", "delivered"}:
            continue
        return task
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
    project["project_structure"] = infer_project_structure(project, {})

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
        decoder = json.JSONDecoder()
        for idx, ch in enumerate(text):
            if ch not in "[{":
                continue
            try:
                obj, _end = decoder.raw_decode(text[idx:])
                return obj
            except json.JSONDecodeError:
                continue
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
            "execution_dir": task.get("execution_dir"),
        }
        for task in mem.get("tasks", [])
    }
    context = {
        "project": mem.get("project", {}),
        "repo": repo_state,
        "milestones": mem.get("milestones", []),
        "task_skill_map": task_skill_map,
        "output_dir": mem.get("project", {}).get("output_dir", "./output"),
        "execution_dir_map": {
            task.get("id"): task.get("execution_dir")
            for task in mem.get("tasks", [])
            if isinstance(task, dict) and task.get("id")
        },
    }
    return json.dumps(context, indent=2, ensure_ascii=False)


def _telegram_orchestrator_state(mem: dict[str, Any]) -> dict[str, Any]:
    project = mem.setdefault("project", {})
    orchestrator = project.setdefault("orchestrator", {})
    return orchestrator.setdefault("telegram", {})


# ── Fase 1: Helpers de aclaración de planificacion ────────────────────────

def _clarification_pending(mem: dict[str, Any]) -> dict[str, Any] | None:
    """Return pending clarification metadata from MEMORY, or None."""
    return mem.get("project", {}).get("pending_clarification") or None


def _save_clarification_pending(
    mem: dict[str, Any],
    *,
    questions: list[str],
    brief: str,
    sent_at: str,
) -> None:
    """Persist clarification state in MEMORY so the orchestrator does not
    re-send the same question if it restarts."""
    mem.setdefault("project", {})["pending_clarification"] = {
        "questions": questions,
        "original_brief": brief,
        "sent_at": sent_at,
        "reply": None,
        "resolved": False,
    }


def _consume_clarification_reply(mem: dict[str, Any]) -> str | None:
    """Read and clear the user reply from a pending clarification.

    Returns the reply text if available, or None if not yet answered.
    Side-effect: marks the clarification as resolved and removes
    `pending_clarification` from the project dict.
    """
    clarification = mem.get("project", {}).get("pending_clarification")
    if not isinstance(clarification, dict):
        return None
    reply = clarification.get("reply")
    if not reply:
        return None
    # consume it: remove the block so it is not replayed
    mem.get("project", {}).pop("pending_clarification", None)
    return str(reply).strip() or None


# ---------------------------------------------------------------------------

def _telegram_chat_id_matches(incoming_chat_id: Any) -> bool:
    _token, configured_chat_id = get_telegram_credentials()
    if not configured_chat_id:
        return True
    return str(incoming_chat_id) == str(configured_chat_id)


def _telegram_message_summary(mem: dict[str, Any]) -> str:
    project = mem.get("project", {}) if isinstance(mem, dict) else {}
    counts = project.get("task_counts", {}) if isinstance(project, dict) else {}
    parts = [
        f"Proyecto: {project.get('name') or 'sin nombre'}",
        f"Estado: {project.get('status') or 'idle'}",
        f"Runtime: {project.get('runtime_status') or 'idle'}",
        f"Orquestador: {project.get('orchestrator', {}).get('status') or 'idle'}",
        f"Tareas: {counts.get('done', 0)} done / {counts.get('open', 0)} open / {counts.get('error', 0)} error",
    ]
    if project.get("blocked_reason"):
        parts.append(f"Bloqueo: {project.get('blocked_reason')}")
    if project.get("repo_path"):
        parts.append(f"Repo: {project.get('repo_path')}")
    return "\n".join(parts)


def _telegram_help_message() -> str:
    return (
        "Comandos disponibles:\n"
        "/status - resumen del proyecto\n"
        "/help - muestra esta ayuda\n"
        "Cualquier otro texto se entrega al coordinador como mensaje para ARCH."
    )


async def _poll_telegram_inbox() -> None:
    """Fetch Telegram messages and persist them as coordinator inbox entries."""
    token, chat_id = get_telegram_credentials()
    if not token:
        return

    mem = load_memory()
    telegram_state = _telegram_orchestrator_state(mem)
    offset = telegram_state.get("update_offset")
    try:
        offset_int = int(offset) if offset is not None else None
    except Exception:
        offset_int = None

    result = fetch_telegram_updates(offset=offset_int, timeout=20, limit=50, token=token)
    if not result.get("ok"):
        reason = result.get("reason")
        if reason:
            log_event(f"Telegram polling failed: {reason}", "system", level="warning")
        return

    updates = result.get("updates", [])
    if not updates:
        return

    existing_ids = {m.get("id", "") for m in mem.get("messages", [])}
    seen_updates: list[int] = []
    for update in updates:
        if not isinstance(update, dict):
            continue
        update_id = update.get("update_id")
        try:
            update_id_int = int(update_id)
        except Exception:
            continue
        seen_updates.append(update_id_int)

        message = update.get("message") or update.get("edited_message") or update.get("channel_post")
        if not isinstance(message, dict):
            continue
        text = message.get("text") or message.get("caption") or ""
        if not isinstance(text, str):
            text = str(text)
        text = text.strip()
        if not text:
            continue

        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        incoming_chat_id = chat.get("id") if isinstance(chat, dict) else None
        if not _telegram_chat_id_matches(incoming_chat_id):
            continue

        normalized = {
            "id": f"telegram-{update_id_int}",
            "from": "telegram",
            "to": "arch",
            "message": text,
            "raw": update,
            "received_at": utc_now(),
            "source": "telegram",
            "relay_status": "pending",
            "chat_id": str(incoming_chat_id) if incoming_chat_id is not None else None,
            "update_id": update_id_int,
        }

        if normalized["id"] not in existing_ids:
            existing_ids.add(normalized["id"])
            upper = text.upper()
            if upper.startswith("/STATUS"):
                normalized["relay_status"] = "handled"
                mem.setdefault("messages", [])
                mem["messages"].append(normalized)
                log_event(f"Telegram command /status received: {text}", "telegram")
                try:
                    send_telegram_message(_telegram_message_summary(mem))
                except Exception as exc:
                    log_event(f"Telegram status reply failed: {exc}", "system", level="warning")
                continue
            elif upper.startswith("/HELP"):
                normalized["relay_status"] = "handled"
                mem.setdefault("messages", [])
                mem["messages"].append(normalized)
                log_event(f"Telegram command /help received: {text}", "telegram")
                try:
                    send_telegram_message(_telegram_help_message())
                except Exception as exc:
                    log_event(f"Telegram help reply failed: {exc}", "system", level="warning")
                continue
            elif upper.startswith("/PAUSE"):
                normalized["relay_status"] = "handled"
                mem.setdefault("messages", [])
                mem["messages"].append(normalized)
                telegram_state["control_request"] = "pause"
                log_event(f"Telegram command /pause received: {text}", "telegram")
                try:
                    send_telegram_message("Pausa solicitada por Telegram. Se aplicará en el siguiente ciclo.")
                except Exception as exc:
                    log_event(f"Telegram pause ack failed: {exc}", "system", level="warning")
                continue
            elif upper.startswith("/RESUME"):
                normalized["relay_status"] = "handled"
                mem.setdefault("messages", [])
                mem["messages"].append(normalized)
                log_event(f"Telegram command /resume received: {text}", "telegram")
                try:
                    send_telegram_message("Reanudación solicitada por Telegram. Usa /devsquad o /api/project/resume para aplicarla.")
                except Exception as exc:
                    log_event(f"Telegram resume ack failed: {exc}", "system", level="warning")
                continue
            elif upper.startswith("APROBAR "):
                normalized["relay_status"] = "handled"
                mem.setdefault("messages", [])
                mem["messages"].append(normalized)
                proposal_id = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
                if not proposal_id:
                    try:
                        send_telegram_message("Uso: APROBAR <proposal_id>")
                    except Exception as exc:
                        log_event(f"Telegram approve usage reply failed: {exc}", "system", level="warning")
                    continue
                approved_task = approve_proposal(proposal_id)
                if not approved_task:
                    try:
                        send_telegram_message(f"No se encontró la propuesta {proposal_id}")
                    except Exception as exc:
                        log_event(f"Telegram approve miss reply failed: {exc}", "system", level="warning")
                    continue
                log_event(f"Telegram aprobó {proposal_id} -> {approved_task.get('id')}", "telegram")
                try:
                    send_telegram_message(
                        "\n".join(
                            [
                                f"Propuesta aprobada: {proposal_id}",
                                f"Nueva tarea en cola: {approved_task.get('id')} ({approved_task.get('agent')})",
                                f"Directorio: {approved_task.get('execution_dir') or 'n/a'}",
                            ]
                        )
                    )
                except Exception as exc:
                    log_event(f"Telegram approve ack failed: {exc}", "system", level="warning")
                continue
            elif upper.startswith("/ACLARAR ") or upper.startswith("ACLARAR "):
                # Fase 1: el usuario responde a una pregunta de planificacion pendiente
                clarification_text = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else text.strip()
                normalized["relay_status"] = "handled"
                normalized["kind"] = "clarification_reply"
                mem.setdefault("messages", [])
                mem["messages"].append(normalized)

                # guardar la respuesta en el bloque pending_clarification
                pending = mem.get("project", {}).get("pending_clarification")
                if isinstance(pending, dict) and not pending.get("resolved"):
                    pending["reply"] = clarification_text
                    pending["resolved"] = True
                    pending["replied_at"] = utc_now()
                    mem.setdefault("project", {})["status"] = "pending"
                    mem["project"]["bootstrap_status"] = "clarification_received"
                    log_event(
                        f"[Fase 1] Aclaración recibida por Telegram: {clarification_text[:120]}",
                        "telegram",
                    )
                    try:
                        send_telegram_message(
                            f"✅ Aclaración registrada. ARCH reanudará la planificación en el siguiente ciclo.\n"
                            f"Respuesta recibida: {clarification_text[:120]}"
                        )
                    except Exception as exc:
                        log_event(f"Telegram clarification ack failed: {exc}", "system", level="warning")
                else:
                    log_event(
                        "[Fase 1] Respuesta /ACLARAR recibida pero no había pregunta pendiente",
                        "telegram",
                        level="warning",
                    )
                    try:
                        send_telegram_message(
                            "No hay ninguna pregunta de planificación pendiente. "
                            "Para iniciar un proyecto escribe directamente el brief."
                        )
                    except Exception:
                        pass
                continue
            else:
                mem.setdefault("messages", [])
                mem["messages"].append(normalized)
                log_event(f"Telegram -> coordinator: {text}", "telegram")
                # Fase 1: si hay un pending_clarification sin reply, tratar mensaje libre como respuesta
                pending = mem.get("project", {}).get("pending_clarification")
                if isinstance(pending, dict) and not pending.get("reply") and not upper.startswith("/"):
                    pending["reply"] = text
                    pending["resolved"] = True
                    pending["replied_at"] = utc_now()
                    mem.setdefault("project", {})["status"] = "pending"
                    mem["project"]["bootstrap_status"] = "clarification_received"
                    log_event(
                        f"[Fase 1] Mensaje libre interpretado como aclaración: {text[:120]}",
                        "telegram",
                    )
                    try:
                        send_telegram_message(
                            f"✅ Respuesta registrada como aclaración de planificación.\n"
                            f"ARCH reanudará en el siguiente ciclo.\nRespuesta: {text[:120]}"
                        )
                    except Exception:
                        pass
                else:
                    try:
                        send_telegram_message("Mensaje recibido. ARCH lo revisará en el siguiente ciclo.")
                    except Exception as exc:
                        log_event(f"Telegram ack failed: {exc}", "system", level="warning")

    if seen_updates:
        telegram_state["update_offset"] = max(seen_updates) + 1
    save_memory(mem)


def _consume_telegram_control_request() -> str | None:
    mem = load_memory()
    telegram_state = _telegram_orchestrator_state(mem)
    request = str(telegram_state.get("control_request") or "").strip().lower()
    if request:
        telegram_state.pop("control_request", None)
        save_memory(mem)
        return request
    return None


async def relay_team_messages(client: OpenClawClient) -> None:
    """Drain team inboxes, update memory, and let ARCH answer blockers."""
    await _poll_telegram_inbox()
    bridges = {agent_id: get_bridge(agent_id) for agent_id in AGENT_IDS}
    mem = load_memory()
    existing_message_ids: set[str] = {m.get("id", "") for m in mem.get("messages", [])}
    arch_messages: list[dict[str, Any]] = []
    telegram_pending_ids: list[str] = []

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
            if "BLOCKER:" in message_upper or "QUESTION:" in message_upper:
                is_question = "QUESTION:" in message_upper
                issue_type = "QUESTION" if is_question else "BLOCKER"
                current_task = _active_task_for_agent(mem, normalized.get("from") or agent_id)
                blocker_entry = record_blocker(
                    normalized["message"],
                    normalized["from"],
                    task_id=normalized.get("task_id"),
                    agent_id=normalized.get("from"),
                    retryable=True,
                )
                mem.setdefault("blockers", [])
                if blocker_entry not in mem["blockers"]:
                    mem["blockers"].append(blocker_entry)
                if current_task:
                    try:
                        project = mem.get("project", {}) or {}
                        skill_profile = current_task.get("skill_profile") or mem.get("skill_profile") or {}
                        repo_state = mem.get("repo_state") or {
                            "repo_path": project.get("repo_path") or project.get("output_dir"),
                            "branch": project.get("branch"),
                            "repo_url": project.get("repo_url"),
                            "repo_name": project.get("name"),
                        }
                        refresh_agent_workspace_files(
                            normalized.get("from") or agent_id,
                            current_task,
                            project,
                            skill_profile,
                            repo_state,
                            question=normalized["message"] if is_question else None,
                        )
                    except Exception as exc:
                        log_event(f"No se pudo refrescar el workspace tras BLOCKER/QUESTION: {exc}", "system", level="warning")
                arch_messages.append(
                    {
                        "id": f"{issue_type.lower()}-{blocker_entry['id']}",
                        "from": normalized["from"],
                        "to": "arch",
                        "message": f"{issue_type}:{normalized.get('task_id') or 'unknown'} {normalized['message']}",
                        "received_at": normalized.get("received_at") or utc_now(),
                        "raw": normalized,
                    }
                )
                try:
                    send_telegram_message(
                        f"{issue_type} de {normalized['from']}: {normalized['message']}"
                    )
                except Exception as exc:
                    log_event(f"Falló la notificación por Telegram: {exc}", "system")

            if agent_id == "arch" and normalized["from"] in {"byte", "pixel"}:
                arch_messages.append(normalized)

    for message in mem.get("messages", []) or []:
        if not isinstance(message, dict):
            continue
        if message.get("source") != "telegram" or message.get("relay_status") != "pending":
            continue
        message_id = message.get("id")
        if not isinstance(message_id, str) or not message_id:
            continue
        arch_messages.append(
            {
                "id": message_id,
                "from": "telegram",
                "to": "arch",
                "message": message.get("message") or "",
                "received_at": message.get("received_at") or utc_now(),
                "raw": message,
            }
        )
        telegram_pending_ids.append(message_id)

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
        try:
            current_task = _active_task_for_agent(mem, target)
            if current_task:
                project = mem.get("project", {}) or {}
                skill_profile = current_task.get("skill_profile") or mem.get("skill_profile") or {}
                repo_state = mem.get("repo_state") or {
                    "repo_path": project.get("repo_path") or project.get("output_dir"),
                    "branch": project.get("branch"),
                    "repo_url": project.get("repo_url"),
                    "repo_name": project.get("name"),
                }
                refresh_agent_workspace_files(
                    target,
                    current_task,
                    project,
                    skill_profile,
                    repo_state,
                    reply=message,
                )
        except Exception as exc:
            log_event(f"No se pudo registrar la respuesta de ARCH en el workspace: {exc}", "system", level="warning")
        log_event(f"ARCH -> {target}: {message}", "arch")

    if telegram_pending_ids:
        mem = load_memory()
        for message in mem.get("messages", []) or []:
            if not isinstance(message, dict):
                continue
            if message.get("id") in telegram_pending_ids:
                message["relay_status"] = "sent"
                message["relayed_at"] = utc_now()
        save_memory(mem)


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

# (Prompts externalized to prompts/*.md)


def _format_planning_clarification_message(brief: str, questions: list[str], structure: dict[str, Any]) -> str:
    lines = [
        "Se requiere aclaración antes de planificar el proyecto.",
        f"Brief: {brief}",
        "",
        "Preguntas:",
    ]
    lines.extend(f"- {question}" for question in questions)
    layout_kind = structure.get("kind") or "n/a"
    layout_root = structure.get("root") or "n/a"
    layout_entry = structure.get("entrypoint") or "n/a"
    lines.extend(
        [
            "",
            f"Tipo detectado: {layout_kind}",
            f"Raíz sugerida: {layout_root}",
            f"Punto de entrada sugerido: {layout_entry}",
            "",
            "Responde por Telegram con la aclaración concreta. ARCH reanudará la planificación cuando esté disponible.",
        ]
    )
    return "\n".join(lines)


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

    if not dry_run:
        # \u2500\u2500 Fase 1: anti-loop + consumo de respuesta \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        mem_pre = load_memory()
        clarification_reply = _consume_clarification_reply(mem_pre)
        if clarification_reply:
            save_memory(mem_pre)
            brief = f"{brief}\n\n[Aclaraci\u00f3n del usuario]: {clarification_reply}"
            log_event(
                f"[Fase 1] Brief enriquecido con la aclaraci\u00f3n del usuario: {clarification_reply[:120]}",
                "arch",
            )

        clarification_questions = needs_planning_clarification(brief)
        if clarification_questions:
            existing_clarification = _clarification_pending(mem_pre)
            already_sent = (
                isinstance(existing_clarification, dict)
                and not existing_clarification.get("resolved")
                and existing_clarification.get("original_brief", "") == brief.split("\n\n[Aclaraci\u00f3n")[0]
            )

            clarification_project = {
                "name": brief[:60].strip() or "Project",
                "description": brief,
                "tech_stack": infer_tech_stack_from_brief(brief),
            }
            clarification_structure = infer_project_structure(clarification_project, {})
            clarification_message = _format_planning_clarification_message(
                brief,
                clarification_questions,
                clarification_structure,
            )

            if not already_sent:
                try:
                    send_telegram_message(clarification_message)
                    log_event("[Fase 1] Pregunta de aclaraci\u00f3n enviada por Telegram", "arch")
                except Exception as exc:
                    log_event(f"No se pudo enviar la aclaraci\u00f3n por Telegram: {exc}", "system", level="warning")
                _save_clarification_pending(
                    mem_pre,
                    questions=clarification_questions,
                    brief=brief.split("\n\n[Aclaraci\u00f3n")[0],
                    sent_at=utc_now(),
                )
                save_memory(mem_pre)
                log_event("[Fase 1] Estado de aclaraci\u00f3n guardado en MEMORY (anti-loop)", "arch")
            else:
                log_event(
                    "[Fase 1] Ya se envi\u00f3 la pregunta. Esperando respuesta del usuario.",
                    "arch",
                    level="warning",
                )

            update_agent_status("arch", "blocked", "awaiting_clarification")
            update_orchestrator_state(
                "blocked",
                phase="planning",
                detail="A la espera de aclaraci\u00f3n de alcance por Telegram",
                dry_run=dry_run,
            )
            raise ProjectClarificationRequired(
                clarification_message,
                questions=clarification_questions,
                project_brief=brief,
                project_structure=clarification_structure,
            )
        # \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

    if dry_run:
        plan_json = build_dry_run_plan(brief)
    else:
        if client is None:
            raise RuntimeError("Se requiere un cliente OpenClaw fuera del modo dry-run")
        arch = client.get_agent("arch")
        progress_cb = make_progress_callback(notify_telegram=True, telegram_throttle_sec=30.0)
        planner_prompt = PLANNER_PROMPT.format(project_brief=brief)
        planner_session_id = _stable_session_id("arch", "planning", brief)
        result = await retry_async(
            "Planner execution",
            lambda: arch.execute(
                planner_prompt,
                on_progress=progress_cb,
                session_id=planner_session_id,
                thinking="medium",
            ),
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
    # Start each planned project with a clean runtime surface so prior runs do
    # not leak progress files, proposals, or artifact metadata into the new run.
    mem["tasks"] = []
    mem["blockers"] = []
    mem["proposals"] = []
    mem["milestones"] = []
    mem["files_produced"] = []
    mem["progress_files"] = []
    project_patch = plan_json.get("project", {})
    mem.setdefault("project", {})
    project_structure = project_patch.get("project_structure") or infer_project_structure(
        {
            "name": project_patch.get("name") or mem["project"].get("name"),
            "description": project_patch.get("description") or mem["project"].get("description") or brief,
            "tech_stack": project_patch.get("tech_stack") or mem["project"].get("tech_stack", {}),
            "repo_path": mem["project"].get("repo_path"),
            "output_dir": mem["project"].get("output_dir"),
        },
        {},
    )
    mem["project"].update(
        {
            **project_patch,
            "id": project_patch.get("id") or _ensure_project_id(project_patch),
            "status": "planned",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "project_structure": project_structure,
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
            task["execution_dir"] = infer_task_execution_dir(mem["project"], task, repo_state=None)
            task["skill_family"] = profile["family"]
            task["skill_profile"] = profile
            task["skills"] = profile["skills"]
            task["workspace_notes"] = profile["instructions"]
            task_skill_summary[task["id"]] = profile["skills"]
            all_tasks.append(task)

    mem["tasks"] = all_tasks
    mem["project"]["task_skill_summary"] = task_skill_summary
    refresh_project_runtime_state(mem)
    save_memory(mem)

    arch_bridge.speak(
        f"Plan listo. {len(all_tasks)} tareas en {len(mem['plan'].get('phases', []))} fases."
    )
    log_event(f"Plan creado: {len(all_tasks)} tareas", "arch")
    update_agent_status("arch", "idle", None)
    update_orchestrator_state("planned", phase="planning", detail=f"{len(all_tasks)} tareas planificadas", dry_run=dry_run)
    return plan_json


# ── Phase 2: Execution ─────────────────────────────────────────────────────────


# ---------------------------------------------------------------------------
# execute_task — Auxiliary helpers (extracted for readability)
# ---------------------------------------------------------------------------


def _dry_run_data(task_id: str, agent_id: str, skill_profile: dict[str, Any]) -> dict[str, Any]:
    """Return a synthetic task payload for dry-run mode."""
    return {
        "files": [
            {
                "path": f"{task_id.lower()}/dry-run-summary.md",
                "content": "\n".join([
                    f"# Resultado de dry-run para {task_id}",
                    "",
                    f"- Agent: {agent_id}",
                    f"- Title: {task_id}",
                    f"- Family: {skill_profile.get('family', 'general')}",
                    "",
                    "Esta tarea se ejecutó en modo dry-run.",
                    "No se ejecutó ningún agente externo ni se modificó el repositorio.",
                ]),
            }
        ],
        "notes": "Dry-run completado correctamente.",
    }


async def _run_agent_task(
    agent: Any,
    prompt: str,
    session_id: str,
    task_progress_cb: Any,
    task_timeout_sec: int,
    retry_attempts: int,
    retry_delay_sec: float,
    agent_id: str,
) -> Any:
    """Fire the agent and return AgentResult, letting exceptions propagate."""
    async def _call() -> Any:
        return await agent.execute(prompt, on_progress=task_progress_cb, session_id=session_id)

    return await retry_async(
        f"Ejecución de tarea del agente {agent_id}",
        _call(),
        timeout_sec=task_timeout_sec,
        retries=retry_attempts,
        delay_sec=retry_delay_sec,
        agent=agent_id,
    )


def _write_task_files(
    files_payload: list[dict[str, str]],
    output_dir: Path,
) -> list[str]:
    """Write agent-produced files to disk and return their normalized paths."""
    files_written: list[str] = []
    for f in files_payload:
        fpath = _safe_workspace_path(output_dir, f["path"])
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(f["content"], encoding="utf-8")
        files_written.append(normalize_output_path(fpath))
    return files_written


def _handle_task_blocked(
    detail: str,
    *,
    task_id: str,
    agent_id: str,
    result: Any,
    progress_path: Path,
    bridge: Any,
    dry_run: bool,
) -> None:
    """Persist a BLOCKER/QUESTION state and notify."""
    append_progress_event(
        progress_path,
        "blocked",
        "El agente reportó bloqueo/consulta y no entregó archivos",
        status="blocked",
        notes=detail,
        raw_response=(result.content[:1000] if isinstance(result.content, str) else None),
    )
    mem = load_memory()
    for t in mem.get("tasks", []):
        if t.get("id") == task_id:
            t["status"] = "pending"
            t["next_action"] = "awaiting_arch_response"
            t["blocked_note"] = detail
            t["failure_count"] = int(t.get("failure_count") or 0) + 1
            t["last_failure_at"] = utc_now()
            t["not_before"] = (
                datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=60)
            ).replace(tzinfo=None).isoformat()
            t["raw_response"] = (result.content or "")[:2000]
    _sync_project_status(mem)
    refresh_project_runtime_state(mem)
    save_memory(mem)
    record_blocker(
        f"Tarea {task_id} ({agent_id}) reportó bloqueo: {detail}",
        source=agent_id,
        task_id=task_id,
        agent_id=agent_id,
        retryable=True,
    )
    bridge.heartbeat("idle", f"Bloqueo en {task_id}")
    update_agent_status(agent_id, "idle", None)
    update_orchestrator_state(
        "blocked",
        phase="execution",
        task_id=task_id,
        detail=detail[:240],
        dry_run=dry_run,
    )
    log_event(f"Tarea {task_id} bloqueada por {agent_id}: {detail}", agent_id, level="warning")


def _handle_review_result(
    passed: bool,
    review_issues: list[str],
    review_round: int,
    *,
    task: dict[str, Any],
    task_id: str,
    agent_id: str,
    progress_path: Path,
    dry_run: bool,
) -> None:
    """Persist review outcome and propose corrections when needed."""
    if passed:
        return
    append_progress_event(
        progress_path,
        "error",
        "La revisión final detectó desajustes",
        status="error",
        review_round=review_round,
        review_issues=review_issues,
    )
    mem = load_memory()
    for t in mem.get("tasks", []):
        if t.get("id") == task_id:
            t["status"] = "pending"
            t["next_action"] = "correct_after_review"
            t["review_round"] = review_round
            t["review_issues"] = review_issues
    mem.setdefault("project", {})
    mem["project"]["status"] = "in_progress"
    mem["project"]["updated_at"] = utc_now()
    refresh_project_runtime_state(mem)
    save_memory(mem)
    log_event(f"Revisión final de {task_id} detectó issues: {review_issues}", agent_id, level="warning")

    proposal_title: str
    proposal_kind: str
    if review_round >= MAX_REVIEW_ROUNDS:
        mem = load_memory()
        mem.setdefault("project", {})
        mem["project"]["status"] = "blocked"
        mem["project"]["blocked_reason"] = (
            f"Se alcanzó el máximo de revisiones para {task_id}: {', '.join(review_issues) or 'desajuste de aceptación'}"
        )
        refresh_project_runtime_state(mem)
        save_memory(mem)
        update_orchestrator_state(
            "blocked",
            phase="execution",
            task_id=task_id,
            detail=mem["project"]["blocked_reason"],
            dry_run=dry_run,
        )
        proposal_title = f"Corregir {task_id}: {task.get('title')}"
        proposal_kind = "correction"
    else:
        proposal_title = f"Mejora sugerida tras {task_id}: {task.get('title')}"
        proposal_kind = "improvement"

    try:
        proposal = propose_follow_up_task(
            title=proposal_title,
            description=f"Ajuste de {task_id} tras revisión: {', '.join(review_issues)}",
            rationale=f"Revisión final ({review_round}) detectó issues: {', '.join(review_issues)}",
            agent=agent_id,
            kind=proposal_kind,
            execution_dir=task.get("execution_dir"),
            acceptance=task.get("acceptance", []),
        )
        _notify_proposal_by_telegram(proposal)
    except Exception as exc:
        log_event(f"Falló la propuesta de seguimiento por Telegram: {exc}", "system")


def _recover_from_existing_artifacts(task: dict[str, Any], project: dict[str, Any], repo_state: dict[str, Any]) -> list[str]:
    """Check if the task has already been completed externally or in a previous run."""
    return check_existing_task_artifacts(task, project, repo_state)


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
    task.setdefault("execution_dir", infer_task_execution_dir(project, task, repo_state))

    # ── Fase 0: Validar estructura canónica ─────────────────────────────────
    structure_violations = validate_project_structure(str(task.get("execution_dir") or ""), project, task)
    if structure_violations:
        violation_detail = " | ".join(structure_violations)
        log_event(f"[Fase 0] Tarea {task_id} bloqueada: {violation_detail}", agent_id, level="error")
        record_blocker(f"BLOCKER:{task_id} {violation_detail}", source="orchestrator", task_id=task_id, agent_id=agent_id, retryable=False)
        mem = load_memory()
        for t in mem.get("tasks", []):
            if t.get("id") == task_id:
                t.update({"status": "error", "error": violation_detail, "failure_kind": "structure", "retryable": False, "next_action": "fix_execution_dir"})
        _sync_project_status(mem)
        refresh_project_runtime_state(mem)
        save_memory(mem)
        update_orchestrator_state("blocked", phase="execution", task_id=task_id, detail=violation_detail[:240], dry_run=dry_run)
        try:
            send_telegram_message(f"\u274c [Fase 0] Ruta inválida en {task_id}:\n{violation_detail}")
        except Exception:
            pass
        return

    # ── Fase 3: Recuperación de estado canónico ─────────────────────────────
    existing_artifacts = _recover_from_existing_artifacts(task, project, repo_state)
    if existing_artifacts:
        log_event(f"[Fase 3] Recuperación: se encontraron {len(existing_artifacts)} artefactos existentes para {task_id}", agent_id, level="info")
        mem = load_memory()
        for t in mem.get("tasks", []):
            if t.get("id") == task_id:
                t.update({
                    "status": "passed",
                    "files_produced": existing_artifacts,
                    "updated_at": utc_now(),
                    "notes": "Completado mediante recuperación de artefactos existentes (Fase 3)."
                })
        _sync_project_status(mem)
        refresh_project_runtime_state(mem)
        save_memory(mem)
        update_agent_status(agent_id, "idle", task_id)
        bridge.speak(f"Reanudado {task_id}: artefactos ya presentes.")
        return

    # ── Preparar workspace ──────────────────────────────────────────────────
    workspace_files = write_agent_workspace_files(agent_id, task, project, skill_profile, repo_state)
    try:
        session_diagnostics = apply_session_diagnostics_to_workspace(agent_id, task, project, skill_profile, repo_state)
        if session_diagnostics:
            log_event(f"Diagnóstico de sesión aplicado para {task_id}: {session_diagnostics.get('summary')}", agent_id)
    except Exception as exc:
        log_event(f"No se pudo aplicar diagnóstico de sesión para {task_id}: {exc}", "system", level="warning")
    progress_path = workspace_files["progress_path"]

    update_agent_status(agent_id, "working", task_id)
    update_orchestrator_state("executing", phase="execution", task_id=task_id, detail=f"Ejecutando {task_id}", dry_run=dry_run)
    bridge.heartbeat("working", f"Tarea {task_id}: {task['title'][:50]}")
    bridge.speak(f"Iniciando {task_id}: {task['title']}")
    log_event(f"Iniciando tarea {task_id}", agent_id)

    # ── Session ID ─────────────────────────────────────────────────────────
    mem = load_memory()
    generated_session_id = _stable_session_id(
        str(mem.get("project", {}).get("id") or mem.get("project", {}).get("name") or "project"),
        agent_id, task_id,
    )
    for t in mem.get("tasks", []):
        if t.get("id") == task_id:
            stored = str(t.get("session_id") or "").strip()
            session_id = stored if _is_valid_session_id(stored) else generated_session_id
            t.update({"status": "in_progress", "progress_file": str(progress_path),
                      "workspace_context": str(workspace_files["context_md"]),
                      "skills": skill_profile["skills"], "skill_family": skill_profile["family"],
                      "session_id": session_id})
    if str(progress_path) not in mem.get("progress_files", []):
        mem.setdefault("progress_files", []).append(str(progress_path))
    save_memory(mem)

    append_progress_event(progress_path, "started", "Tarea iniciada", status="in_progress",
                          skill_profile=skill_profile, repo_state=repo_state, dry_run=dry_run)

    # ── Construir prompt ────────────────────────────────────────────────────
    acceptance_str = "\n".join(f"- {a}" for a in task.get("acceptance", []))
    skill_list = "\n".join(f"- {item}" for item in skill_profile.get("skills", []) or ["General engineering"])
    instruction_list = "\n".join(f"- {item}" for item in skill_profile.get("instructions", []) or ["Follow the repository stack."])
    prompt_kwargs = {
        "context": project_context, "repo_context": json.dumps(repo_state, indent=2, ensure_ascii=False),
        "skill_family": skill_profile.get("family", "general"),
        "skill_focus": skill_profile.get("prompt_focus", "General engineering specialist"),
        "skill_list": skill_list, "instruction_list": instruction_list,
        "workspace_md_path": str(workspace_files["context_md"]),
        "workspace_json_path": str(workspace_files["context_json"]),
        "progress_path": str(progress_path),
        "task_id": task_id, "title": task["title"], "description": task["description"],
        "acceptance": acceptance_str,
    }
    prompt = BYTE_TASK_PROMPT.format(**prompt_kwargs) if agent_id == "byte" else PIXEL_TASK_PROMPT.format(**prompt_kwargs)

    # ── mark_task_failure (closure) ─────────────────────────────────────────
    def mark_task_failure(
        detail: str,
        *,
        progress_message: str,
        retryable: bool = True,
        raw_response: str | None = None,
        failure_kind: str | None = None,
    ) -> None:
        append_progress_event(progress_path, "error", progress_message, status="error",
                              failure_kind=failure_kind,
                              raw_response=(raw_response[:1000] if isinstance(raw_response, str) else None))
        mem = load_memory()
        fallback_agent: str | None = None
        failure_count = 0
        for t in mem.get("tasks", []):
            if t.get("id") == task_id:
                failure_count = int(t.get("failure_count") or 0) + 1
                t.update({"status": "error", "error": detail, "failure_kind": failure_kind,
                          "retryable": retryable, "failure_count": failure_count,
                          "last_failure_at": utc_now(),
                          "next_action": "review" if not retryable else "retry_or_reassign"})
                if raw_response:
                    t["raw_response"] = raw_response[:2000]
                fallback_agent = _fallback_agent_for(t, agent_id)
                if retryable and fallback_agent and failure_count >= RESUME_FAILURE_THRESHOLD:
                    t.update({"previous_agent": agent_id, "agent": fallback_agent,
                              "status": "pending", "next_action": f"reassigned_to_{fallback_agent}",
                              "suggested_agent": fallback_agent, "reassigned_at": utc_now()})
        _sync_project_status(mem)
        refresh_project_runtime_state(mem)
        save_memory(mem)
        record_blocker(f"Tarea {task_id} ({agent_id}) falló [{failure_kind or 'unknown'}]: {detail}",
                       source=agent_id, task_id=task_id, agent_id=agent_id, retryable=retryable)
        if fallback_agent and retryable and failure_count >= RESUME_FAILURE_THRESHOLD:
            log_event(f"Tarea {task_id} reasignada a {fallback_agent} tras {failure_count} fallos", "system", level="warning")
        bridge.heartbeat("error", f"Error en {task_id}")
        update_agent_status(agent_id, "error", task_id)
        update_orchestrator_state("blocked", phase="execution", task_id=task_id, detail=detail, dry_run=dry_run)
        log_event(f"La tarea {task_id} FALLÓ [{failure_kind or 'unknown'}]: {detail}", agent_id, level="error")

    # ── Ejecución del agente ────────────────────────────────────────────────
    result = None
    if dry_run:
        data = _dry_run_data(task_id, agent_id, skill_profile)
    else:
        if client is None:
            raise RuntimeError("Se requiere un cliente OpenClaw fuera del modo dry-run")
        agent = client.get_agent(agent_id)
        task_progress_cb = make_progress_callback(notify_telegram=True, telegram_throttle_sec=30.0)
        try:
            result = await _run_agent_task(
                agent, prompt, session_id, task_progress_cb,
                task_timeout_sec, retry_attempts, retry_delay_sec, agent_id,
            )
        except Exception as exc:
            failure_kind: FailureKind | None = (
                result.failure_kind if result is not None and getattr(result, "failure_kind", None)
                else _infer_failure_kind(content="", stderr_lines=[str(exc)], returncode=1, exc=exc)
            )
            mark_task_failure(
                f"error de ejecución del agente: {exc}",
                progress_message=("Fallo de infraestructura del agente" if failure_kind == "infra"
                                  else f"Falló la ejecución del agente: {exc}"),
                retryable=failure_kind != "infra",
                failure_kind=failure_kind,
            )
            return

        # Consumir failure_kind y events nativos del SDK
        log_event(
            f"{agent_id.upper()} respondió en {result.elapsed_sec:.0f}s "
            f"(content_len={len(result.content)}, failure_kind={result.failure_kind or 'none'})",
            agent_id,
        )
        for ev in (result.events or []):
            if ev.get("kind") in ("tool_use", "thinking"):
                append_progress_event(progress_path, ev["kind"], ev.get("label", "")[:200],
                                      status="running", notes=ev.get("tool_name"))

        # Parsear respuesta
        try:
            data = _parse_task_json_payload(result.content)
            files_payload, task_notes = _normalize_task_output(data, agent_id=agent_id, task_id=task_id)
        except TaskOutputBlocked as exc:
            _handle_task_blocked(
                str(exc) or f"BLOCKER:{task_id} bloqueo sin detalle",
                task_id=task_id, agent_id=agent_id, result=result,
                progress_path=progress_path, bridge=bridge, dry_run=dry_run,
            )
            return
        except Exception as exc:
            _stderr = getattr(result, "stderr_lines", [])
            _content = getattr(result, "content", "")
            failure_kind = (
                result.failure_kind if getattr(result, "failure_kind", None)
                else _infer_failure_kind(content=_content, stderr_lines=_stderr + [str(exc)], returncode=1, exc=exc)
            )
            mark_task_failure(
                f"Invalid JSON response: {exc}",
                progress_message=("Fallo de infraestructura" if failure_kind == "infra"
                                  else "Respuesta JSON inválida o incompleta del agente"),
                retryable=failure_kind != "infra",
                raw_response=result.content,
                failure_kind=failure_kind,
            )
            return

    # Dry-run: extraer archivos del payload sintético
    if dry_run:
        files_payload = data.get("files", [])
        task_notes = data.get("notes", "")

    # ── Escribir archivos y persistir estado done ───────────────────────────
    try:
        files_written = _write_task_files(files_payload, output_dir)

        mem = load_memory()
        for t in mem.get("tasks", []):
            if t.get("id") == task_id:
                t.update({"status": "done", "files": files_written, "notes": task_notes,
                          "progress_file": str(progress_path),
                          "skill_family": skill_profile["family"], "skills": skill_profile["skills"]})
        mem.setdefault("files_produced", []).extend(
            f for f in files_written if f not in mem["files_produced"]
        )
        _sync_project_status(mem)
        refresh_project_runtime_state(mem)
        _synchronize_project_artifacts(mem)

        # ── Revisión de aceptación ──────────────────────────────────────────
        review_round = int(task.get("review_round") or 0) + 1
        passed_review, review_issues = _task_matches_acceptance(task, project)
        _record_task_review(task_id, review_round, review_issues)
        _handle_review_result(
            passed_review, review_issues, review_round,
            task=task, task_id=task_id, agent_id=agent_id,
            progress_path=progress_path, dry_run=dry_run,
        )
        if not passed_review:
            return

        append_progress_event(progress_path, "completed", "Tarea completada correctamente",
                              status="done", files=files_written, notes=task_notes, dry_run=dry_run)

        # ── Git finalize ────────────────────────────────────────────────────
        git_finalize_result: dict[str, Any] = {"committed": False, "pushed": False, "pr_created": False}
        if repo_state.get("action") not in ("dry-run", None) and files_written:
            try:
                git_finalize_result = finalize_repo_after_task(
                    Path(repo_state["repo_path"]), agent_id, task_id,
                    task.get("title", task_id), create_pr=True,
                )
                log_event(
                    f"Git finalize para {task_id}: commit={git_finalize_result.get('committed')} "
                    f"push={git_finalize_result.get('pushed')} pr={git_finalize_result.get('pr_created')}",
                    agent_id,
                )
            except Exception as exc:
                log_event(f"Git finalize falló (no crítico): {exc}", agent_id, level="warning")

        bridge.heartbeat("idle", f"Done: {task_id}")
        bridge.speak(f"Completada {task_id}: se escribieron {len(files_written)} archivo(s).")
        log_event(f"Tarea {task_id} completada. Archivos: {files_written}", agent_id)
        update_agent_status(agent_id, "idle", None)
        update_orchestrator_state("idle", phase="execution", task_id=None, detail=f"Completed {task_id}", dry_run=dry_run)
        try:
            send_telegram_message("\n".join([
                _telegram_task_summary(task, status="completada"), "",
                f"Directorio de ejecución: {task.get('execution_dir') or infer_task_execution_dir(project, task, repo_state)}",
                f"Git: commit={git_finalize_result.get('committed')} push={git_finalize_result.get('pushed')} pr={git_finalize_result.get('pr_created')}",
            ]))
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
        review_session_id = _stable_session_id(
            str(mem.get("project", {}).get("id") or mem.get("project", {}).get("name") or "project"),
            "arch",
            "review",
        )
        result = await retry_async(
            "Final review",
            lambda: arch.execute(review_prompt, on_progress=review_cb, session_id=review_session_id, thinking="medium"),
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
        refresh_project_runtime_state(mem)
        _synchronize_project_artifacts(mem)
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
        try:
            send_telegram_message(_telegram_project_summary(mem))
        except Exception as exc:
            log_event(f"Falló el resumen de proyecto por Telegram: {exc}", "system")
        return

    if _has_tasks_needing_correction(mem.get("tasks", [])):
        mem = load_memory()
        mem.setdefault("project", {})
        mem["project"]["status"] = "blocked"
        mem["project"]["blocked_reason"] = "Hay tareas con corrección pendiente; no se puede entregar todavía"
        mem["project"]["updated_at"] = utc_now()
        refresh_project_runtime_state(mem)
        save_memory(mem)
        update_orchestrator_state(
            "blocked",
            phase="review",
            detail="Revisión detenida: hay tareas con corrección pendiente",
            dry_run=dry_run,
        )
        log_event(
            "La revisión final detectó tareas con corrección pendiente; no se marcará como entregado",
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
    mem["project"]["delivery"] = {
        "delivery_path": str(delivery_path),
        "git": {
            "branch": mem.get("project", {}).get("branch"),
            "repo_path": mem.get("project", {}).get("repo_path"),
            "pushed": True,
        },
    }
    mem.setdefault("milestones", [])
    mem["milestones"].append(f"Proyecto entregado en {utc_now()}")
    refresh_project_runtime_state(mem)
    _synchronize_project_artifacts(mem)
    save_memory(mem)

    arch_bridge.speak("Proyecto entregado. Revisa DELIVERY.md")
    log_event("Proyecto entregado. Revisa DELIVERY.md", "arch")
    try:
        send_telegram_message(
            "\n".join(
                [
                    _telegram_project_summary(mem),
                    "",
                    f"Entrega: {delivery_path}",
                    f"Git branch: {mem.get('project', {}).get('branch') or 'n/a'}",
                ]
            )
        )
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
            refresh_project_runtime_state(mem)
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
            refresh_project_runtime_state(mem)
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
                    refresh_project_runtime_state(mem)
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
                    except ProjectClarificationRequired as exc:
                        mem = load_memory()
                        mem.setdefault("project", {})
                        mem["project"]["status"] = "blocked"
                        mem["project"]["bootstrap_status"] = "awaiting_clarification"
                        mem["project"]["updated_at"] = utc_now()
                        mem.setdefault("blockers", [])
                        mem["blockers"].append(
                            {
                                "ts": utc_now(),
                                "source": "arch",
                                "msg": str(exc),
                                "questions": getattr(exc, "questions", []),
                            }
                        )
                        refresh_project_runtime_state(mem)
                        save_memory(mem)
                        log_event(f"Planificación en pausa por aclaración: {exc}", "arch", level="warning")
                        print(str(exc))
                        return
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
                        refresh_project_runtime_state(mem)
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
                        refresh_project_runtime_state(mem)
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
                    telegram_request = _consume_telegram_control_request()
                    if telegram_request == "pause":
                        mem = load_memory()
                        mem.setdefault("project", {})
                        mem["project"]["status"] = "in_progress"
                        mem["project"]["updated_at"] = utc_now()
                        refresh_project_runtime_state(mem)
                        save_memory(mem)
                        update_orchestrator_state(
                            "paused",
                            phase="execution",
                            detail="Pausado por comando de Telegram",
                            dry_run=args.dry_run,
                        )
                        send_telegram_message("Orquestador pausado por comando de Telegram.")
                        print("\nEjecución pausada por Telegram.")
                        return

                    now_iso = utc_now()
                    ready = [
                        task
                        for task in pending_tasks
                        if all(dep in completed_ids for dep in task.get("depends_on", []))
                        and task.get("status") == "pending"
                        and (not task.get("not_before") or str(task.get("not_before")) <= now_iso)
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
                    refresh_project_runtime_state(mem)
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
