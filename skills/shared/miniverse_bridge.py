""" miniverse_bridge.py - LOCAL MODE (No external Miniverse)

This is a drop-in replacement for the Miniverse bridge.
All network calls to miniverse-public-production.up.railway.app are replaced with local logging.
"""

import os
import time
import json
import threading
from typing import Literal
from pathlib import Path

# Check if Miniverse is disabled
MINIVERSE_ENABLED = os.getenv("MINIVERSE_ENABLED", "false").lower() == "true"
MINIVERSE_URL = os.getenv("MINIVERSE_URL", "local")

AgentState = Literal["working", "thinking", "speaking", "idle", "sleeping", "error", "offline"]

AGENT_META = {
    "arch": {"display": "ARCH 🗂️", "role": "Coordinator"},
    "byte": {"display": "BYTE 💻", "role": "Programmer"},
    "pixel": {"display": "PIXEL 🎨", "role": "Designer"},
}

# Local log directory
LOG_DIR = Path("/var/www/openclaw-multi-agents/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)


class MiniverseBridge:
    """
    Local-only Miniverse bridge.
    All network calls are replaced with local logging.
    """

    def __init__(self, agent_id: str, interval: int = 30):
        self.agent_id = agent_id
        self.interval = interval
        self._state: AgentState = "idle"
        self._task = "Standing by"
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self):
        """Start background heartbeat (local logging only)."""
        self._running = True
        print(f"[miniverse-local] {self.agent_id} started (local mode, Miniverse disabled)")

    def stop(self):
        """Stop heartbeat."""
        self._running = False
        self._log("offline", "Shutting down")

    def heartbeat(self, state: AgentState, task: str):
        """Update state locally (no network call)."""
        self._state = state
        self._task = task
        self._log(state, task)

    def speak(self, message: str):
        """Log speak message locally."""
        self._log("speaking", message[:80])

    def message_agent(self, to: str, message: str, from_route: str | None = None, to_route: str | None = None):
        """Log message to another agent locally."""
        log_entry = {
            "timestamp": time.time(),
            "from": self.agent_id,
            "to": to,
            "message": message,
            "from_route": from_route,
            "to_route": to_route
        }
        self._write_log(f"message_to_{to}", log_entry)
        print(f"[miniverse-local] {self.agent_id} -> {to}: {message[:50]}...")

    def _log(self, state: str, task: str):
        """Write heartbeat to local log."""
        log_entry = {
            "timestamp": time.time(),
            "agent": self.agent_id,
            "state": state,
            "task": task
        }
        self._write_log("heartbeat", log_entry)

    def _write_log(self, log_type: str, data: dict):
        """Write to local JSONL log file."""
        log_file = LOG_DIR / f"{self.agent_id}_local.jsonl"
        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(data) + "\n")
        except Exception as e:
            print(f"[miniverse-local] Log error: {e}")

    def get_inbox(self) -> list:
        """Check local inbox (no network call)."""
        inbox_file = LOG_DIR / f"{self.agent_id}_inbox.jsonl"
        messages = []
        try:
            if inbox_file.exists():
                with open(inbox_file, "r") as f:
                    for line in f:
                        if line.strip():
                            messages.append(json.loads(line))
                # Clear inbox after reading
                inbox_file.unlink(missing_ok=True)
        except Exception as e:
            print(f"[miniverse-local] Inbox error: {e}")
        return messages

    def check_inbox(self) -> list:
        """Alias for get_inbox() for compatibility with orchestrator."""
        return self.get_inbox()


def get_bridge(agent_id: str) -> MiniverseBridge:
    """Get a MiniverseBridge instance for the given agent."""
    return MiniverseBridge(agent_id)


# Cache for bridge instances
_bridge_cache: dict[str, MiniverseBridge] = {}


def get_bridge_cached(agent_id: str) -> MiniverseBridge:
    """Get or create a cached MiniverseBridge instance."""
    if agent_id not in _bridge_cache:
        _bridge_cache[agent_id] = MiniverseBridge(agent_id)
    return _bridge_cache[agent_id]
