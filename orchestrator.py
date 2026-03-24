#!/usr/bin/env python3
"""
orchestrator.py - Dev Squad Multi-Agent Orchestrator
----------------------------------------------------
Coordinates ARCH, BYTE, and PIXEL with OpenClaw, shared memory, repository
bootstrap, stack-aware skill routing, Telegram notifications, and Miniverse.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import sys
from pathlib import Path
from typing import Any

from openclaw_sdk import OpenClawClient

from coordination import (
    RepositoryApprovalRequired,
    RepositoryBootstrapError,
    bootstrap_repository,
    build_task_skill_profile,
    send_telegram_message,
    write_agent_workspace_files,
)
from shared_state import BASE_DIR, ensure_memory_file, load_memory, save_memory
from skills.shared.miniverse_bridge import get_bridge

OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR = BASE_DIR / "logs"
PROJECTS_DIR = BASE_DIR / "projects"
AGENT_IDS = ("arch", "byte", "pixel")


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.datetime.utcnow().isoformat()


def ensure_runtime_dirs() -> None:
    """Create runtime directories used by the orchestrator."""
    for path in (OUTPUT_DIR, LOG_DIR, PROJECTS_DIR, BASE_DIR / "shared", BASE_DIR / "workspaces"):
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


def log_event(message: str, agent: str = "system") -> None:
    """Append a log event to shared memory."""
    mem = load_memory()
    mem.setdefault("log", [])
    mem["log"].append(
        {
            "ts": utc_now(),
            "agent": agent,
            "msg": message,
        }
    )
    mem.setdefault("project", {})
    mem["project"]["updated_at"] = utc_now()
    save_memory(mem)


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


def record_blocker(message: str, source: str = "system") -> None:
    """Store a blocker in shared memory."""
    mem = load_memory()
    mem.setdefault("blockers", [])
    mem["blockers"].append(
        {
            "ts": utc_now(),
            "source": source,
            "msg": message,
        }
    )
    save_memory(mem)


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
    arch_messages: list[dict[str, Any]] = []

    for agent_id, bridge in bridges.items():
        try:
            inbox = bridge.check_inbox()
        except Exception as exc:
            log_event(f"Inbox read failed for {agent_id}: {exc}", "system")
            continue

        for raw in inbox or []:
            normalized = normalize_message(agent_id, raw)
            mem.setdefault("messages", [])
            mem["messages"].append(normalized)
            log_event(
                f"Message for {agent_id} from {normalized['from']}: {normalized['message']}",
                normalized["from"],
            )

            message_upper = normalized["message"].upper()
            if "BLOCKER:" in message_upper:
                record_blocker(normalized["message"], normalized["from"])
                try:
                    send_telegram_message(f"BLOCKER from {normalized['from']}: {normalized['message']}")
                except Exception as exc:
                    log_event(f"Telegram notify failed: {exc}", "system")

            if agent_id == "arch" and normalized["from"] in {"byte", "pixel"}:
                arch_messages.append(normalized)

    save_memory(mem)

    if not arch_messages:
        return

    arch = client.get_agent("arch")
    result = await arch.execute(
        COORDINATION_PROMPT.format(
            messages=json.dumps(arch_messages, indent=2, ensure_ascii=False),
        )
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


# ── Phase 1: Planning ──────────────────────────────────────────────────────────

PLANNER_PROMPT = """
You are ARCH, the senior project coordinator of a multi-agent engineering team.
Analyze the project brief and produce a structured JSON plan that can be
executed by BYTE and PIXEL.

Requirements:
- Decompose the work into atomic tasks with clear acceptance criteria.
- Assign code-focused work to BYTE and UI/design work to PIXEL.
- When the stack is obvious, make the planned tasks stack-aware
  (for example Laravel/PHP, Node/Express, React/TypeScript, DevOps, docs).
- Include optional "skills" and "workspace_notes" arrays for each task when
  they help the downstream agent specialize.

Respond ONLY with valid JSON. No markdown fences.

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

PROJECT REQUEST: {project_brief}
"""

COORDINATION_PROMPT = """
You are ARCH, coordinating the team.
Respond to the incoming messages from BYTE and PIXEL.

Return valid JSON only with this schema:
{{
  "responses": [
    {{
      "to": "byte|pixel",
      "message": "short, actionable reply",
      "in_reply_to": "optional message id"
    }}
  ]
}}

