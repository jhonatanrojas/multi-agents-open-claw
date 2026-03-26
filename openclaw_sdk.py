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
from typing import Any, Callable, Awaitable, Literal

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent

# Default path to the base OpenClaw config file.
OPENCLAW_CONFIG_PATH = Path(os.getenv("OPENCLAW_CONFIG", Path.home() / ".openclaw" / "openclaw.json"))
OPENCLAW_RUNTIME_PROFILE = os.getenv("OPENCLAW_PROFILE", "multi-agents-runtime-v2").strip()
OPENCLAW_RUNTIME_HOME = Path(os.getenv("OPENCLAW_RUNTIME_HOME", str(BASE_DIR / ".openclaw-runtime")))
_BASE_OPENCLAW_ROOT = OPENCLAW_CONFIG_PATH.parent

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
_SESSION_INDEX_RELATIVE = Path(".openclaw") / "agents"


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


# ── Fase 2: Clasificación nativa de fallos y eventos estructurados ───────────

FailureKind = Literal["infra", "format", "content", "blocked"]

_INFRA_SIGNALS = (
    "timeout",
    "connection reset",
    "connection refused",
    "gateway",
    "503",
    "502",
    "econnreset",
    "econnrefused",
    "network",
    "tls",
    "ssl",
)
_FORMAT_SIGNALS = (
    "json",
    "parse",
    "decode",
    "syntax",
    "unexpected token",
    "unterminated",
    "invalid json",
    "markdown fence",
)
_CONTENT_SIGNALS = (
    "no files",
    "empty content",
    "no content",
    "acceptance",
    "missing",
)
_BLOCKED_SIGNALS = (
    "blocker:",
    "question:",
    "awaiting",
    "waiting for",
    "blocked by",
)


def _infer_failure_kind(
    *,
    content: str,
    stderr_lines: list[str],
    returncode: int,
    exc: BaseException | None = None,
) -> FailureKind | None:
    """Classify the root cause of an agent run without relying on caller logic.

    Returns one of ``infra | format | content | blocked`` or ``None`` when the
    run succeeded (non-empty content and exit code 0).

    Rules (in priority order):
    1. Non-empty content + exit 0  → None (success, no failure)
    2. BLOCKED/QUESTION keywords in last stderr lines  → ``blocked``
    3. Infrastructure keywords (timeout, gateway…)  → ``infra``
    4. JSON/parse errors  → ``format``
    5. Empty content after successful exit  → ``content``
    6. Any other non-zero exit  → ``infra``
    """
    if content and returncode == 0:
        return None  # success

    needle = (" ".join(stderr_lines[-10:]) + " " + str(exc or "")).lower()

    if any(s in needle for s in _BLOCKED_SIGNALS):
        return "blocked"
    if any(s in needle for s in _INFRA_SIGNALS):
        return "infra"
    if any(s in needle for s in _FORMAT_SIGNALS):
        return "format"
    if not content:
        return "content"
    if returncode != 0:
        return "infra"
    return None


def _parse_stderr_events(stderr_lines: list[str], agent_id: str, t0: float) -> list[dict[str, Any]]:
    """Extract structured events from raw stderr lines.

    Each event has at minimum ``{ts, agent, kind, label}``.
    Tool-use events also include ``tool_name`` when detectable.
    This replaces the pattern of the orchestrator scanning ``stderr_lines`` as text.
    """
    events: list[dict[str, Any]] = []
    # Pattern to optionally detect tool name after tool_use label.
    _tool_name_re = re.compile(r"(?:tool[:\s_-]*(?:use|call|invoke|exec)[:\s_-]*)([\w_]+)", re.IGNORECASE)

    for i, line in enumerate(stderr_lines):
        kind = classify_progress(line)
        event: dict[str, Any] = {
            "seq": i,
            "agent": agent_id,
            "kind": kind,
            "label": line[:200],
        }
        if kind == "tool_use":
            m = _tool_name_re.search(line)
            if m:
                event["tool_name"] = m.group(1)
        events.append(event)
    return events


def _find_json_document(text: str) -> Any:
    """Return the first decodable JSON object found inside mixed CLI output."""
    text = (text or "").strip()
    if not text:
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch not in "[{":
            continue
        try:
            obj, _end = decoder.raw_decode(text[idx:])
            return obj
        except json.JSONDecodeError:
            continue
    return None


