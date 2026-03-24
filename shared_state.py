from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
PRIMARY_MEMORY = BASE_DIR / "shared" / "MEMORY.json"
LEGACY_MEMORY = BASE_DIR / "MEMORY.json"

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
    """Load shared memory, preferring the canonical shared/ location."""
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
            save_memory(merged)
        return merged


def save_memory(data: dict[str, Any]) -> dict[str, Any]:
    """Persist shared memory to both the canonical and legacy paths."""
    with _MEMORY_LOCK:
        payload = _deep_merge(DEFAULT_MEMORY, data)
        for path in (PRIMARY_MEMORY, LEGACY_MEMORY):
            _write_atomic(path, payload)
        return payload


def ensure_memory_file() -> dict[str, Any]:
    """Ensure the shared memory file exists and is normalized."""
    return save_memory(load_memory())
