from __future__ import annotations

import json
import os
import re
import subprocess
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from shared_state import BASE_DIR

PROJECTS_ROOT = BASE_DIR / "projects"
WORKSPACES_ROOT = BASE_DIR / "workspaces"
WORKSPACE_NAMES = {
    "arch": "coordinator",
    "byte": "programmer",
    "pixel": "designer",
}


class RepositoryBootstrapError(RuntimeError):
    """Raised when repository bootstrap cannot continue safely."""


class RepositoryApprovalRequired(RuntimeError):
    """Raised when the coordinator needs repo approval/details via Telegram."""


@dataclass
class TaskSkillProfile:
    family: str
    stack: str
    skills: list[str]
    instructions: list[str]
    prompt_focus: str


def slugify(value: str | None) -> str:
    """Convert a string into a filesystem and branch friendly slug."""
    raw = (value or "project").strip().lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw)
    raw = re.sub(r"-+", "-", raw).strip("-")
    return raw or "project"


def workspace_root_for_agent(agent_id: str) -> Path:
    """Return the workspace directory that OpenClaw mounts for an agent."""
    return WORKSPACES_ROOT / WORKSPACE_NAMES.get(agent_id, agent_id)


def _project_text(project: dict[str, Any], task: dict[str, Any]) -> str:
    tech_stack = project.get("tech_stack", {}) or {}
    parts = [
        project.get("name") or "",
        project.get("description") or "",
        " ".join(str(v) for v in tech_stack.values()),
        task.get("title") or "",
        task.get("description") or "",
        " ".join(task.get("acceptance", []) or []),
    ]
    return " ".join(parts).lower()


def _stack_from_project(project: dict[str, Any], task: dict[str, Any]) -> str:
    text = _project_text(project, task)
    tech_stack = project.get("tech_stack", {}) or {}
    tech_blob = " ".join(str(v).lower() for v in tech_stack.values())

    if any(token in text for token in ("laravel", "php", "artisan", "eloquent")):
        return "laravel"
    if any(token in text for token in ("express", "node", "fastify", "nestjs", "npm")):
        return "node-express"
    if any(token in text for token in ("react", "vite", "next.js", "nextjs", "frontend", "typescript")):
        return "frontend"
    if any(token in text for token in ("devops", "apache", "nginx", "backup", "health check", "cron", "deployment")):
        return "devops"
    if any(token in text for token in ("documentation", "docs", "markdown", "manual", "guide")):
        return "documentation"

    if "laravel" in tech_blob or "php" in tech_blob:
        return "laravel"
    if "express" in tech_blob or "node" in tech_blob:
        return "node-express"
    if "react" in tech_blob:
        return "frontend"

    return "general"


def _base_skills_for_stack(stack: str, agent_id: str) -> tuple[list[str], list[str], str]:
    if stack == "laravel":
        return (
            ["PHP", "Laravel", "Artisan", "Eloquent", "Composer", "Migrations", "Testing"],
            [
                "Use Laravel conventions and clean service boundaries.",
                "Prefer Eloquent models, migrations, and reusable services.",
                "If authentication is involved, plan the auth flow before coding.",
            ],
            "Laravel specialist",
        )

    if stack == "node-express":
        return (
            ["Node.js", "Express", "REST APIs", "Middleware", "NPM", "Testing"],
            [
                "Use Express routing, middleware, and clear module boundaries.",
                "Keep API contracts explicit and document request/response shapes.",
                "Prefer TypeScript when the repo already uses it.",
            ],
            "Node/Express specialist",
        )

    if stack == "frontend":
        return (
            ["React", "TypeScript", "Accessibility", "Responsive UI", "Component Design"],
            [
                "Preserve existing design language and keep the UI accessible.",
                "Break complex UI into reusable components and keep state predictable.",
                "If the project already uses a design system, extend it instead of replacing it.",
            ],
            "Frontend specialist",
        )

    if stack == "devops":
        return (
            ["Bash", "Apache", "Nginx", "Cron", "Backups", "Health Checks", "Deployment"],
            [
                "Prefer idempotent scripts and clear operational runbooks.",
                "Validate ports, health checks, and backup/restore flows explicitly.",
                "Document any required secrets or environment variables.",
            ],
            "DevOps specialist",
        )

    if stack == "documentation":
        return (
            ["Markdown", "Information Architecture", "User Guides", "Installation Flows"],
            [
                "Keep documentation structured, searchable, and task-oriented.",
                "Include install, usage, troubleshooting, and examples where relevant.",
                "Prefer clear headings and concise procedural steps.",
            ],
            "Documentation specialist",
        )

    return (
        ["Task Decomposition", "Repository Hygiene", "Testing", "Coordination"],
        [
            "Inspect the current repository before making changes.",
            "Use the stack already present in the repository unless the brief says otherwise.",
            "Ask ARCH for clarification if a dependency or interface is missing.",
        ],
        "General engineering specialist",
    )