def _extract_cli_payload(stdout: str, stderr: str = "") -> dict[str, Any]:
    """Parse the top-level JSON envelope from ``openclaw agent --json``.

    Returns the parsed dict (with ``meta`` and ``payloads`` keys) or an
    empty dict on failure.
    """
    candidates = []
    for chunk in (stdout, stderr):
        text = (chunk or "").strip()
        if not text:
            continue
        parsed = _find_json_document(text)
        if isinstance(parsed, dict):
            candidates.append(parsed)

    if not candidates:
        log.warning(
            "openclaw CLI returned no parseable JSON envelope; stdout=%d bytes stderr=%d bytes",
            len(stdout or ""),
            len(stderr or ""),
        )
        return {}

    def _payload_container(payload: dict[str, Any]) -> dict[str, Any] | None:
        if isinstance(payload.get("result"), dict):
            return payload["result"]
        return payload

    def score(payload: dict[str, Any]) -> tuple[int, int]:
        container = _payload_container(payload) or payload
        has_payloads = 1 if isinstance(container.get("payloads"), list) and container.get("payloads") else 0
        has_direct = 1 if any(isinstance(container.get(key), str) and container.get(key).strip() for key in ("response", "content", "message", "text")) else 0
        nested_payloads = 1 if isinstance(payload.get("result"), dict) and isinstance(payload["result"].get("payloads"), list) and payload["result"].get("payloads") else 0
        return (has_payloads + nested_payloads, has_direct)

    return max(candidates, key=score)


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

    result = envelope.get("result")
    if isinstance(result, dict):
        nested = _extract_content(result)
        if nested:
            return nested

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


def _session_index_path(agent_id: str) -> Path:
    """Return the sessions index for an OpenClaw agent."""
    return Path.home() / _SESSION_INDEX_RELATIVE / agent_id / "sessions" / "sessions.json"


