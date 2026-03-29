from __future__ import annotations

import fcntl
import json
import os
import threading
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = Path(os.getenv("OPENCLAW_RUNTIME_DIR", str(Path.home() / ".openclaw" / "multi-agents")))
PRIMARY_MEMORY = RUNTIME_DIR / "MEMORY.json"
LEGACY_MEMORY = [
    BASE_DIR / "shared" / "MEMORY.json",
    BASE_DIR / "MEMORY.json",
]
_FLOCK_PATH = PRIMARY_MEMORY.with_suffix(".lock")

# Limits for unbounded-growth arrays (GAP-4 / P2)
from datetime import datetime, timezone
MAX_LOG_ENTRIES = 500
MAX_MESSAGES = 200
MAX_BLOCKERS = 100
TASK_PREVIEW_STATUSES = {"running", "stopped", "not_applicable"}

def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp without tzinfo (database compatible)."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

DEFAULT_MEMORY: dict[str, Any] = {
    "schema_version": "3.0",  # Nuevo schema con estado por proyecto
    # Proyecto activo (solo uno a la vez)
    "active_project_id": None,
    "project": {
        "id": None,
        "name": None,
        "description": None,
        "tech_stack": {},
        "output_dir": "./output",
        "repo_url": None,
        "repo_name": None,
        "repo_path": None,
        "branch": None,
        "bootstrap_status": "idle",
        "status": "idle",
        "created_at": None,
        "updated_at": None,
        "orchestrator": {
            "status": "idle",
            "pid": None,
            "phase": None,
            "task_id": None,
            "started_at": None,
            "updated_at": None,
            "dry_run": False,
        },
    },
    "plan": {
        "phases": [],
        "current_phase": None,
    },
    "tasks": [],
    "agents": {
        "arch": {"status": "idle", "current_task": None, "last_seen": None},
        "byte": {"status": "idle", "current_task": None, "last_seen": None},
        "pixel": {"status": "idle", "current_task": None, "last_seen": None},
    },
    # Proyectos archivados (máximo 10)
    "archived_projects": [],
    # Historial de proyectos entregados
    "projects": [],
    # Sistema y diagnóstico
    "blockers": [],
    "proposals": [],
    "milestones": [],
    "files_produced": [],
    "progress_files": [],
    "messages": [],
    "log": [],
    # Configuración de modelos con estado
    "model_status": {},
}

_MEMORY_LOCK = threading.RLock()
ACTIVE_ORCHESTRATOR_STATES = {"starting", "planning", "executing", "review", "working"}
RESUMABLE_ORCHESTRATOR_STATES = {"idle", "paused", "error"}


