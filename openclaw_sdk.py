"""
openclaw_sdk.py — Thin async wrapper around the ``openclaw`` CLI.

The CLI's ``--json`` output envelope looks like::

    {
      "meta": { ... },
      "payloads": [
        { "text": "<actual agent response>" }
      ]
    }

``result.content`` exposes ``payloads[0].text`` so callers can parse it
directly as JSON (or treat it as plain text for the review phase).

Progress lines from stderr are streamed in real-time via an optional
callback so the orchestrator can log them, notify Telegram, and update
heartbeats while the agent is working.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable

log = logging.getLogger(__name__)

# Default path to the OpenClaw config file.
OPENCLAW_CONFIG_PATH = Path(os.getenv("OPENCLAW_CONFIG", Path.home() / ".openclaw" / "openclaw.json"))

# Minimum seconds between Telegram-bound progress updates (avoid spam).
_PROGRESS_THROTTLE_SEC = 15.0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Patterns commonly seen in openclaw stderr progress lines.
_TOOL_USE_RE = re.compile(r"tool[:\s_-]*(use|call|invoke|exec)", re.IGNORECASE)
_THINKING_RE = re.compile(r"(think|reason|plann|analy)", re.IGNORECASE)
_WRITING_RE = re.compile(r"(writ|creat|generat|build)", re.IGNORECASE)
_READING_RE = re.compile(r"(read|fetch|load|search|scan)", re.IGNORECASE)


def classify_progress(line: str) -> str:
    """Return a short human label for a stderr progress line."""
    if _TOOL_USE_RE.search(line):
        return "tool_use"
    if _THINKING_RE.search(line):
        return "thinking"
    if _WRITING_RE.search(line):
        return "writing"
    if _READING_RE.search(line):
        return "reading"
    return "working"


def _extract_cli_payload(stdout: str, stderr: str = "") -> dict[str, Any]:
    """Parse the top-level JSON envelope from ``openclaw agent --json``.

    Returns the parsed dict (with ``meta`` and ``payloads`` keys) or an
    empty dict on failure.
    """
    text = (stdout or "").strip()
    if not text:
        log.warning("openclaw CLI returned empty stdout; stderr=%s", stderr[:300])
        return {}
    try:
        return json.loads(text)  # type: ignore[no-any-return]
    except json.JSONDecodeError as exc:
        log.warning("Failed to parse CLI JSON envelope: %s — raw[:200]=%s", exc, text[:200])
        return {}


def _extract_content(envelope: dict[str, Any]) -> str:
    """Pull the useful text out of the CLI envelope.

    Priority order:
    1. ``payloads[0].text`` — the documented path.
    2. ``content`` (legacy / future-proofing).
    3. ``message`` (legacy).
    4. Empty string as last resort.
    """
    payloads = envelope.get("payloads")
    if isinstance(payloads, list) and payloads:
        first = payloads[0]
        if isinstance(first, dict) and "text" in first:
            return first["text"]
        if isinstance(first, str):
            return first

    # Fallbacks
    for key in ("content", "message"):
        val = envelope.get(key)
        if isinstance(val, str) and val:
            return val

    log.warning("Could not extract content from envelope keys=%s", sorted(envelope.keys()))
    return ""


def _extract_timing(envelope: dict[str, Any]) -> dict[str, Any]:
    """Extract timing metadata from the CLI envelope if present."""
    meta = envelope.get("meta", {})
    timing: dict[str, Any] = {}
    for key in ("duration_ms", "tokens_in", "tokens_out", "model", "provider"):
        if key in meta:
            timing[key] = meta[key]
    return timing


# Type alias for progress callbacks.
# Called with (agent_id, classification, raw_line, elapsed_sec).
ProgressCallback = Callable[[str, str, str, float], Awaitable[None] | None]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class AgentResult:
    """Thin wrapper so callers can do ``result.content``."""

    content: str
    raw_envelope: dict[str, Any]
    stderr_lines: list[str] = field(default_factory=list)
    elapsed_sec: float = 0.0
    timing: dict[str, Any] = field(default_factory=dict)


class Agent:
    """Proxy for a single OpenClaw agent."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id

    async def execute(
        self,
        prompt: str,
        *,
        on_progress: ProgressCallback | None = None,
        progress_throttle_sec: float = _PROGRESS_THROTTLE_SEC,
    ) -> AgentResult:
        """Run ``openclaw agent --local --json`` and return the result.

        If *on_progress* is provided it is called for each non-empty stderr
        line emitted by the CLI.  The callback receives
        ``(agent_id, classification, line, elapsed_sec)`` and may be sync or
        async.  Calls are throttled to at most once every
        *progress_throttle_sec* seconds to avoid Telegram spam.
        """
        cmd = [
            "openclaw",
            "agent",
            "--local",
            "--json",
            "--agent",
            self.agent_id,
            "--message",
            prompt,
        ]
        log.info(
            "Executing: openclaw agent --local --json --agent %s (prompt len=%d)",
            self.agent_id,
            len(prompt),
        )

        t0 = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Stream stderr in real-time while stdout is buffered.
        stderr_lines: list[str] = []
        last_progress_ts = 0.0

        async def _drain_stderr() -> None:
            nonlocal last_progress_ts
            assert proc.stderr is not None
            while True:
                raw = await proc.stderr.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip()
                if not line:
                    continue
                stderr_lines.append(line)
                elapsed = time.monotonic() - t0
                classification = classify_progress(line)
                log.debug(
                    "[%s] %.1fs %s: %s",
                    self.agent_id,
                    elapsed,
                    classification,
                    line[:120],
                )

                if on_progress is not None:
                    now = time.monotonic()
                    if (now - last_progress_ts) >= progress_throttle_sec:
                        last_progress_ts = now
                        try:
                            rv = on_progress(self.agent_id, classification, line, elapsed)
                            if asyncio.iscoroutine(rv):
                                await rv
                        except Exception as cb_exc:
                            log.warning("Progress callback error: %s", cb_exc)

        # Run stderr drain concurrently with stdout read.
        stderr_task = asyncio.ensure_future(_drain_stderr())

        stdout_bytes, _ = await proc.communicate()
        await stderr_task  # ensure all stderr lines are captured

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        elapsed = time.monotonic() - t0

        if proc.returncode != 0:
            log.error(
                "openclaw agent exited %d for agent=%s (%.1fs); last stderr=%s",
                proc.returncode,
                self.agent_id,
                elapsed,
                stderr_lines[-1][:200] if stderr_lines else "N/A",
            )

        envelope = _extract_cli_payload(stdout, "\n".join(stderr_lines[-5:]))
        content = _extract_content(envelope)
        timing = _extract_timing(envelope)

        if not content:
            log.error(
                "Empty content after extraction for agent=%s (%.1fs); "
                "envelope_keys=%s stdout[:200]=%s last_stderr=%s",
                self.agent_id,
                elapsed,
                sorted(envelope.keys()) if envelope else "N/A",
                stdout[:200],
                stderr_lines[-3:] if stderr_lines else "N/A",
            )

        log.info(
            "Agent %s finished in %.1fs (content_len=%d, stderr_lines=%d)",
            self.agent_id,
            elapsed,
            len(content),
            len(stderr_lines),
        )

        # Always fire a final progress event so the caller knows it's done.
        if on_progress is not None:
            try:
                summary = f"Completado en {elapsed:.0f}s — {len(content)} chars"
                rv = on_progress(self.agent_id, "done", summary, elapsed)
                if asyncio.iscoroutine(rv):
                    await rv
            except Exception as cb_exc:
                log.warning("Final progress callback error: %s", cb_exc)

        return AgentResult(
            content=content,
            raw_envelope=envelope,
            stderr_lines=stderr_lines,
            elapsed_sec=elapsed,
            timing=timing,
        )