def _latest_session_file(agent_id: str) -> Path | None:
    """Return the most recent session log file for *agent_id* if available."""
    index_path = _session_index_path(agent_id)
    try:
        index_data = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        index_data = None

    if isinstance(index_data, dict):
        entry = index_data.get(f"agent:{agent_id}:main")
        if isinstance(entry, dict):
            session_file = entry.get("sessionFile")
            if isinstance(session_file, str) and session_file.strip():
                candidate = Path(session_file).expanduser()
                if candidate.exists():
                    return candidate

    sessions_dir = index_path.parent
    if sessions_dir.exists():
        candidates = sorted(sessions_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        if candidates:
            return candidates[0]
    return None


def _extract_last_assistant_text(session_file: Path) -> str:
    """Extract the latest assistant text from a JSONL OpenClaw session log."""
    try:
        lines = session_file.read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""

    for raw_line in reversed(lines):
        try:
            entry = json.loads(raw_line)
        except Exception:
            continue

        message = entry.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue

        content = message.get("content")
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text") or item.get("thinking")
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
            if chunks:
                return "\n".join(chunks)

        for key in ("text", "content", "message"):
            val = message.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()

    return ""


def _recover_content_from_session_log(agent_id: str) -> str:
    """Best-effort fallback when the CLI result content is unexpectedly empty."""
    session_file = _latest_session_file(agent_id)
    if not session_file:
        return ""
    return _extract_last_assistant_text(session_file)


def _profile_root(profile_name: str | None = None) -> Path | None:
    profile = (profile_name or OPENCLAW_RUNTIME_PROFILE).strip()
    if not profile:
        return None
    return OPENCLAW_RUNTIME_HOME / f".openclaw-{profile}"


def _profile_config_path(profile_name: str | None = None) -> Path:
    root = _profile_root(profile_name)
    return root / "openclaw.json" if root is not None else OPENCLAW_CONFIG_PATH


def _active_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    profile_cfg = _profile_config_path()
    if profile_cfg.exists():
        return profile_cfg
    return OPENCLAW_CONFIG_PATH


def _rewrite_openclaw_paths(value: Any, *, base_root: Path, profile_root: Path) -> Any:
    base_prefix = str(base_root)
    profile_prefix = str(profile_root)

    if isinstance(value, dict):
        return {
            key: _rewrite_openclaw_paths(inner, base_root=base_root, profile_root=profile_root)
            for key, inner in value.items()
        }
    if isinstance(value, list):
        return [_rewrite_openclaw_paths(item, base_root=base_root, profile_root=profile_root) for item in value]
    if isinstance(value, str) and value.startswith(base_prefix):
        suffix = value[len(base_prefix):].lstrip("/")
        return str(profile_root / suffix) if suffix else profile_prefix
    return value


def _ensure_runtime_profile(profile_name: str | None = None) -> Path | None:
    """Clone the base OpenClaw tree into a writable runtime profile if needed."""
    root = _profile_root(profile_name)
    if root is None:
        return None

    config_path = root / "openclaw.json"
    if config_path.exists():
        return root

    # First-use bootstrap: copy the base tree so agent/session state becomes writable.
    if not root.exists() and _BASE_OPENCLAW_ROOT.exists():
        shutil.copytree(_BASE_OPENCLAW_ROOT, root)
    else:
        root.mkdir(parents=True, exist_ok=True)

    if OPENCLAW_CONFIG_PATH.exists():
        try:
            base_cfg = json.loads(OPENCLAW_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Could not load base OpenClaw config for runtime profile bootstrap: %s", exc)
            return root

        if isinstance(base_cfg, dict):
            rewritten = _rewrite_openclaw_paths(base_cfg, base_root=_BASE_OPENCLAW_ROOT, profile_root=root)
            agents_list = rewritten.get("agents", {}).get("list", []) if isinstance(rewritten.get("agents"), dict) else []
            for agent in agents_list:
                agent_id = agent.get("id")
                if not agent_id:
                    continue
                sessions_dir = root / "agents" / agent_id / "sessions"
                if sessions_dir.exists():
                    shutil.rmtree(sessions_dir, ignore_errors=True)
                sessions_dir.mkdir(parents=True, exist_ok=True)
                (sessions_dir / "sessions.json").write_text("{}\n", encoding="utf-8")
            config_path.write_text(json.dumps(rewritten, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            log.info("Bootstrapped OpenClaw runtime profile at %s", root)
    return root


# Type alias for progress callbacks.
# Called with (agent_id, classification, raw_line, elapsed_sec).
ProgressCallback = Callable[[str, str, str, float], Awaitable[None] | None]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class AgentResult:
    """Thin wrapper so callers can do ``result.content``.

    Fase 2 additions:
    - ``failure_kind``: native classification (infra/format/content/blocked/None)
    - ``session_id``:   the session used (echoed back for traceability)
    - ``events``:       structured list of tool-use, thinking and writing events
                        extracted from stderr — no scraping needed by the orchestrator.
    """

    content: str
    raw_envelope: dict[str, Any]
    stderr_lines: list[str] = field(default_factory=list)
    elapsed_sec: float = 0.0
    timing: dict[str, Any] = field(default_factory=dict)
    # Fase 2 — contrato de interface ampliado
    failure_kind: FailureKind | None = None
    session_id: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)


class Agent:
    """Proxy for a single OpenClaw agent."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id

    async def execute(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        use_local: bool = False,
        thinking: str | None = None,
        on_progress: ProgressCallback | None = None,
        progress_throttle_sec: float = _PROGRESS_THROTTLE_SEC,
    ) -> AgentResult:
        """Run ``openclaw agent`` and return the result.

        If *on_progress* is provided it is called for each non-empty stderr
        line emitted by the CLI.  The callback receives
        ``(agent_id, classification, line, elapsed_sec)`` and may be sync or
        async.  Calls are throttled to at most once every
        *progress_throttle_sec* seconds to avoid Telegram spam.
        """
        runtime_profile = OPENCLAW_RUNTIME_PROFILE or None
        if runtime_profile:
            _ensure_runtime_profile(runtime_profile)

        cmd = ["openclaw"]
        if runtime_profile:
            cmd.extend(["--profile", runtime_profile])
        cmd.extend([
            "agent",
        ])
        if use_local:
            cmd.append("--local")
        cmd.extend([
            "--json",
            "--agent",
            self.agent_id,
            "--message",
            prompt,
        ])
        if session_id:
            cmd.extend(["--session-id", session_id])
        if thinking:
            cmd.extend(["--thinking", thinking])
        log.info(
            "Executing: openclaw%s%s agent --json --agent %s (prompt len=%d, session_id=%s, profile=%s)",
            " --local" if use_local else "",
            f" --profile {runtime_profile}" if runtime_profile else "",
            self.agent_id,
            len(prompt),
            session_id or "auto",
            runtime_profile or "default",
        )

        t0 = time.monotonic()
        env = os.environ.copy()
        env["HOME"] = str(OPENCLAW_RUNTIME_HOME)
        env.setdefault("OPENCLAW_PROFILE", runtime_profile or "")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
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

        # Drain stderr concurrently, but read stdout directly to avoid
        # competing consumers on the same stream.
        stderr_task = asyncio.ensure_future(_drain_stderr())

        assert proc.stdout is not None
        stdout_bytes = await proc.stdout.read()
        await proc.wait()
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

        envelope = _extract_cli_payload(stdout, "\n".join(stderr_lines))
        content = _extract_content(envelope)
        timing = _extract_timing(envelope)

        if not content:
            recovered = _recover_content_from_session_log(self.agent_id)
            if recovered:
                log.warning(
                    "Recovered empty CLI content for agent=%s from session log %s",
                    self.agent_id,
                    _latest_session_file(self.agent_id),
                )
                content = recovered

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
            # Fase 2: campos nativos de contrato
            failure_kind=_infer_failure_kind(
                content=content,
                stderr_lines=stderr_lines,
                returncode=proc.returncode or 0,
            ),
            session_id=session_id,
            events=_parse_stderr_events(stderr_lines, self.agent_id, t0),
        )


# ---------------------------------------------------------------------------
# OpenClaw config read/write
# ---------------------------------------------------------------------------


def load_openclaw_config(path: Path | None = None) -> dict[str, Any]:
    """Load and return the full ``openclaw.json`` config."""
    p = _active_config_path(path)
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
    if path is None and OPENCLAW_RUNTIME_PROFILE:
        _ensure_runtime_profile(OPENCLAW_RUNTIME_PROFILE)
    p = _active_config_path(path)
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