@contextmanager
def _cross_process_lock():
    """Exclusive file lock that works across processes (POSIX/Linux)."""
    _FLOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_FLOCK_PATH, "w") as _lf:
        fcntl.flock(_lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(_lf, fcntl.LOCK_UN)


def _pid_is_alive(pid: int | None) -> bool:
    """Return True when *pid* appears to be running."""
    if not pid or pid <= 0:
        return False
    stat_path = Path(f"/proc/{pid}/stat")
    try:
        if stat_path.exists():
            stat_fields = stat_path.read_text(encoding="utf-8").split()
            if len(stat_fields) >= 3 and stat_fields[2] == "Z":
                return False
    except Exception:
        pass
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _deep_merge(base: Any, incoming: Any) -> Any:
    """Merge incoming data into a default skeleton without dropping extras."""
    if isinstance(base, dict) and isinstance(incoming, dict):
        merged: dict[str, Any] = {}
        for key in base:
            if key in incoming:
                merged[key] = _deep_merge(base[key], incoming[key])
            else:
                merged[key] = deepcopy(base[key])
        for key in incoming:
            if key not in merged:
                merged[key] = incoming[key]
        return merged

    if incoming is None:
        return deepcopy(base)

    return incoming


def _normalize_task_preview_fields(mem: dict[str, Any]) -> None:
    """Ensure task preview fields always exist and use a valid status."""
    tasks = mem.get("tasks")
    if not isinstance(tasks, list):
        return
    for task in tasks:
        if not isinstance(task, dict):
            continue
        if "preview_url" not in task:
            task["preview_url"] = None
        elif task["preview_url"] is not None and not isinstance(task["preview_url"], str):
            task["preview_url"] = str(task["preview_url"])

        preview_status = str(task.get("preview_status") or "").strip().lower()
        if preview_status not in TASK_PREVIEW_STATUSES:
            task["preview_status"] = "not_applicable"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def default_memory() -> dict[str, Any]:
    """Return a fresh copy of the default memory layout."""
    return deepcopy(DEFAULT_MEMORY)


def refresh_project_runtime_state(mem: dict[str, Any]) -> dict[str, Any]:
    """Derive explicit runtime status fields from the current task graph."""
    project = mem.setdefault("project", {})
    orchestrator = project.setdefault("orchestrator", {})
    tasks = [task for task in mem.get("tasks", []) if isinstance(task, dict)]

    counts = {
        "total": len(tasks),
        "done": sum(1 for task in tasks if task.get("status") == "done"),
        "pending": sum(1 for task in tasks if task.get("status") == "pending"),
        "in_progress": sum(1 for task in tasks if task.get("status") == "in_progress"),
        "paused": sum(1 for task in tasks if task.get("status") == "paused"),
        "error": sum(1 for task in tasks if task.get("status") == "error"),
    }
    counts["open"] = counts["pending"] + counts["in_progress"] + counts["paused"] + counts["error"]

    pid_alive = _pid_is_alive(orchestrator.get("pid"))
    orchestrator_status = str(orchestrator.get("status") or "").lower()
    project_status = str(project.get("status") or "").lower()

    if project_status == "delivered" and counts["open"] == 0:
        runtime_status = "delivered"
    elif orchestrator_status == "paused":
        runtime_status = "paused" if counts["open"] == 0 else "resumable"
    elif counts["error"] > 0:
        runtime_status = "blocked" if pid_alive or orchestrator_status in ACTIVE_ORCHESTRATOR_STATES else "resumable"
    elif counts["pending"] > 0 or counts["in_progress"] > 0:
        runtime_status = "running" if pid_alive or orchestrator_status in ACTIVE_ORCHESTRATOR_STATES else "resumable"
    elif pid_alive or orchestrator_status in ACTIVE_ORCHESTRATOR_STATES:
        runtime_status = "running"
    elif project_status in {"planned", "planning", "in_progress"}:
        runtime_status = "resumable"
    else:
        runtime_status = "idle"

    if counts["error"] > 0:
        blocked_reason = f"{counts['error']} tarea(s) con error"
    elif counts["paused"] > 0:
        blocked_reason = f"{counts['paused']} tarea(s) pausadas"
    elif counts["pending"] > 0 or counts["in_progress"] > 0:
        blocked_reason = f"{counts['pending'] + counts['in_progress']} tarea(s) pendientes o en progreso"
    else:
        blocked_reason = None

    project["task_counts"] = counts
    project["runtime_status"] = runtime_status
    project["can_resume"] = bool(counts["open"])
    project["blocked_reason"] = blocked_reason
    project["has_blockers"] = bool(mem.get("blockers"))
    return mem


def load_memory() -> dict[str, Any]:
    """Load shared memory, preferring the canonical shared/ location.

    Reads do NOT need a file lock: _write_atomic uses an atomic tmp-file
    replace, so any read always sees a complete, valid JSON snapshot.
    """
    with _MEMORY_LOCK:
        source: dict[str, Any] | None = None
        source_path: Path | None = None

        for path in (PRIMARY_MEMORY, *LEGACY_MEMORY):
            if path.exists():
                try:
                    source = _read_json(path)
                    source_path = path
                    break
                except Exception:
                    continue

        if not isinstance(source, dict):
            source = default_memory()

        merged = _deep_merge(DEFAULT_MEMORY, source)
        _normalize_task_preview_fields(merged)
        if source_path != PRIMARY_MEMORY or merged != source:
            # Migrate / normalise – go through save_memory for truncation.
            save_memory(merged)
        return merged


def save_memory(data: dict[str, Any]) -> dict[str, Any]:
    """Persist shared memory to both paths under an exclusive cross-process lock.

    Also truncates unbounded arrays so the JSON never grows without limit.
    """
    with _MEMORY_LOCK, _cross_process_lock():
        payload = _deep_merge(DEFAULT_MEMORY, data)
        # Truncate growing arrays (GAP-4 / P2)
        if len(payload.get("log", [])) > MAX_LOG_ENTRIES:
            payload["log"] = payload["log"][-MAX_LOG_ENTRIES:]
        if len(payload.get("messages", [])) > MAX_MESSAGES:
            payload["messages"] = payload["messages"][-MAX_MESSAGES:]
        if len(payload.get("blockers", [])) > MAX_BLOCKERS:
            payload["blockers"] = payload["blockers"][-MAX_BLOCKERS:]
        _normalize_task_preview_fields(payload)
        _write_atomic(PRIMARY_MEMORY, payload)
        return payload


def ensure_memory_file() -> dict[str, Any]:
    """Ensure the shared memory file exists and is normalized."""
    return save_memory(load_memory())


# ---------------------------------------------------------------------------
# Funciones para gestión de proyectos múltiples (Tarea 1.1)
# ---------------------------------------------------------------------------

MAX_ARCHIVED_PROJECTS = 10


def archive_current_project(mem: dict[str, Any]) -> dict[str, Any]:
    """
    Archivar el proyecto actual si existe y está entregado.
    
    Mueve el proyecto a archived_projects y limpia el estado activo.
    """
    project = mem.get("project", {})
    project_id = project.get("id")
    
    if not project_id:
        # No hay proyecto activo, nada que archivar
        return mem
    
    # Crear snapshot del proyecto
    archived = {
        "id": project_id,
        "name": project.get("name"),
        "description": project.get("description"),
        "status": project.get("status"),
        "created_at": project.get("created_at"),
        "updated_at": project.get("updated_at"),
        "repo_url": project.get("repo_url"),
        "repo_name": project.get("repo_name"),
        "task_count": len(mem.get("tasks", [])),
        "archived_at": utc_now(),
    }
    
    # Añadir a archivados
    mem.setdefault("archived_projects", [])
    mem["archived_projects"].append(archived)
    
    # Mantener solo los últimos MAX_ARCHIVED_PROJECTS
    if len(mem["archived_projects"]) > MAX_ARCHIVED_PROJECTS:
        mem["archived_projects"] = mem["archived_projects"][-MAX_ARCHIVED_PROJECTS:]
    
    return mem


def start_fresh_project(mem: dict[str, Any], brief: str) -> dict[str, Any]:
    """
    Iniciar un proyecto completamente nuevo.
    
    Archiva el proyecto anterior si existe y limpia todas las tareas.
    """
    from datetime import datetime
    
    # Archivar proyecto anterior si existe
    if mem.get("project", {}).get("id"):
        mem = archive_current_project(mem)
    
    # Generar nuevo ID de proyecto
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    slug = "".join(c if c.isalnum() else "-" for c in brief[:30]).strip("-")
    new_id = f"{slug}-{timestamp}"
    
    # Resetear estado del proyecto
    mem["active_project_id"] = new_id
    mem["project"] = {
        "id": new_id,
        "name": None,
        "description": brief,
        "tech_stack": {},
        "output_dir": "./output",
        "repo_url": None,
        "repo_name": None,
        "repo_path": None,
        "branch": None,
        "bootstrap_status": "idle",
        "status": "planning",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "orchestrator": {
            "status": "starting",
            "pid": None,
            "phase": None,
            "task_id": None,
            "started_at": utc_now(),
            "updated_at": utc_now(),
            "dry_run": False,
        },
    }
    
    # Limpiar tareas y estado relacionado
    mem["tasks"] = []
    mem["plan"] = {"phases": [], "current_phase": None}
    mem["blockers"] = []
    mem["files_produced"] = []
    mem["progress_files"] = []
    mem["messages"] = []
    mem["milestones"] = []
    
    # Resetear agentes
    for agent_id in ["arch", "byte", "pixel"]:
        mem["agents"][agent_id] = {
            "status": "idle",
            "current_task": None,
            "last_seen": None,
        }
    
    return mem


def clean_blocked_tasks(mem: dict[str, Any]) -> int:
    """
    Mover tareas en in_progress a cancelled.
    
    Retorna el número de tareas limpiadas.
    """
    cleaned = 0
    for task in mem.get("tasks", []):
        if task.get("status") == "in_progress":
            task["status"] = "cancelled"
            task["cancelled_reason"] = "new_project_started"
            task["cancelled_at"] = utc_now()
            cleaned += 1
    return cleaned


def get_active_project(mem: dict[str, Any]) -> dict[str, Any] | None:
    """Obtener el proyecto activo o None si no hay."""
    if mem.get("active_project_id"):
        return mem.get("project")
    return None


def is_project_active(mem: dict[str, Any]) -> bool:
    """Verificar si hay un proyecto activo."""
    return bool(mem.get("active_project_id") and mem.get("project", {}).get("id"))