# ---------------------------------------------------------------------------
# OpenClaw config read/write
# ---------------------------------------------------------------------------


def load_openclaw_config(path: Path | None = None) -> dict[str, Any]:
    """Load and return the full ``openclaw.json`` config."""
    p = path or OPENCLAW_CONFIG_PATH
    if not p.exists():
        log.warning("OpenClaw config not found at %s", p)
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        log.error("Failed to read openclaw config: %s", exc)
        return {}


def save_openclaw_config(config: dict[str, Any], path: Path | None = None) -> None:
    """Write *config* back to ``openclaw.json`` with a backup."""
    p = path or OPENCLAW_CONFIG_PATH
    # Safety backup before writing.
    if p.exists():
        backup = p.with_suffix(".json.bak")
        shutil.copy2(p, backup)
    p.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log.info("OpenClaw config saved to %s", p)


def get_available_models(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return a flat list of all models available across all providers.

    Each entry: ``{"qualified": "provider/model_id", "provider": ..., "name": ..., ...}``
    """
    cfg = config or load_openclaw_config()
    models: list[dict[str, Any]] = []

    # 1. Models declared in providers (with full metadata).
    providers = cfg.get("models", {}).get("providers", {})
    for provider_id, provider_cfg in providers.items():
        for m in provider_cfg.get("models", []):
            model_id = m.get("id", "")
            qualified = f"{provider_id}/{model_id}"
            models.append({
                "qualified": qualified,
                "provider": provider_id,
                "model_id": model_id,
                "name": m.get("name", model_id),
                "reasoning": m.get("reasoning", False),
                "context_window": m.get("contextWindow"),
                "max_tokens": m.get("maxTokens"),
                "source": "provider",
            })

    # 2. Models referenced in agents.defaults.models (may add extras).
    defaults_models = cfg.get("agents", {}).get("defaults", {}).get("models", {})
    known_qualified = {m["qualified"] for m in models}
    for qualified, meta in defaults_models.items():
        if qualified not in known_qualified:
            parts = qualified.split("/", 1)
            provider = parts[0] if len(parts) > 1 else "unknown"
            model_id = parts[1] if len(parts) > 1 else qualified
            models.append({
                "qualified": qualified,
                "provider": provider,
                "model_id": model_id,
                "name": meta.get("alias", model_id),
                "source": "defaults",
            })

    return models


def get_agent_models(config: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Return current model assignment per agent.

    Returns ``{"arch": {"model": "nvidia/z-ai/glm5", ...}, ...}``
    """
    cfg = config or load_openclaw_config()
    agents_list = cfg.get("agents", {}).get("list", [])
    defaults = cfg.get("agents", {}).get("defaults", {})
    default_model = defaults.get("model", {}).get("primary", "")
    fallbacks = defaults.get("model", {}).get("fallbacks", [])

    result: dict[str, dict[str, Any]] = {}
    for agent in agents_list:
        aid = agent.get("id", "")
        if not aid:
            continue
        result[aid] = {
            "model": agent.get("model", default_model),
            "name": agent.get("name", aid),
            "workspace": agent.get("workspace"),
            "is_default": "model" not in agent,
        }

    # Add default fallbacks info.
    result["_defaults"] = {
        "primary": default_model,
        "fallbacks": fallbacks,
    }
    return result


def set_agent_model(
    agent_id: str,
    model_qualified: str,
    config: dict[str, Any] | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Change the model for *agent_id* in ``openclaw.json`` and save.

    *model_qualified* must be in ``provider/model_id`` format
    (e.g. ``nvidia/z-ai/glm5``).

    Returns the updated agent entry.
    """
    cfg = config if config is not None else load_openclaw_config(path)
    agents_list = cfg.get("agents", {}).get("list", [])

    # Validate model exists in known models.
    available = {m["qualified"] for m in get_available_models(cfg)}
    if model_qualified not in available:
        raise ValueError(
            f"Modelo '{model_qualified}' no está configurado en OpenClaw. "
            f"Modelos disponibles: {sorted(available)}"
        )

    # Find and update the agent.
    updated = None
    for agent in agents_list:
        if agent.get("id") == agent_id:
            agent["model"] = model_qualified
            updated = agent
            break

    if updated is None:
        raise ValueError(f"Agente '{agent_id}' no encontrado en la configuración de OpenClaw.")

    save_openclaw_config(cfg, path)
    return updated


def set_default_model(
    model_qualified: str,
    fallbacks: list[str] | None = None,
    config: dict[str, Any] | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Change the default primary model (and optionally fallbacks).

    Returns the updated defaults.model block.
    """
    cfg = config if config is not None else load_openclaw_config(path)
    available = {m["qualified"] for m in get_available_models(cfg)}

    if model_qualified not in available:
        raise ValueError(
            f"Modelo '{model_qualified}' no está configurado en OpenClaw. "
            f"Modelos disponibles: {sorted(available)}"
        )

    if fallbacks:
        bad = [f for f in fallbacks if f not in available]
        if bad:
            raise ValueError(f"Fallback(s) no disponibles: {bad}")

    defaults = cfg.setdefault("agents", {}).setdefault("defaults", {})
    model_block = defaults.setdefault("model", {})
    model_block["primary"] = model_qualified
    if fallbacks is not None:
        model_block["fallbacks"] = fallbacks

    save_openclaw_config(cfg, path)
    return model_block


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class OpenClawClient:
    """Async context-manager client that wraps the ``openclaw`` CLI."""

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    # -- context manager -----------------------------------------------------

    @classmethod
    def connect(cls) -> "OpenClawClient":
        """Return an instance usable as ``async with OpenClawClient.connect() as c:``."""
        return cls()

    async def __aenter__(self) -> "OpenClawClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        pass

    # -- agent registry ------------------------------------------------------

    def get_agent(self, agent_id: str) -> Agent:
        """Return (or create) an :class:`Agent` proxy for *agent_id*."""
        if agent_id not in self._agents:
            self._agents[agent_id] = Agent(agent_id)
        return self._agents[agent_id]

    # -- config helpers (convenience pass-throughs) --------------------------

    @staticmethod
    def available_models() -> list[dict[str, Any]]:
        return get_available_models()

    @staticmethod
    def agent_models() -> dict[str, dict[str, Any]]:
        return get_agent_models()

    @staticmethod
    def set_agent_model(agent_id: str, model_qualified: str) -> dict[str, Any]:
        return set_agent_model(agent_id, model_qualified)

    @staticmethod
    def set_default_model(model_qualified: str, fallbacks: list[str] | None = None) -> dict[str, Any]:
        return set_default_model(model_qualified, fallbacks)