MESSAGES:
{messages}
"""

BYTE_TASK_PROMPT = """
You are BYTE, a senior full-stack engineer. Implement the following task.
Read the project context and the workspace files before coding.

PROJECT CONTEXT:
{context}

REPO CONTEXT:
{repo_context}

SKILL PROFILE:
- Family: {skill_family}
- Focus: {skill_focus}
- Skills:
{skill_list}
- Instructions:
{instruction_list}

WORKSPACE FILES:
- Markdown context: {workspace_md_path}
- JSON context: {workspace_json_path}
- Progress JSON: {progress_path}

YOUR TASK:
ID: {task_id}
Title: {title}
Description: {description}
Acceptance Criteria:
{acceptance}

COORDINATION PROTOCOL:
- If you are blocked, DM ARCH with `BLOCKER:{task_id} <issue>`.
- If you need clarification, DM ARCH with `QUESTION:{task_id} <question>`.
- Keep the progress JSON updated when your environment allows writes.

Output the complete file contents in this JSON format:
{{
  "files": [
    {{"path": "relative/path/file.py", "content": "..."}}
  ],
  "notes": "..."
}}
Respond with valid JSON only.
"""

PIXEL_TASK_PROMPT = """
You are PIXEL, a senior UI/UX designer and frontend engineer. Create the
design artifacts for the following task.
Read the project context and the workspace files before designing.

PROJECT CONTEXT:
{context}

REPO CONTEXT:
{repo_context}

SKILL PROFILE:
- Family: {skill_family}
- Focus: {skill_focus}
- Skills:
{skill_list}
- Instructions:
{instruction_list}

WORKSPACE FILES:
- Markdown context: {workspace_md_path}
- JSON context: {workspace_json_path}
- Progress JSON: {progress_path}

YOUR TASK:
ID: {task_id}
Title: {title}
Description: {description}
Acceptance Criteria:
{acceptance}

COORDINATION PROTOCOL:
- If you are blocked, DM ARCH with `BLOCKER:{task_id} <issue>`.
- If you need clarification, DM ARCH with `QUESTION:{task_id} <question>`.
- Keep the progress JSON updated when your environment allows writes.

Output design artifacts in this JSON format:
{{
  "files": [
    {{"path": "design/{task_id}/component.tsx", "content": "..."}},
    {{"path": "design/{task_id}/spec.md", "content": "..."}}
  ],
  "notes": "..."
}}
Respond with valid JSON only.
"""

REVIEW_PROMPT = """
You are ARCH. All tasks are complete. Review the project outcome below and
produce a final delivery summary.

MEMORY STATE:
{memory}

