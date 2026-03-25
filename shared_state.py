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
PRIMARY_MEMORY = BASE_DIR / "shared" / "MEMORY.json"
LEGACY_MEMORY = BASE_DIR / "MEMORY.json"
_FLOCK_PATH = PRIMARY_MEMORY.with_suffix(".lock")

# Limits for unbounded-growth arrays (GAP-4 / P2)
MAX_LOG_ENTRIES = 500
MAX_MESSAGES = 200
MAX_BLOCKERS = 100

DEFAULT_MEMORY: dict[str, Any] = {
    "schema_version": "2.0",
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
    "blockers": [],
    "milestones": [],
    "files_produced": [],
    "progress_files": [],
    "messages": [],
    "log": [],
}

_MEMORY_LOCK = threading.RLock()


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


def load_memory() -> dict[str, Any]:
    """Load shared memory, preferring the canonical shared/ location.

    Reads do NOT need a file lock: _write_atomic uses an atomic tmp-file
    replace, so any read always sees a complete, valid JSON snapshot.
    """
    with _MEMORY_LOCK:
        source: dict[str, Any] | None = None
        source_path: Path | None = None

        for path in (PRIMARY_MEMORY, LEGACY_MEMORY):
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
        for path in (PRIMARY_MEMORY, LEGACY_MEMORY):
            _write_atomic(path, payload)
        return payload


def ensure_memory_file() -> dict[str, Any]:
    """Ensure the shared memory file exists and is normalized."""
    return save_memory(load_memory())