def build_task_skill_profile(project: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    """Infer stack-specific skills and instructions for a task."""
    stack = _stack_from_project(project, task)
    title_text = _project_text(project, task)
    base_skills, instructions, prompt_focus = _base_skills_for_stack(stack, task.get("agent", "byte"))

    skills = list(dict.fromkeys(base_skills))

    if "auth" in title_text or "authentication" in title_text:
        skills.append("Authentication")
        instructions.append("Validate auth flows and protect sensitive routes.")
    if "dashboard" in title_text or "admin" in title_text:
        skills.append("Dashboard UX")
    if "api" in title_text or "rest" in title_text:
        skills.append("API Design")
    if "metrics" in title_text or "monitor" in title_text:
        skills.append("Observability")
    if "markdown" in title_text or "documentation" in title_text:
        skills.append("Markdown")
    if "backup" in title_text or "restore" in title_text:
        skills.append("Backup and Restore")
    if "apache" in title_text:
        skills.append("Apache")

    if task.get("agent") == "pixel" and "frontend" not in stack:
        instructions.append("Coordinate with BYTE on UI surface area and file boundaries.")

    return asdict(
        TaskSkillProfile(
            family=stack,
            stack=project.get("tech_stack", {}).get("backend")
            or project.get("tech_stack", {}).get("frontend")
            or stack,
            skills=list(dict.fromkeys(skills)),
            instructions=list(dict.fromkeys(instructions)),
            prompt_focus=prompt_focus,
        )
    )


def render_task_context_md(
    agent_id: str,
    task: dict[str, Any],
    project: dict[str, Any],
    skill_profile: dict[str, Any],
    repo_state: dict[str, Any],
) -> str:
    """Render the workspace context markdown for a task."""
    acceptance = task.get("acceptance", []) or []
    skills = skill_profile.get("skills", []) or []
    instructions = skill_profile.get("instructions", []) or []
    repo_path = repo_state.get("repo_path") or project.get("output_dir") or "./output"
    branch = repo_state.get("branch") or project.get("branch") or "n/a"

    lines = [
        f"# Active Task: {task.get('id')}",
        "",
        f"- Agent: {agent_id}",
        f"- Family: {skill_profile.get('family', 'general')}",
        f"- Focus: {skill_profile.get('prompt_focus', 'General engineering specialist')}",
        f"- Repo path: {repo_path}",
        f"- Branch: {branch}",
        "",
        "## Task",
        f"- Title: {task.get('title', '')}",
        f"- Description: {task.get('description', '')}",
        "",
        "## Acceptance Criteria",
    ]
    lines.extend(f"- {item}" for item in acceptance or ["No criteria provided."])
    lines.append("")
    lines.append("## Skill Focus")
    lines.extend(f"- {item}" for item in skills or ["Repository inspection", "Task decomposition"])
    lines.append("")
    lines.append("## Coordination Rules")
    lines.extend(
        [
            "- If you are blocked, DM ARCH with `BLOCKER:<task_id> <issue>`.",
            "- If you need a decision, DM ARCH with `QUESTION:<task_id> <question>`.",
            "- Keep your progress JSON updated under `progress/` in this workspace.",
        ]
    )
    lines.append("")
    lines.append("## Agent Notes")
    lines.extend(f"- {item}" for item in instructions or ["Follow the stack already present in the repo."])
    return "\n".join(lines)


def write_agent_workspace_files(
    agent_id: str,
    task: dict[str, Any],
    project: dict[str, Any],
    skill_profile: dict[str, Any],
    repo_state: dict[str, Any],
) -> dict[str, Path]:
    """Write task context and initial progress files for an agent workspace."""
    workspace_root = workspace_root_for_agent(agent_id)
    progress_root = workspace_root / "progress"
    workspace_root.mkdir(parents=True, exist_ok=True)
    progress_root.mkdir(parents=True, exist_ok=True)

    task_id = task.get("id", "task")
    timestamp = datetime.utcnow().isoformat()
    context_md = render_task_context_md(agent_id, task, project, skill_profile, repo_state)
    context_json = {
        "agent": agent_id,
        "task": task,
        "project": {
            "name": project.get("name"),
            "description": project.get("description"),
            "tech_stack": project.get("tech_stack", {}),
            "output_dir": project.get("output_dir"),
            "repo_path": repo_state.get("repo_path") or project.get("output_dir"),
            "branch": repo_state.get("branch") or project.get("branch"),
        },
        "skill_profile": skill_profile,
        "repo_state": repo_state,
        "created_at": timestamp,
    }
    progress_payload = {
        "task_id": task_id,
        "agent": agent_id,
        "status": "queued",
        "title": task.get("title"),
        "skills": skill_profile.get("skills", []),
        "family": skill_profile.get("family"),
        "repo_path": repo_state.get("repo_path") or project.get("output_dir"),
        "branch": repo_state.get("branch") or project.get("branch"),
        "created_at": timestamp,
        "updated_at": timestamp,
        "events": [
            {
                "ts": timestamp,
                "type": "queued",
                "message": "Task queued for execution",
            }
        ],
    }

    context_md_path = workspace_root / "active_task.md"
    context_json_path = workspace_root / "active_task.json"
    progress_path = progress_root / f"{task_id}.json"

    context_md_path.write_text(context_md, encoding="utf-8")
    context_json_path.write_text(
        json.dumps(context_json, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    progress_path.write_text(
        json.dumps(progress_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "workspace_root": workspace_root,
        "context_md": context_md_path,
        "context_json": context_json_path,
        "progress_path": progress_path,
    }


def _run_git(args: list[str], cwd: Path | None = None) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True)


def _ensure_git_identity(repo_path: Path) -> None:
    username = os.getenv("GIT_AUTHOR_NAME") or os.getenv("GIT_COMMITTER_NAME") or "OpenClaw"
    email = os.getenv("GIT_AUTHOR_EMAIL") or os.getenv("GIT_COMMITTER_EMAIL") or "openclaw@example.com"
    _run_git(["config", "user.name", username], cwd=repo_path)
    _run_git(["config", "user.email", email], cwd=repo_path)


def bootstrap_repository(
    project: dict[str, Any],
    repo_url: str | None = None,
    repo_name: str | None = None,
    branch: str | None = None,
    allow_init_repo: bool = False,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Create or attach a repository workspace and return the normalized state."""
    project_root = project_root or PROJECTS_ROOT
    project_root.mkdir(parents=True, exist_ok=True)

    resolved_repo_url = repo_url or project.get("repo_url")
    resolved_repo_name = repo_name or project.get("repo_name") or slugify(project.get("name"))
    branch_name = branch or project.get("branch") or f"codex/{slugify(project.get('name') or resolved_repo_name)}"
    target_path = Path(project.get("repo_path") or (project_root / resolved_repo_name))
    repo_state = {
        "repo_url": resolved_repo_url,
        "repo_name": resolved_repo_name,
        "repo_path": str(target_path),
        "branch": branch_name,
        "action": None,
        "git_available": shutil.which("git") is not None,
    }

    if not repo_state["git_available"]:
        raise RepositoryBootstrapError("Git is not available in this environment.")

    try:
        if target_path.exists() and (target_path / ".git").exists():
            repo_state["action"] = "existing"
            _ensure_git_identity(target_path)
            _run_git(["checkout", "-B", branch_name], cwd=target_path)
            project["repo_path"] = str(target_path)
            project["branch"] = branch_name
            project["output_dir"] = str(target_path)
            project["bootstrap_status"] = "existing"
            return repo_state

        if resolved_repo_url:
            if target_path.exists() and any(target_path.iterdir()):
                raise RepositoryBootstrapError(
                    f"Target path {target_path} already exists and is not empty."
                )
            _run_git(["clone", resolved_repo_url, str(target_path)])
            _ensure_git_identity(target_path)
            _run_git(["checkout", "-B", branch_name], cwd=target_path)
            repo_state["action"] = "cloned"
            project["repo_url"] = resolved_repo_url
            project["repo_path"] = str(target_path)
            project["branch"] = branch_name
            project["output_dir"] = str(target_path)
            project["bootstrap_status"] = "cloned"
            return repo_state

        if allow_init_repo:
            target_path.mkdir(parents=True, exist_ok=True)
            if not (target_path / ".git").exists():
                _run_git(["init"], cwd=target_path)
            _ensure_git_identity(target_path)
            _run_git(["checkout", "-B", branch_name], cwd=target_path)
            repo_state["action"] = "initialized"
            project["repo_path"] = str(target_path)
            project["branch"] = branch_name
            project["output_dir"] = str(target_path)
            project["bootstrap_status"] = "initialized"
            return repo_state
    except subprocess.CalledProcessError as exc:
        raise RepositoryBootstrapError(f"Git command failed: {exc}") from exc
    except OSError as exc:
        raise RepositoryBootstrapError(f"Repository bootstrap failed: {exc}") from exc

    raise RepositoryApprovalRequired(
        "Repository details are missing. Send the repository URL over Telegram or allow local init."
    )


def send_telegram_message(
    message: str,
    token: str | None = None,
    chat_id: str | None = None,
) -> dict[str, Any]:
    """Send a Telegram notification when credentials are available."""
    resolved_token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    resolved_chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    if not resolved_token or not resolved_chat_id:
        return {
            "sent": False,
            "reason": "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID",
        }

    response = requests.post(
        f"https://api.telegram.org/bot{resolved_token}/sendMessage",
        json={
            "chat_id": resolved_chat_id,
            "text": message,
            "disable_web_page_preview": True,
        },
        timeout=15,
    )
    response.raise_for_status()
    return {
        "sent": True,
        "status_code": response.status_code,
        "response": response.json() if response.content else {},
    }