Write a markdown summary (## Delivery Summary) covering:
1. What was built
2. Files produced (list them)
3. How to run the project
4. Known limitations or next steps
"""


async def plan_project(client: OpenClawClient, brief: str) -> dict[str, Any]:
    """Ask ARCH to produce a plan and persist it to shared memory."""
    arch = client.get_agent("arch")
    arch_bridge = get_bridge("arch")

    arch_bridge.heartbeat("thinking", f"Planning: {brief[:60]}")
    update_agent_status("arch", "thinking", "initial_planning")
    log_event(f"Planning project: {brief}", "arch")

    result = await arch.execute(PLANNER_PROMPT.format(project_brief=brief))

    try:
        plan_json = json.loads(result.content)
    except json.JSONDecodeError as exc:
        update_agent_status("arch", "error", "planning_failed")
        log_event(f"Planner returned invalid JSON: {exc}", "arch")
        raise RuntimeError("Planner returned invalid JSON") from exc

    mem = load_memory()
    project_patch = plan_json.get("project", {})
    mem.setdefault("project", {})
    mem["project"].update(
        {
            **project_patch,
            "status": "planned",
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
    )
    mem["plan"] = plan_json.get("plan", {"phases": []})
    mem["milestones"] = plan_json.get("milestones", [])

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
        f"Plan ready! {len(all_tasks)} tasks across {len(mem['plan'].get('phases', []))} phases."
    )
    log_event(f"Plan created: {len(all_tasks)} tasks", "arch")
    update_agent_status("arch", "idle", None)
    return plan_json


# ── Phase 2: Execution ─────────────────────────────────────────────────────────


async def execute_task(
    client: OpenClawClient,
    task: dict[str, Any],
    project_context: str,
    repo_state: dict[str, Any],
) -> None:
    """Execute one task with the assigned agent and persist progress."""
    agent_id = task["agent"]
    task_id = task["id"]
    bridge = get_bridge(agent_id)
    mem = load_memory()
    project = mem.get("project", {})
    output_dir = resolve_path(project.get("output_dir"), OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    skill_profile = task.get("skill_profile") or build_task_skill_profile(project, task)
    workspace_files = write_agent_workspace_files(agent_id, task, project, skill_profile, repo_state)
    progress_path = workspace_files["progress_path"]

    update_agent_status(agent_id, "working", task_id)
    bridge.heartbeat("working", f"Task {task_id}: {task['title'][:50]}")
    bridge.speak(f"Starting {task_id}: {task['title']}")
    log_event(f"Starting task {task_id}", agent_id)

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
        "Task started",
        status="in_progress",
        skill_profile=skill_profile,
        repo_state=repo_state,
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

    agent = client.get_agent(agent_id)

    try:
        result = await agent.execute(prompt)
    except Exception as exc:
        append_progress_event(progress_path, "error", f"Agent execution failed: {exc}", status="error")
        mem = load_memory()
        for t in mem.get("tasks", []):
            if t.get("id") == task_id:
                t["status"] = "error"
                t["error"] = str(exc)
        save_memory(mem)
        bridge.heartbeat("error", f"Error on {task_id}")
        log_event(f"Task {task_id} FAILED: agent execution error {exc}", agent_id)
        update_agent_status(agent_id, "error", task_id)
        return

    try:
        data = json.loads(result.content)
    except json.JSONDecodeError:
        append_progress_event(
            progress_path,
            "error",
            "Invalid JSON response from agent",
            status="error",
            raw_response=result.content[:1000],
        )
        mem = load_memory()
        for t in mem.get("tasks", []):
            if t.get("id") == task_id:
                t["status"] = "error"
                t["error"] = "Invalid JSON response"
        save_memory(mem)
        bridge.heartbeat("error", f"Error on {task_id}")
        log_event(f"Task {task_id} FAILED: bad JSON response", agent_id)
        update_agent_status(agent_id, "error", task_id)
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
            "Task completed successfully",
            status="done",
            files=files_written,
            notes=data.get("notes", ""),
        )

        bridge.heartbeat("idle", f"Done: {task_id}")
        bridge.speak(f"Completed {task_id}: {len(files_written)} file(s) written.")
        log_event(f"Task {task_id} done. Files: {files_written}", agent_id)
        update_agent_status(agent_id, "idle", None)
        try:
            send_telegram_message(
                f"Task complete: {task_id} ({agent_id}) - {len(files_written)} file(s) written."
            )
        except Exception as exc:
            log_event(f"Telegram notify failed: {exc}", "system")
    except Exception as exc:
        append_progress_event(progress_path, "error", f"File write failed: {exc}", status="error")
        mem = load_memory()
        for t in mem.get("tasks", []):
            if t.get("id") == task_id:
                t["status"] = "error"
                t["error"] = str(exc)
        save_memory(mem)
        bridge.heartbeat("error", f"Error on {task_id}")
        log_event(f"Task {task_id} FAILED: file write error {exc}", agent_id)
        update_agent_status(agent_id, "error", task_id)


# ── Phase 3: Final Review ──────────────────────────────────────────────────────


async def final_review(client: OpenClawClient) -> None:
    """Ask ARCH for the delivery summary and persist it."""
    arch = client.get_agent("arch")
    arch_bridge = get_bridge("arch")

    arch_bridge.heartbeat("thinking", "Reviewing all completed work")
    mem = load_memory()
    result = await arch.execute(REVIEW_PROMPT.format(memory=json.dumps(mem, indent=2, ensure_ascii=False)))

    project_output_dir = resolve_path(mem.get("project", {}).get("output_dir"), OUTPUT_DIR)
    project_output_dir.mkdir(parents=True, exist_ok=True)
    delivery_path = project_output_dir / "DELIVERY.md"
    delivery_path.write_text(result.content, encoding="utf-8")

    if delivery_path.resolve() != (OUTPUT_DIR / "DELIVERY.md").resolve():
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "DELIVERY.md").write_text(result.content, encoding="utf-8")

    mem = load_memory()
    mem.setdefault("project", {})
    mem["project"]["status"] = "delivered"
    mem["project"]["updated_at"] = utc_now()
    mem.setdefault("milestones", [])
    mem["milestones"].append(f"Project delivered at {utc_now()}")
    save_memory(mem)

    arch_bridge.speak("Project delivered! See DELIVERY.md")
    log_event("Project delivered. See DELIVERY.md", "arch")
    try:
        send_telegram_message(f"Project delivered: {mem.get('project', {}).get('name') or 'unnamed project'}")
    except Exception as exc:
        log_event(f"Telegram notify failed: {exc}", "system")

    print("\n" + "=" * 60)
    print(result.content)
    print("=" * 60)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Run the Dev Squad orchestrator.")
    parser.add_argument("brief", nargs="*", help="Project brief")
    parser.add_argument("--repo-url", dest="repo_url", help="Existing repository URL to clone")
    parser.add_argument("--repo-name", dest="repo_name", help="Repository name for local creation")
    parser.add_argument("--branch", dest="branch", help="Branch name to create or switch to")
    parser.add_argument(
        "--allow-init-repo",
        action="store_true",
        help="Initialize a local git repository when no repo URL is provided",
    )
    return parser.parse_args()


async def main(args: argparse.Namespace) -> None:
    """Run the full orchestration lifecycle."""
    project_brief = " ".join(args.brief).strip() or (
        "Build a simple TODO app with React + TypeScript frontend, "
        "FastAPI backend, SQLite database, REST API, and a clean UI."
    )

    ensure_runtime_dirs()
    ensure_memory_file()
    print(f"\nDev Squad starting - Project: {project_brief}\n")

    for agent_id in AGENT_IDS:
        bridge = get_bridge(agent_id)
        bridge.heartbeat("idle", "Warming up")

    async with OpenClawClient.connect() as client:
        print("Phase 1: Planning...")
        try:
            await plan_project(client, project_brief)
        except Exception as exc:
            log_event(f"Planning failed: {exc}", "arch")
            try:
                send_telegram_message(f"Planning failed: {exc}")
            except Exception:
                pass
            print(f"Planning failed: {exc}")
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
                f"Repository ready: {repo_state.get('action')} -> {repo_state.get('repo_path')} @ {repo_state.get('branch')}",
                "arch",
            )
            try:
                send_telegram_message(
                    f"Repository ready: {repo_state.get('action')} -> {repo_state.get('repo_path')} @ {repo_state.get('branch')}"
                )
            except Exception as exc:
                log_event(f"Telegram notify failed: {exc}", "system")
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
            log_event(f"Repository approval required: {exc}", "arch")
            try:
                send_telegram_message(f"Repository approval required: {exc}")
            except Exception:
                pass
            print(str(exc))
            return
        except RepositoryBootstrapError as exc:
            log_event(f"Repository bootstrap failed: {exc}", "arch")
            try:
                send_telegram_message(f"Repository bootstrap failed: {exc}")
            except Exception:
                pass
            print(f"Repository bootstrap failed: {exc}")
            return

        print("\nPhase 2: Executing tasks...")
        mem = load_memory()
        completed_ids: set[str] = set()
        pending_tasks = [task for task in mem.get("tasks", [])]
        max_rounds = len(pending_tasks) + 8
        rounds = 0

        project_context = build_project_context(mem, repo_state)

        while pending_tasks and rounds < max_rounds:
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
                pending_tasks = [task for task in mem.get("tasks", []) if task.get("status") not in ("done", "error")]
                completed_ids = {task["id"] for task in mem.get("tasks", []) if task.get("status") == "done"}
                continue

            byte_tasks = [task for task in ready if task["agent"] == "byte"]
            pixel_tasks = [task for task in ready if task["agent"] == "pixel"]

            coros = []
            if byte_tasks:
                coros.append(execute_task(client, byte_tasks[0], project_context, repo_state))
            if pixel_tasks:
                coros.append(execute_task(client, pixel_tasks[0], project_context, repo_state))
            if not coros and ready:
                coros.append(execute_task(client, ready[0], project_context, repo_state))

            await asyncio.gather(*coros)
            await relay_team_messages(client)

            mem = load_memory()
            pending_tasks = [task for task in mem.get("tasks", []) if task.get("status") not in ("done", "error")]
            completed_ids = {task["id"] for task in mem.get("tasks", []) if task.get("status") == "done"}

        print("\nPhase 3: Final review...")
        await relay_team_messages(client)
        await final_review(client)

    print("\nDev Squad done. Check ./output/ for all files.")


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
