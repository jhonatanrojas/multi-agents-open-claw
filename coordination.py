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
OPENCLAW_AGENTS_ROOT = Path("/root/.openclaw/agents")
WORKSPACE_NAMES = {
    "arch": "coordinator",
    "byte": "programmer",
    "pixel": "designer",
}


class RepositoryBootstrapError(RuntimeError):
    """Se lanza cuando el bootstrap del repositorio no puede continuar de forma segura."""


class RepositoryApprovalRequired(RuntimeError):
    """Se lanza cuando el coordinador necesita aprobación o datos del repositorio por Telegram."""


class ProjectClarificationRequired(RuntimeError):
    """Se lanza cuando el brief requiere una aclaración antes de planificar."""

    def __init__(
        self,
        message: str,
        *,
        questions: list[str] | None = None,
        project_brief: str | None = None,
        project_structure: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.questions = questions or []
        self.project_brief = project_brief
        self.project_structure = project_structure or {}


def get_telegram_credentials() -> tuple[str | None, str | None]:
    """Return the configured Telegram bot token and chat id, if any."""
    return (
        os.getenv("TELEGRAM_BOT_TOKEN"),
        os.getenv("TELEGRAM_CHAT_ID"),
    )


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


def _project_workspace_key(project: dict[str, Any] | None) -> str | None:
    if not isinstance(project, dict):
        return None
    raw_key = (
        project.get("id")
        or project.get("repo_name")
        or project.get("name")
        or project.get("repo_path")
    )
    if not raw_key:
        return None
    return slugify(str(raw_key))


def workspace_root_for_agent(agent_id: str, project: dict[str, Any] | None = None) -> Path:
    """Return the workspace directory that OpenClaw mounts for an agent.

    When a project is provided, the workspace is namespaced by project key so
    task progress and context files do not collide across different runs that
    reuse the same task IDs.
    """
    base = WORKSPACES_ROOT / WORKSPACE_NAMES.get(agent_id, agent_id)
    project_key = _project_workspace_key(project)
    if project_key:
        return base / project_key
    return base


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


def _brief_mentions_feature_scope(text: str) -> bool:
    return any(
        token in text
        for token in (
            "feature",
            "existing project",
            "existing app",
            "en el proyecto existente",
            "sobre el proyecto",
            "sobre la app actual",
            "en la app actual",
            "extender",
            "ampliar",
            "modificar",
            "mejorar",
            "añadir",
            "agregar",
            "integrar",
        )
    )


def _brief_mentions_framework(text: str) -> bool:
    return any(
        token in text
        for token in (
            "react",
            "vue",
            "angular",
            "next.js",
            "nextjs",
            "svelte",
            "nuxt",
            "astro",
            "remix",
            "vite",
            "tailwind",
            "bootstrap",
            "framework",
        )
    )


def _brief_mentions_vanilla(text: str) -> bool:
    return any(
        token in text
        for token in (
            "html",
            "css",
            "javascript",
            "vanilla",
            "vanilla js",
            "js puro",
            "localstorage",
            "local storage",
            "dom",
            "sitio estático",
            "sitio estatíco",
            "sitio web estático",
            "static site",
        )
    )


def _brief_likely_needs_architecture(text: str) -> bool:
    return any(
        token in text
        for token in (
            "app",
            "application",
            "aplicación",
            "dashboard",
            "admin",
            "crud",
            "portal",
            "panel",
            "auth",
            "login",
            "signup",
            "form",
            "forms",
            "multi-page",
            "spa",
            "single page",
            "state",
            "component",
            "api",
        )
    )


def needs_planning_clarification(brief: str) -> list[str]:
    """Return clarifying questions required before planning, if any."""
    text = (brief or "").lower()
    if not text:
        return []
    if _brief_mentions_feature_scope(text):
        return []
    if _brief_mentions_framework(text) or _brief_mentions_vanilla(text):
        return []
    if not _brief_likely_needs_architecture(text):
        return []

    return [
        "¿Este proyecto es nuevo o una feature sobre un proyecto existente?",
        "Si es un proyecto nuevo, ¿prefieres Vanilla HTML/CSS/JS con estructura simple o un framework (React/Vue/Angular/Next)?",
    ]


def infer_project_structure(project: dict[str, Any], task: dict[str, Any] | None = None) -> dict[str, Any]:
    """Infer a canonical project structure from the brief and stack."""
    task = task or {}
    text = _project_text(project, task)
    stack = _stack_from_project(project, task)
    repo_root = str(Path(project.get("repo_path") or project.get("output_dir") or "./output").resolve())

    if stack == "vanilla-frontend":
        return {
            "kind": "vanilla-static",
            "root": repo_root,
            "entrypoint": "index.html",
            "directories": {
                "styles": "css/",
                "scripts": "js/",
                "assets": "assets/",
                "fonts": "fonts/",
            },
            "notes": [
                "Mantén index.html en la raíz del proyecto.",
                "Usa css/ para estilos, js/ para lógica y assets/ para recursos estáticos.",
                "No uses output/frontend salvo que el brief lo pida explícitamente.",
            ],
        }

    if stack == "frontend":
        return {
            "kind": "framework-frontend",
            "root": repo_root,
            "entrypoint": "src/",
            "directories": {
                "components": "src/components/",
                "features": "src/features/",
                "hooks": "src/hooks/",
                "services": "src/services/",
                "utils": "src/utils/",
                "pages": "src/pages/",
                "public": "public/",
            },
            "notes": [
                "Estructura basada en funcionalidades y componentes reutilizables.",
                "Coloca el código fuente en src/ y los estáticos en public/.",
            ],
        }

    if stack in {"fastapi", "node-express"}:
        return {
            "kind": "backend-service",
            "root": repo_root,
            "entrypoint": "backend/",
            "directories": {
                "app": "backend/app/",
                "services": "backend/services/",
                "routes": "backend/routes/",
                "tests": "backend/tests/",
                "config": "backend/config/",
            },
            "notes": [
                "Separa la lógica de dominio, rutas y tests.",
                "No mezcles la salida del backend con estructuras de frontend.",
            ],
        }

    if stack == "laravel":
        return {
            "kind": "laravel-app",
            "root": repo_root,
            "entrypoint": "root",
            "directories": {
                "app": "app/",
                "resources": "resources/",
                "views": "resources/views/",
                "public": "public/",
                "tests": "tests/",
            },
            "notes": [
                "Respeta la convención estándar de Laravel.",
                "Si el brief describe una feature sobre una app Laravel existente, trabaja dentro de su estructura actual.",
            ],
        }

    if "documentation" in text or "docs" in text or "markdown" in text:
        return {
            "kind": "documentation",
            "root": repo_root,
            "entrypoint": "root",
            "directories": {
                "docs": "docs/",
            },
            "notes": [
                "Organiza la documentación en Markdown con encabezados claros.",
            ],
        }

    return {
        "kind": "general",
        "root": repo_root,
        "entrypoint": "root",
        "directories": {},
        "notes": [
            "Usa la estructura que ya exista en el repositorio.",
        ],
    }


def _stack_from_project(project: dict[str, Any], task: dict[str, Any]) -> str:
    text = _project_text(project, task)
    tech_stack = project.get("tech_stack", {}) or {}
    tech_blob = " ".join(str(v).lower() for v in tech_stack.values())

    if any(token in text for token in ("fastapi", "sqlalchemy", "pydantic", "sqlite", "cors", "python backend")):
        return "fastapi"
    if any(token in text for token in ("html", "css", "javascript", "localstorage", "vanilla js", "dom manipulation")):
        if not any(token in text for token in ("react", "typescript", "next.js", "nextjs", "vite")):
            return "vanilla-frontend"
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
    if any(token in tech_blob for token in ("fastapi", "sqlalchemy", "pydantic", "sqlite", "python")):
        return "fastapi"

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

    if stack == "fastapi":
        return (
            ["Python", "FastAPI", "SQLAlchemy", "Pydantic", "SQLite", "CORS", "REST APIs", "Pytest"],
            [
                "Prioriza la estructura del backend antes de cualquier detalle de integración.",
                "Crea una base sólida con FastAPI, configuración de CORS, SQLite y modelos de datos claros.",
                "Genera tests unitarios o de integración para cada módulo backend nuevo.",
                "Los tests son obligatorios para cualquier módulo backend nuevo antes de cerrar la tarea.",
                "Mantén explícitos los contratos de request/response y valida la configuración de entorno.",
            ],
            "Especialista en FastAPI",
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

    if stack == "vanilla-frontend":
        return (
            ["HTML5", "CSS3", "JavaScript ES6+", "LocalStorage", "Accessibility", "Responsive UI"],
            [
                "Usa HTML semántico y divide la estructura en secciones claras.",
                "Mantén el CSS simple, responsive y consistente con el contenido del proyecto.",
                "La estructura canónica es raíz/index.html + css/ + js/ + assets/; evita output/frontend salvo indicación explícita.",
                "Si el proyecto usa JavaScript puro, evita introducir frameworks o dependencias innecesarias.",
            ],
            "Especialista en HTML/CSS/JavaScript",
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


def infer_task_execution_dir(project: dict[str, Any], task: dict[str, Any], repo_state: dict[str, Any] | None = None) -> str:
    """Infer the canonical directory where a task should execute.

    The directory is a coordinator decision, not an agent decision.  It is used
    to keep task scope stable and avoid each agent inventing its own structure.
    """
    repo_root = Path((repo_state or {}).get("repo_path") or project.get("repo_path") or project.get("output_dir") or "./output")
    task_text = _project_text(project, task)
    task_id = str(task.get("id") or "task").lower()
    structure = infer_project_structure(project, task)
    structure_kind = str(structure.get("kind") or "")

    if any(token in task_text for token in ("fastapi", "sqlalchemy", "pydantic", "sqlite", "backend")):
        return str((repo_root / "backend").resolve())
    if any(token in task_text for token in ("design", "spec", "component", "pixel")):
        return str((repo_root / "design" / task_id).resolve())
    if any(token in task_text for token in ("readme", "documentation", "markdown")):
        return str(repo_root.resolve())
    if structure_kind == "vanilla-static":
        return str(repo_root.resolve())
    if structure_kind == "framework-frontend":
        return str((repo_root / "src").resolve())
    if structure_kind == "backend-service":
        return str((repo_root / "backend").resolve())
    if any(token in task_text for token in ("react", "typescript", "frontend", "ui", "dashboard")):
        return str((repo_root / "src").resolve())
    if any(token in task_text for token in ("html", "css", "javascript", "localstorage", "vanilla")):
        return str(repo_root.resolve())
    return str(repo_root.resolve())


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
    execution_dir = task.get("execution_dir") or infer_task_execution_dir(project, task, repo_state)
    project_structure = project.get("project_structure") or infer_project_structure(project, task)
    directories = project_structure.get("directories", {}) or {}

    lines = [
        f"# Tarea activa: {task.get('id')}",
        "",
        f"- Agente: {agent_id}",
        f"- Familia: {skill_profile.get('family', 'general')}",
        f"- Enfoque: {skill_profile.get('prompt_focus', 'Especialista general en ingeniería')}",
        f"- Ruta del repo: {repo_path}",
        f"- Rama: {branch}",
        f"- Directorio de ejecución: {execution_dir}",
        "",
        "## Resumen del proyecto",
        f"- Nombre: {project.get('name', '')}",
        f"- Descripción: {project.get('description', '')}",
        f"- Stack frontend: {project.get('tech_stack', {}).get('frontend', 'n/a')}",
        f"- Stack backend: {project.get('tech_stack', {}).get('backend', 'n/a')}",
        f"- Base de datos: {project.get('tech_stack', {}).get('database', 'n/a')}",
        "",
        "## Estructura canónica",
        f"- Tipo: {project_structure.get('kind', 'n/a')}",
        f"- Raíz: {project_structure.get('root', 'n/a')}",
        f"- Punto de entrada: {project_structure.get('entrypoint', 'n/a')}",
    ]
    if isinstance(directories, dict) and directories:
        lines.extend(f"- {name}: {path}" for name, path in directories.items())
    project_structure_notes = project_structure.get("notes", []) or []
    if project_structure_notes:
        lines.append("")
        lines.append("## Notas de estructura")
        lines.extend(f"- {item}" for item in project_structure_notes)
    lines.extend(
        [
            "",
            "## Tarea",
            f"- Título: {task.get('title', '')}",
            f"- Descripción: {task.get('description', '')}",
            "",
            "## Criterios de aceptación",
        ]
    )
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
    lines.append("")
    lines.append("## Contrato de salida")
    lines.extend(
        [
            "- Escribe únicamente los archivos que realmente correspondan a esta tarea y colócalos en el directorio de ejecución indicado.",
            "- Si los archivos ya existen, verifícalos y corrígelos; no reinicies la tarea ni inventes otra estructura.",
            "- Si no puedes producir archivos porque falta una decisión o el entorno está roto, responde con `BLOCKER:<task_id> ...` o `QUESTION:<task_id> ...`.",
            "- No declares la tarea como terminada hasta haber escrito los archivos y haber verificado que existen en disco.",
            "- La validación final se hará contra el filesystem y el manifest del proyecto, no solo contra el texto del chat.",
        ]
    )
    lines.append("")
    lines.append("## Protocolo de continuidad")
    lines.extend(
        [
            "- Si algo no está claro, detente y pregunta a ARCH con `QUESTION:<task_id> <pregunta>`.",
            "- Cuando ARCH responda, continúa exactamente desde el último paso incompleto, no reinicies la tarea.",
            "- Usa el mismo `session_id` del workspace para mantener el hilo de trabajo vivo.",
            "- Respeta el directorio de ejecución definido por ARCH; no inventes otra estructura.",
            "- Antes de concluir, verifica que los archivos producidos cumplan todos los criterios de aceptación.",
        ]
    )
    lines.append("")
    lines.append("## Estado esperado al terminar")
    lines.append("- Devuelve solo el JSON solicitado por el orquestador.")
    lines.append("- Si la tarea se completa, asegúrate de que los archivos estén en el workspace indicado.")
    return "\n".join(lines)


def refresh_agent_workspace_files(
    agent_id: str,
    task: dict[str, Any],
    project: dict[str, Any],
    skill_profile: dict[str, Any],
    repo_state: dict[str, Any],
    *,
    question: str | None = None,
    reply: str | None = None,
) -> dict[str, Path]:
    """Refresh the workspace context and append coordination notes.

    This is used when ARCH receives a QUESTION or sends a follow-up reply so
    the active agent can resume from the exact interruption point.
    """
    task_id = task.get("id", "task")
    workspace_root = workspace_root_for_agent(agent_id, project)
    progress_root = workspace_root / "progress"
    context_md_path = workspace_root / "active_task.md"
    context_json_path = workspace_root / "active_task.json"
    progress_path = progress_root / f"{task_id}.json"
    if not (context_md_path.exists() and context_json_path.exists() and progress_path.exists()):
        return write_agent_workspace_files(agent_id, task, project, skill_profile, repo_state)

    coordination_event = {
        "ts": datetime.utcnow().isoformat(),
        "task_id": task_id,
        "agent": agent_id,
        "question": question,
        "reply": reply,
    }

    try:
        context_data = json.loads(context_json_path.read_text(encoding="utf-8"))
    except Exception:
        context_data = {}
    context_data.setdefault("coordination", [])
    context_data["coordination"].append(coordination_event)
    if question:
        context_data["last_question"] = question
    if reply:
        context_data["last_arch_reply"] = reply
    context_data["resume_hint"] = (
        "Resume desde el último paso incompleto usando la respuesta del coordinador "
        "si existe. No reinicies el trabajo."
    )
    context_json_path.write_text(json.dumps(context_data, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        progress_data = json.loads(progress_path.read_text(encoding="utf-8"))
    except Exception:
        progress_data = {"task_id": task_id, "events": []}
    progress_data.setdefault("coordination_log", [])
    progress_data["coordination_log"].append(coordination_event)
    if question:
        progress_data["last_question"] = question
    if reply:
        progress_data["last_arch_reply"] = reply
    progress_data["updated_at"] = datetime.utcnow().isoformat()
    progress_path.write_text(json.dumps(progress_data, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        "",
        "## Última coordinación",
    ]
    if question:
        md_lines.append(f"- Pregunta: {question}")
    if reply:
        md_lines.append(f"- Respuesta de ARCH: {reply}")
    md_lines.append("- Continúa desde el último paso incompleto; no reinicies la tarea.")
    context_md_path.write_text(
        context_md_path.read_text(encoding="utf-8").rstrip() + "\n" + "\n".join(md_lines) + "\n",
        encoding="utf-8",
    )
    return {
        "workspace_root": workspace_root,
        "context_md": context_md_path,
        "context_json": context_json_path,
        "progress_path": progress_path,
    }


def _session_log_candidates(agent_id: str) -> list[Path]:
    sessions_dir = OPENCLAW_AGENTS_ROOT / agent_id / "sessions"
    if not sessions_dir.exists():
        return []
    return sorted(
        (p for p in sessions_dir.glob("*.jsonl") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def collect_agent_session_diagnostics(agent_id: str, *, max_events: int = 40) -> dict[str, Any] | None:
    """Summarize the latest OpenClaw session log for an agent.

    The goal is to surface the last real failure or misleading tool usage so
    the coordinator can refresh the workspace before relaunching.
    """
    for session_path in _session_log_candidates(agent_id):
        try:
            lines = session_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue

        events: list[dict[str, Any]] = []
        last_error: str | None = None
        last_model: str | None = None
        last_provider: str | None = None
        last_stop_reason: str | None = None
        last_content: str | None = None
        last_tool_name: str | None = None

        for raw_line in lines[-max_events:]:
            try:
                entry = json.loads(raw_line)
            except Exception:
                continue
            events.append(entry)
            if entry.get("type") == "model_change":
                last_provider = entry.get("provider") or last_provider
                last_model = entry.get("modelId") or last_model
            message = entry.get("message")
            if isinstance(message, dict):
                message_content = message.get("content")
                if isinstance(message_content, list) and message_content:
                    first = message_content[0]
                    if isinstance(first, dict):
                        text = first.get("text") or first.get("thinking")
                        if isinstance(text, str) and text.strip():
                            last_content = text.strip()
                if message.get("stopReason"):
                    last_stop_reason = message.get("stopReason") or last_stop_reason
                if message.get("errorMessage"):
                    last_error = message.get("errorMessage") or last_error
                tool_call_id = message.get("toolCallId")
                tool_name = message.get("toolName")
                if isinstance(tool_name, str) and tool_name.strip():
                    last_tool_name = tool_name
                if isinstance(tool_call_id, str) and not last_tool_name:
                    last_tool_name = tool_call_id
            if entry.get("errorMessage"):
                last_error = entry.get("errorMessage") or last_error

        if not any([last_error, last_content, last_stop_reason, last_model, last_provider]):
            continue

        summary_parts = []
        if last_provider or last_model:
            summary_parts.append(
                f"Modelo: {last_provider or 'n/a'}/{last_model or 'n/a'}"
            )
        if last_stop_reason:
            summary_parts.append(f"stopReason: {last_stop_reason}")
        if last_tool_name:
            summary_parts.append(f"tool: {last_tool_name}")
        if last_error:
            summary_parts.append(f"error: {last_error}")
        if last_content:
            summary_parts.append(f"último texto: {last_content[:180]}")

        return {
            "session_file": str(session_path),
            "summary": " | ".join(summary_parts) if summary_parts else "Sin señales útiles",
            "provider": last_provider,
            "model": last_model,
            "stop_reason": last_stop_reason,
            "error": last_error,
            "last_text": last_content,
            "events_seen": len(events),
        }
    return None


def apply_session_diagnostics_to_workspace(
    agent_id: str,
    task: dict[str, Any],
    project: dict[str, Any],
    skill_profile: dict[str, Any],
    repo_state: dict[str, Any],
) -> dict[str, Any] | None:
    """Attach the latest session diagnosis to the agent workspace."""
    diagnostics = collect_agent_session_diagnostics(agent_id)
    if not diagnostics:
        return None

    paths = refresh_agent_workspace_files(agent_id, task, project, skill_profile, repo_state)
    context_json_path = paths["context_json"]
    progress_path = paths["progress_path"]
    context_md_path = paths["context_md"]

    try:
        context_data = json.loads(context_json_path.read_text(encoding="utf-8"))
    except Exception:
        context_data = {}
    context_data["last_session_diagnostics"] = diagnostics
    context_json_path.write_text(json.dumps(context_data, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        progress_data = json.loads(progress_path.read_text(encoding="utf-8"))
    except Exception:
        progress_data = {"task_id": task.get("id", "task"), "events": []}
    progress_data["last_session_diagnostics"] = diagnostics
    progress_path.write_text(json.dumps(progress_data, indent=2, ensure_ascii=False), encoding="utf-8")

    md_append = [
        "",
        "## Diagnóstico de la sesión anterior",
        f"- {diagnostics['summary']}",
        f"- Archivo: {diagnostics['session_file']}",
        "- Si el contexto anterior estaba desalineado, ignóralo y sigue este workspace actualizado.",
    ]
    context_md_path.write_text(
        context_md_path.read_text(encoding="utf-8").rstrip() + "\n" + "\n".join(md_append) + "\n",
        encoding="utf-8",
    )
    return diagnostics


def write_agent_workspace_files(
    agent_id: str,
    task: dict[str, Any],
    project: dict[str, Any],
    skill_profile: dict[str, Any],
    repo_state: dict[str, Any],
) -> dict[str, Path]:
    """Write task context and initial progress files for an agent workspace."""
    workspace_root = workspace_root_for_agent(agent_id, project)
    progress_root = workspace_root / "progress"
    workspace_root.mkdir(parents=True, exist_ok=True)
    progress_root.mkdir(parents=True, exist_ok=True)

    task_id = task.get("id", "task")
    timestamp = datetime.utcnow().isoformat()
    execution_dir = task.get("execution_dir") or infer_task_execution_dir(project, task, repo_state)
    context_md = render_task_context_md(agent_id, task, project, skill_profile, repo_state)
    context_json = {
        "agent": agent_id,
        "task": task,
        "execution_dir": execution_dir,
        "project": {
            "name": project.get("name"),
            "description": project.get("description"),
            "tech_stack": project.get("tech_stack", {}),
            "project_structure": project.get("project_structure") or infer_project_structure(project, task),
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
        "execution_dir": execution_dir,
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


def git_has_remote(repo_path: Path, remote: str = "origin") -> bool:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", remote],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def git_current_branch(repo_path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        branch = result.stdout.strip()
        return branch or None
    except Exception:
        return None


def git_push_current_branch(repo_path: Path, remote: str = "origin") -> bool:
    try:
        _run_git(["push", "-u", remote, "HEAD"], cwd=repo_path)
        return True
    except Exception:
        return False


def git_open_pr(repo_path: Path, title: str, body: str = "") -> bool:
    gh = shutil.which("gh")
    if not gh:
        return False
    try:
        subprocess.run(
            [gh, "pr", "create", "--fill", "--title", title, "--body", body],
            cwd=repo_path,
            check=True,
        )
        return True
    except Exception:
        return False


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


def finalize_repo_after_task(
    repo_path: Path,
    agent_id: str,
    task_id: str,
    task_title: str,
    *,
    create_pr: bool = True,
) -> dict[str, Any]:
    """Commit, push, and optionally open a PR after a task completes."""
    result = {
        "committed": False,
        "pushed": False,
        "pr_created": False,
        "branch": None,
        "remote": None,
    }
    if not repo_path.exists():
        return result
    result["branch"] = git_current_branch(repo_path)
    try:
        result["committed"] = commit_task_output(repo_path, agent_id, task_id, task_title)
    except Exception:
        result["committed"] = False

    if git_has_remote(repo_path):
        result["remote"] = "origin"
        result["pushed"] = git_push_current_branch(repo_path, remote="origin")
        if create_pr and result["pushed"]:
            result["pr_created"] = git_open_pr(
                repo_path,
                title=f"[{agent_id}] {task_id}: {task_title[:72]}",
                body=f"Auto-generated by OpenClaw for task {task_id}.",
            )
    return result


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


def fetch_telegram_updates(
    *,
    offset: int | None = None,
    timeout: int = 30,
    limit: int = 50,
    token: str | None = None,
) -> dict[str, Any]:
    """Fetch bot updates using Telegram long polling."""
    resolved_token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not resolved_token:
        return {"ok": False, "reason": "Falta TELEGRAM_BOT_TOKEN", "updates": []}

    params: dict[str, Any] = {
        "timeout": max(1, int(timeout)),
        "limit": max(1, min(int(limit), 100)),
    }
    if offset is not None:
        params["offset"] = int(offset)

    try:
        response = requests.get(
            f"https://api.telegram.org/bot{resolved_token}/getUpdates",
            params=params,
            timeout=max(5, int(timeout) + 5),
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return {"ok": False, "reason": str(exc), "updates": []}

    updates = payload.get("result", []) if isinstance(payload, dict) else []
    if not isinstance(updates, list):
        updates = []

    return {
        "ok": bool(payload.get("ok", False)) if isinstance(payload, dict) else False,
        "updates": updates,
        "payload": payload,
    }
