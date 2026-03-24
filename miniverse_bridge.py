"""
miniverse_bridge.py
Miniverse integration for the Dev Squad agents.
Each agent imports this and calls heartbeat() / speak() / message_agent().

Usage:
    from miniverse_bridge import MiniverseBridge
    bridge = MiniverseBridge(agent_id="arch")
    bridge.heartbeat("working", "Planning project tasks")
    bridge.speak("Starting task decomposition...")
    bridge.message_agent("byte", "TASK:001 TYPE:code ...")
"""

import os
import time
import json
import threading
import requests
from typing import Literal

MINIVERSE_URL = os.getenv(
    "MINIVERSE_URL",
    "https://miniverse-public-production.up.railway.app"   # public world
    # OR use local: "http://localhost:4321" after `npx create-miniverse`
)

AgentState = Literal["working", "thinking", "speaking", "idle", "sleeping", "error", "offline"]

AGENT_META = {
    "arch": {"display": "ARCH 🗂️", "role": "Coordinator"},
    "byte": {"display": "BYTE 💻", "role": "Programmer"},
    "pixel": {"display": "PIXEL 🎨", "role": "Designer"},
}


class MiniverseBridge:
    def __init__(self, agent_id: str, interval: int = 30):
        self.agent_id = agent_id
        self.interval = interval
        self._state: AgentState = "idle"
        self._task = "Standing by"
        self._thread: threading.Thread | None = None
        self._running = False

    # ── Public API ───────────────────────────────────────────────────────────

    def start(self):
        """Start background heartbeat thread."""
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[miniverse] {self.agent_id} heartbeat started → {MINIVERSE_URL}")

    def stop(self):
        self._running = False
        self.heartbeat("offline", "Shutting down")

    def heartbeat(self, state: AgentState, task: str):
        """Send a single heartbeat (also updates internal state)."""
        self._state = state
        self._task = task
        payload = {
            "agent": self.agent_id,
            "state": state,
            "task": task,
        }
        self._post("/api/heartbeat", payload)

    def speak(self, message: str):
        """Show a speech bubble (visible in world, not delivered to inboxes)."""
        self.heartbeat("speaking", message[:80])
        payload = {
            "agent": self.agent_id,
            "action": {"type": "speak", "message": message},
        }
        self._post("/api/act", payload)

    def message_agent(self, to: str, message: str):
        """Send a direct message to another agent (delivered to inbox)."""
        payload = {
            "agent": self.agent_id,
            "action": {"type": "message", "to": to, "message": message},
        }
        self._post("/api/act", payload)

    def check_inbox(self) -> list[dict]:
        """Drain and return messages from this agent's inbox."""
        try:
            r = requests.get(
                f"{MINIVERSE_URL}/api/inbox",
                params={"agent": self.agent_id},
                timeout=5,
            )
            r.raise_for_status()
            return r.json().get("messages", [])
        except Exception as e:
            print(f"[miniverse] inbox error: {e}")
            return []

    def list_agents(self) -> list[dict]:
        """Return list of all online agents in the world."""
        try:
            r = requests.get(f"{MINIVERSE_URL}/api/agents", timeout=5)
            r.raise_for_status()
            return r.json().get("agents", [])
        except Exception as e:
            print(f"[miniverse] list_agents error: {e}")
            return []

    # ── Internal ─────────────────────────────────────────────────────────────

    def _loop(self):
        while self._running:
            self._post("/api/heartbeat", {
                "agent": self.agent_id,
                "state": self._state,
                "task": self._task,
            })
            time.sleep(self.interval)

    def _post(self, path: str, payload: dict):
        try:
            r = requests.post(
                f"{MINIVERSE_URL}{path}",
                json=payload,
                timeout=5,
            )
            r.raise_for_status()
        except Exception as e:
            print(f"[miniverse] POST {path} error: {e}")


# ── Convenience singleton factory ─────────────────────────────────────────────

_bridges: dict[str, MiniverseBridge] = {}

def get_bridge(agent_id: str) -> MiniverseBridge:
    if agent_id not in _bridges:
        b = MiniverseBridge(agent_id)
        b.start()
        _bridges[agent_id] = b
    return _bridges[agent_id]
