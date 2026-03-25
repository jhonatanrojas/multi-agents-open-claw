from __future__ import annotations

import json
import os
import re
import subprocess
import shutil
import time
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
    """Se lanza cuando el bootstrap del repositorio no puede continuar de forma segura."""


class RepositoryApprovalRequired(RuntimeError):
    """Se lanza cuando el coordinador necesita aprobación o datos del repositorio por Telegram."""


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
                "Usa las convenciones de Laravel y límites claros entre servicios.",
                "Prioriza modelos Eloquent, migraciones y servicios reutilizables.",
                "Si hay autenticación, planifica el flujo antes de escribir código.",
            ],
            "Especialista en Laravel",
        )

    if stack == "node-express":
        return (
            ["Node.js", "Express", "REST APIs", "Middleware", "NPM", "Testing"],
            [
                "Usa rutas de Express, middleware y límites claros entre módulos.",
                "Mantén explícitos los contratos de API y documenta las estructuras de request/response.",
                "Prefiere TypeScript cuando el repositorio ya lo use.",
            ],
            "Especialista en Node/Express",
        )

    if stack == "frontend":
        return (
            ["React", "TypeScript", "Accessibility", "Responsive UI", "Component Design"],
            [
                "Respeta el lenguaje visual existente y mantén la interfaz accesible.",
                "Divide la UI compleja en componentes reutilizables y conserva un estado predecible.",
                "Si el proyecto ya usa un sistema de diseño, extiéndelo en vez de reemplazarlo.",
            ],
            "Especialista en frontend",
        )

    if stack == "devops":
        return (
            ["Bash", "Apache", "Nginx", "Cron", "Backups", "Health Checks", "Deployment"],
            [
                "Prefiere scripts idempotentes y runbooks operativos claros.",
                "Valida puertos, health checks y flujos de backup/restore de forma explícita.",
                "Documenta cualquier secreto o variable de entorno necesaria.",
            ],
            "Especialista en DevOps",
        )

    if stack == "documentation":
        return (
            ["Markdown", "Information Architecture", "User Guides", "Installation Flows"],
            [
                "Mantén la documentación estructurada, localizable y orientada a tareas.",
                "Incluye instalación, uso, solución de problemas y ejemplos cuando aplique.",
                "Prefiere encabezados claros y pasos procedimentales concisos.",
            ],
            "Especialista en documentación",
        )

    return (
        ["Task Decomposition", "Repository Hygiene", "Testing", "Coordination"],
        [
            "Inspecciona el repositorio actual antes de hacer cambios.",
            "Usa el stack ya presente en el repositorio salvo que el brief indique otra cosa.",
            "Pide aclaración a ARCH si falta una dependencia o una interfaz.",
        ],
        "Especialista general en ingeniería",
    )


def build_task_skill_profile(project: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    """Infer stack-specific skills and instructions for a task."""
    stack = _stack_from_project(project, task)
    title_text = _project_text(project, task)
    base_skills, instructions, prompt_focus = _base_skills_for_stack(stack, task.get("agent", "byte"))

    skills = list(dict.fromkeys(base_skills))

    if "auth" in title_text or "authentication" in title_text:
        skills.append("Authentication")
        instructions.append("Valida los flujos de autenticación y protege las rutas sensibles.")
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
        instructions.append("Coordínate con BYTE sobre el alcance de la UI y los límites de archivos.")

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
        f"# Tarea activa: {task.get('id')}",
        "",
        f"- Agente: {agent_id}",
        f"- Familia: {skill_profile.get('family', 'general')}",
        f"- Enfoque: {skill_profile.get('prompt_focus', 'Especialista general en ingeniería')}",
        f"- Ruta del repo: {repo_path}",
        f"- Rama: {branch}",
        "",
        "## Tarea",
        f"- Título: {task.get('title', '')}",
        f"- Descripción: {task.get('description', '')}",
        "",
        "## Criterios de aceptación",
    ]
    lines.extend(f"- {item}" for item in acceptance or ["No se proporcionaron criterios."])
    lines.append("")
    lines.append("## Enfoque de habilidades")
    lines.extend(f"- {item}" for item in skills or ["Inspección del repositorio", "Descomposición de tareas"])
    lines.append("")
    lines.append("## Reglas de coordinación")
    lines.extend(
        [
            "- Si te bloqueas, envía a ARCH `BLOCKER:<task_id> <problema>`.",
            "- Si necesitas una decisión, envía a ARCH `QUESTION:<task_id> <pregunta>`.",
            "- Mantén actualizado tu JSON de progreso en `progress/` dentro de este workspace.",
        ]
    )
    lines.append("")
    lines.append("## Notas del agente")
    lines.extend(f"- {item}" for item in instructions or ["Sigue el stack ya presente en el repositorio."])
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
                "message": "Tarea en cola para ejecución",
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


def commit_task_output(
    repo_path: Path,
    agent_id: str,
    task_id: str,
    task_title: str,
) -> bool:
    """Stage all changes and commit them.  Returns True when a commit was made.

    Non-fatal: if git is unavailable or nothing to commit, returns False quietly.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        if not result.stdout.strip():
            return False  # Nothing to commit
        _run_git(["add", "-A"], cwd=repo_path)
        commit_msg = f"[{agent_id}] {task_id}: {task_title[:72]}"
        _run_git(["commit", "-m", commit_msg], cwd=repo_path)
        return True
    except (subprocess.CalledProcessError, OSError):
        return False


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
        "Faltan los datos del repositorio. Envía la URL por Telegram o permite la inicialización local."
    )


def send_telegram_message(
    message: str,
    token: str | None = None,
    chat_id: str | None = None,
    retries: int = 3,
    timeout: int = 15,
    backoff_seconds: float = 2.0,
) -> dict[str, Any]:
    """Send a Telegram notification when credentials are available."""
    resolved_token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    resolved_chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    if not resolved_token or not resolved_chat_id:
        return {
            "sent": False,
            "reason": "Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID",
        }

    delay = max(0.5, float(backoff_seconds))
    last_error: str | None = None

    for attempt in range(1, max(1, retries) + 1):
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{resolved_token}/sendMessage",
                json={
                    "chat_id": resolved_chat_id,
                    "text": message,
                    "disable_web_page_preview": True,
                },
                timeout=timeout,
            )
            response.raise_for_status()
            return {
                "sent": True,
                "status_code": response.status_code,
                "response": response.json() if response.content else {},
                "attempt": attempt,
            }
        except Exception as exc:
            last_error = str(exc)
            if attempt >= max(1, retries):
                break
            time.sleep(delay)
            delay *= 2

    return {
        "sent": False,
        "reason": last_error or "Falló el envío de Telegram",
        "attempts": max(1, retries),
    }
