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
from typing import Any, Literal, TypedDict

import requests

from shared_state import BASE_DIR, load_memory, refresh_project_runtime_state, save_memory, utc_now

PROJECTS_ROOT = BASE_DIR / "projects"
WORKSPACES_ROOT = BASE_DIR / "workspaces"
LOG_DIR = BASE_DIR / "logs"
OUTPUT_DIR = BASE_DIR / "output"
OPENCLAW_RUNTIME_HOME = Path(os.getenv("OPENCLAW_RUNTIME_HOME", str(Path.home() / ".openclaw-runtime")))
OPENCLAW_RUNTIME_PROFILE = os.getenv("OPENCLAW_PROFILE", "multi-agents-runtime-v2").strip()
OPENCLAW_AGENTS_ROOT = OPENCLAW_RUNTIME_HOME / f".openclaw-{OPENCLAW_RUNTIME_PROFILE}" / "agents"
WORKSPACE_NAMES = {
    "arch": "coordinator",
    "byte": "programmer",
    "pixel": "designer",
}

# ---------------------------------------------------------------------------
# Fase 0 — Contrato formal de estructura de proyecto
# ---------------------------------------------------------------------------

ProjectKind = Literal[
    "vanilla-static",      # index.html en raiz, css/, js/, assets/
    "framework-frontend",  # src/, components/, features/, pages/, public/
    "backend-service",     # backend/, app/, services/, routes/, tests/
    "laravel-app",         # respetar estructura existente de Laravel
    "documentation",       # docs/, README.md como entregable principal
    "general",             # proyecto sin estructura predecible
]


class ProjectStructure(TypedDict, total=False):
    """Schema formal de estructura de proyecto (Fase 0)."""

    kind: str                   # uno de ProjectKind
    root: str                   # directorio raiz relativo al repo
    entrypoint: str             # archivo o carpeta de entrada
    directories: dict           # nombre -> ruta relativa declarada
    canonical_paths: list       # prefijos de ruta permitidos para archivos de entrega
    forbidden_paths: list       # prefijos prohibidos (p. ej. output/frontend)
    notes: list                 # restricciones o advertencias
    is_new_project: bool        # True si el brief describe un proyecto nuevo (no feature)


FORBIDDEN_PATHS_DEFAULT = ["output/", "dist/", ".git/"]


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


def ensure_project_id(project: dict[str, Any]) -> str:
    """Return a stable project identifier, creating one when necessary."""
    pid = project.get("id")
    if pid:
        return str(pid)
    name = project.get("name") or "project"
    return f"{slugify(str(name))}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"


def update_project_history(mem: dict[str, Any]) -> None:
    """Upsert the active project snapshot into the project history list."""
    project = mem.get("project") or {}
    if not isinstance(project, dict):
        return
    project_id = project.get("id")
    if not project_id:
        return
    mem.setdefault("projects", [])
    entry = {
        "id": project_id,
        "name": project.get("name"),
        "description": project.get("description"),
        "status": project.get("status"),
        "created_at": project.get("created_at"),
        "updated_at": project.get("updated_at"),
        "repo_url": project.get("repo_url"),
        "repo_path": project.get("repo_path"),
        "branch": project.get("branch"),
        "output_dir": project.get("output_dir"),
    }
    for existing in mem["projects"]:
        if existing.get("id") == project_id:
            existing.update(entry)
            return
    mem["projects"].append(entry)


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


def _agent_base_workspace_root(agent_id: str) -> Path:
    """Return the shared, non-namespaced workspace for an agent."""
    return WORKSPACES_ROOT / WORKSPACE_NAMES.get(agent_id, agent_id)


def _safe_write_workspace_file(path: Path, content: str) -> None:
    """Write workspace helper files even if a stale symlink is present.

    Some older runs left `active_task.md/json` as symlinks to project-scoped
    workspaces. When that target workspace disappears, writing through the
    broken symlink raises ENOENT. Replace stale symlinks with real files.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    path.write_text(content, encoding="utf-8")


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
    """Infer a canonical project structure from the brief and stack.

    Returns a dict conforming to ProjectStructure. Always includes
    `canonical_paths` and `forbidden_paths` so execute_task() can validate
    that agents do not write to invented directories.
    """
    task = task or {}
    text = _project_text(project, task)
    stack = _stack_from_project(project, task)
    repo_root = str(Path(project.get("repo_path") or project.get("output_dir") or "./output").resolve())
    new_project = not _brief_mentions_feature_scope(text)

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
            "canonical_paths": ["", "css/", "js/", "assets/", "fonts/", "vendor/"],
            "forbidden_paths": ["output/", "dist/", "src/"],
            "notes": [
                "Mantén index.html en la raíz del proyecto.",
                "Usa css/ para estilos, js/ para lógica y assets/ para recursos estáticos.",
            ],
            "is_new_project": new_project,
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
            "canonical_paths": ["src/", "public/"],
            "forbidden_paths": ["output/", "dist/frontend"],
            "notes": [
                "Estructura basada en funcionalidades y componentes reutilizables.",
                "Coloca el código fuente en src/ y los estáticos en public/.",
            ],
            "is_new_project": new_project,
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
            "canonical_paths": ["backend/", "tests/", "config/"],
            "forbidden_paths": ["output/", "frontend/"],
            "notes": [
                "Separa la lógica de dominio, rutas y tests.",
                "No mezcles la salida del backend con estructuras de frontend.",
                "Los tests son obligatorios antes de cerrar cualquier tarea backend.",
            ],
            "is_new_project": new_project,
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
            "canonical_paths": ["app/", "resources/", "public/", "tests/", "database/", "routes/"],
            "forbidden_paths": ["output/"],
            "notes": [
                "Respeta la convención estándar de Laravel.",
                "Si el brief describe una feature sobre una app Laravel existente, trabaja dentro de su estructura actual.",
            ],
            "is_new_project": new_project,
        }

    if "documentation" in text or "docs" in text or "markdown" in text:
        return {
            "kind": "documentation",
            "root": repo_root,
            "entrypoint": "root",
            "directories": {
                "docs": "docs/",
            },
            "canonical_paths": ["docs/", ""],
            "forbidden_paths": ["output/"],
            "notes": [
                "Organiza la documentación en Markdown con encabezados claros.",
            ],
            "is_new_project": new_project,
        }

    return {
        "kind": "general",
        "root": repo_root,
        "entrypoint": "root",
        "directories": {},
        "canonical_paths": [],
        "forbidden_paths": ["output/"],
        "notes": [
            "Usa la estructura que ya exista en el repositorio.",
        ],
        "is_new_project": new_project,
    }


def is_new_project(project: dict[str, Any]) -> bool:
    """Return True when the project brief describes a new project (not a feature)."""
    description = (project.get("description") or "").lower()
    name = (project.get("name") or "").lower()
    return not _brief_mentions_feature_scope(description + " " + name)


def validate_project_structure(
    execution_dir: str,
    project: dict[str, Any],
    task: dict[str, Any],
    *,
    files_written: list[str] | None = None,
) -> list[str]:
    """Validate that execution_dir and written files do not conflict with the canonical structure.

    - Pre-execution: called with files_written=None to check the declared execution_dir.
    - Post-execution: called with files_written=[...] to detect files that landed outside
      the canonical boundaries.

    Returns a list of violation messages. An empty list means valid.
    """
    violations: list[str] = []
    structure = project.get("project_structure") or infer_project_structure(project, task)
    kind = str(structure.get("kind") or "general")
    forbidden: list[str] = list(structure.get("forbidden_paths") or FORBIDDEN_PATHS_DEFAULT)
    canonical: list[str] = list(structure.get("canonical_paths") or [])

    exec_norm = execution_dir.replace("\\", "/").lower()

    # Pre-execution: check that the declared execution_dir is not forbidden
    for bad in forbidden:
        if bad.lower() in exec_norm:
            violations.append(
                f"[Fase 0] El directorio de ejecucion '{execution_dir}' "
                f"contiene la ruta prohibida '{bad}' para proyectos de tipo '{kind}'. "
                f"Usa la estructura canonica: {structure.get('directories') or '{}'}"
            )

    # Post-execution: check that each file landed inside execution_dir or a canonical path
    if files_written:
        exec_dir_path = Path(execution_dir).resolve() if execution_dir else None
        canonical_list = canonical or []
        canonical_paths = [Path(p).resolve() for p in canonical_list if p]
        forbidden_list = forbidden or []
        for fpath_str in files_written:
            fpath = Path(fpath_str).resolve()
            inside_exec = exec_dir_path and (
                fpath == exec_dir_path or exec_dir_path in fpath.parents
            )
            inside_canonical = any(
                fpath == cp or cp in fpath.parents for cp in canonical_paths
            )
            for bad in forbidden_list:
                bad_norm = str(bad).lower().replace("\\", "/")
                if bad_norm in fpath_str.replace("\\", "/").lower():
                    violations.append(
                        f"[Fase 3] Archivo '{fpath_str}' escrito en ruta prohibida '{bad}'. "
                        f"Debería estar en: {execution_dir}"
                    )
            if canonical_paths and not inside_exec and not inside_canonical:
                violations.append(
                    f"[Fase 3] Archivo '{fpath_str}' está fuera del directorio de ejecución "
                    f"'{execution_dir}' y de las rutas canónicas declaradas."
                )

    return violations


def collect_task_expected_files(task: dict[str, Any], project: dict[str, Any], execution_dir: str) -> list[str]:
    """Infer files that a task is realistically expected to touch/create based on acceptance criteria."""
    explicit_files = task.get("files")
    if isinstance(explicit_files, list):
        normalized_explicit = [
            str(item).strip()
            for item in explicit_files
            if isinstance(item, str) and str(item).strip()
        ]
        if normalized_explicit:
            return sorted(dict.fromkeys(normalized_explicit))

    expected: set[str] = set()
    acceptance = [str(x) for x in task.get("acceptance", []) if isinstance(x, str)]
    
    for acc in acceptance:
        words = acc.split()
        for w in words:
            clean_w = w.strip("`'\".,;:()[]{}*").replace("\\", "/")
            if "/" in clean_w and "." in clean_w:
                expected.add(clean_w)
            elif clean_w.endswith(".py") or clean_w.endswith(".ts") or clean_w.endswith(".tsx") or clean_w.endswith(".js") or clean_w.endswith(".html") or clean_w.endswith(".css") or clean_w.endswith(".json") or clean_w.endswith(".md"):
                expected.add(clean_w)
                
    return sorted(list(expected))


def check_existing_task_artifacts(task: dict[str, Any], project: dict[str, Any], repo_state: dict[str, Any] | None = None) -> list[str]:
    """Check if the files that the task promises to create already exist and have content.
    Returns the absolute paths of the found files.
    """
    execution_dir = task.get("execution_dir") or infer_task_execution_dir(project, task, repo_state)
    expected = collect_task_expected_files(task, project, execution_dir)
    
    if not expected:
        return []
        
    found: list[str] = []
    repo_path = Path((repo_state or {}).get("repo_path") or project.get("repo_path") or project.get("output_dir") or "./output").resolve()
    exec_path = Path(execution_dir).resolve()
    
    for rel_path in expected:
        # Check against execution_dir
        p = (exec_path / rel_path).resolve()
        if p.exists() and p.is_file() and p.stat().st_size > 10:
            found.append(str(p))
            continue
            
        # Check against project root
        p2 = (repo_path / rel_path).resolve()
        if p2.exists() and p2.is_file() and p2.stat().st_size > 10:
            found.append(str(p2))
            continue
            
    return found


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
                "La estructura canónica es raíz/index.html + css/ + js/ + assets/; evita buffers externos fuera del repo.",
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


def materialize_planned_project(
    mem: dict[str, Any],
    plan_json: dict[str, Any],
    brief: str,
) -> dict[str, Any]:
    """Normalize a planning response into MEMORY and persist the project state."""
    plan_payload = plan_json if isinstance(plan_json, dict) else {}
    project_patch_raw = plan_payload.get("project", {})
    project_patch = project_patch_raw if isinstance(project_patch_raw, dict) else {}

    mem["tasks"] = []
    mem["blockers"] = []
    mem["proposals"] = []
    mem["milestones"] = []
    mem["files_produced"] = []
    mem["progress_files"] = []
    mem.setdefault("project", {})

    project_structure = project_patch.get("project_structure") or infer_project_structure(
        {
            "name": project_patch.get("name") or mem["project"].get("name"),
            "description": project_patch.get("description") or mem["project"].get("description") or brief,
            "tech_stack": project_patch.get("tech_stack") or mem["project"].get("tech_stack", {}),
            "repo_path": mem["project"].get("repo_path"),
            "output_dir": mem["project"].get("output_dir"),
        },
        {},
    )
    mem["project"].update(
        {
            **project_patch,
            "id": project_patch.get("id") or ensure_project_id(project_patch),
            "status": "planned",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "project_structure": project_structure,
        }
    )
    plan_value = plan_payload.get("plan")
    mem["plan"] = plan_value if isinstance(plan_value, dict) else {"phases": []}
    mem["milestones"] = plan_payload.get("milestones", [])
    update_project_history(mem)

    all_tasks: list[dict[str, Any]] = []
    task_skill_summary: dict[str, list[str]] = {}
    for phase in mem["plan"].get("phases", []):
        for task in phase.get("tasks", []):
            task["phase"] = phase.get("id")
            task["status"] = "pending"
            profile = build_task_skill_profile(mem["project"], task)
            task["execution_dir"] = infer_task_execution_dir(mem["project"], task, repo_state=None)
            task_files = task.get("files")
            if isinstance(task_files, list):
                task_files = [
                    str(item).strip()
                    for item in task_files
                    if isinstance(item, str) and str(item).strip()
                ]
            else:
                task_files = []
            if not task_files:
                task_files = collect_task_expected_files(task, mem["project"], task["execution_dir"])
            task["files"] = list(dict.fromkeys(task_files))
            task["skill_family"] = profile["family"]
            task["skill_profile"] = profile
            task["skills"] = profile["skills"]
            task["workspace_notes"] = profile["instructions"]
            task_skill_summary[task["id"]] = profile["skills"]
            all_tasks.append(task)

    mem["tasks"] = all_tasks
    mem["project"]["task_skill_summary"] = task_skill_summary
    refresh_project_runtime_state(mem)
    save_memory(mem)
    return {
        "tasks": all_tasks,
        "task_skill_summary": task_skill_summary,
        "project_structure": project_structure,
    }


def build_project_context(mem: dict[str, Any], repo_state: dict[str, Any]) -> str:
    """Build a JSON context string for agent prompts."""
    task_skill_map = {
        task["id"]: {
            "skills": task.get("skills", []),
            "skill_family": task.get("skill_family"),
            "workspace_notes": task.get("workspace_notes", []),
            "execution_dir": task.get("execution_dir"),
        }
        for task in mem.get("tasks", [])
        if isinstance(task, dict) and task.get("id")
    }
    task_files_map = {
        task["id"]: collect_task_expected_files(task, mem.get("project", {}), str(task.get("execution_dir") or ""))
        for task in mem.get("tasks", [])
        if isinstance(task, dict) and task.get("id")
    }
    context = {
        "project": mem.get("project", {}),
        "repo": repo_state,
        "milestones": mem.get("milestones", []),
        "task_skill_map": task_skill_map,
        "task_files_map": task_files_map,
        "output_dir": mem.get("project", {}).get("output_dir", "./output"),
        "execution_dir_map": {
            task.get("id"): task.get("execution_dir")
            for task in mem.get("tasks", [])
            if isinstance(task, dict) and task.get("id")
        },
    }
    return json.dumps(context, indent=2, ensure_ascii=False)


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
        
    expected_files = collect_task_expected_files(task, project, execution_dir)
    if expected_files:
        lines.append("")
        lines.append("## Archivos esperados (Fase 3)")
        lines.extend(f"- {f}" for f in expected_files)
        
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
    base_workspace_root = _agent_base_workspace_root(agent_id)
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

    if base_workspace_root != workspace_root:
        base_workspace_root.mkdir(parents=True, exist_ok=True)
        base_context_md_path = base_workspace_root / "active_task.md"
        base_context_json_path = base_workspace_root / "active_task.json"
        base_progress_root = base_workspace_root / "progress"
        base_progress_root.mkdir(parents=True, exist_ok=True)
        _safe_write_workspace_file(base_context_md_path, context_md_path.read_text(encoding="utf-8"))
        _safe_write_workspace_file(
            base_context_json_path,
            context_json_path.read_text(encoding="utf-8"),
        )
        (base_progress_root / f"{task_id}.json").write_text(
            progress_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

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
    base_workspace_root = _agent_base_workspace_root(agent_id)
    progress_root = workspace_root / "progress"
    workspace_root.mkdir(parents=True, exist_ok=True)
    progress_root.mkdir(parents=True, exist_ok=True)

    task_id = task.get("id", "task")
    timestamp = datetime.utcnow().isoformat()
    execution_dir = task.get("execution_dir") or infer_task_execution_dir(project, task, repo_state)
    expected_files = collect_task_expected_files(task, project, execution_dir)
    
    context_md = render_task_context_md(agent_id, task, project, skill_profile, repo_state)
    context_json = {
        "agent": agent_id,
        "task": task,
        "execution_dir": execution_dir,
        "expected_files": expected_files,
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

    if base_workspace_root != workspace_root:
        base_workspace_root.mkdir(parents=True, exist_ok=True)
        _safe_write_workspace_file(base_workspace_root / "active_task.md", context_md)
        _safe_write_workspace_file(
            base_workspace_root / "active_task.json",
            json.dumps(context_json, indent=2, ensure_ascii=False),
        )
        base_progress_root = base_workspace_root / "progress"
        base_progress_root.mkdir(parents=True, exist_ok=True)
        (base_progress_root / f"{task_id}.json").write_text(
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

# ---------------------------------------------------------------------------
# Inspección y validación de contenido (Fase 2)
# ---------------------------------------------------------------------------

OUTPUT_DIR = BASE_DIR / "output"


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


def _safe_workspace_path(base_dir: Path, raw_path: str) -> Path:
    """Resolve a task-provided path and keep it inside *base_dir*."""
    candidate = Path(raw_path)
    if candidate.is_absolute():
        raise ValueError(f"Ruta absoluta no permitida: {raw_path}")
    if any(part == ".." for part in candidate.parts):
        raise ValueError(f"Ruta insegura no permitida: {raw_path}")

    resolved_base = base_dir.resolve()
    resolved_target = (base_dir / candidate).resolve()
    try:
        resolved_target.relative_to(resolved_base)
    except ValueError as exc:
        raise ValueError(f"Ruta fuera del workspace: {raw_path}") from exc
    return resolved_target


def _resolve_task_artifact_path(raw_path: str, project: dict[str, Any]) -> Path | None:
    """Resolve a stored task artifact path against the known project roots."""
    candidate = Path(raw_path)
    if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
        return None

    output_dir = resolve_path(project.get("output_dir"), OUTPUT_DIR).resolve()
    base_dir = BASE_DIR.resolve()
    cleaned = candidate.as_posix()

    roots: list[Path] = []
    try:
        project_root_rel = output_dir.relative_to(base_dir).as_posix()
    except ValueError:
        project_root_rel = ""

    if project_root_rel and cleaned.startswith(f"{project_root_rel}/"):
        suffix = cleaned[len(project_root_rel) + 1 :]
        roots.append((base_dir / cleaned).resolve())
        if suffix:
            roots.append((output_dir / suffix).resolve())
    else:
        roots.append((output_dir / cleaned).resolve())
        roots.append((base_dir / cleaned).resolve())

    for root in roots:
        if root.exists():
            return root
    return None


def _read_text_if_exists(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _task_file_map(task: dict[str, Any], project: dict[str, Any]) -> dict[str, str]:
    file_map: dict[str, str] = {}
    for rel_path in task.get("files", []) or []:
        if not isinstance(rel_path, str) or not rel_path.strip():
            continue
        abs_path = _resolve_task_artifact_path(rel_path, project)
        if abs_path is not None:
            file_map[normalize_output_path(abs_path)] = _read_text_if_exists(abs_path)
    return file_map


def _check_fastapi_task_content(task: dict[str, Any], project: dict[str, Any]) -> list[str]:
    """Inspect FastAPI task outputs for real content, not just filenames."""
    file_map = _task_file_map(task, project)
    files = set(file_map.keys())
    issues: list[str] = []

    requirements = next((content for path, content in file_map.items() if path.endswith("requirements.txt")), "")
    main_py = next((content for path, content in file_map.items() if path.endswith("main.py")), "")
    database_py = next((content for path, content in file_map.items() if path.endswith("database.py")), "")
    env_file = next((content for path, content in file_map.items() if path.endswith(".env")), "")

    if not any(path.endswith("backend/requirements.txt") or path.endswith("requirements.txt") for path in files):
        issues.append("falta requirements.txt")
    else:
        expected_pkgs = ["fastapi", "uvicorn", "sqlalchemy", "pydantic"]
        missing = [pkg for pkg in expected_pkgs if pkg not in requirements.lower()]
        if missing:
            issues.append(f"requirements.txt incompleto: faltan {', '.join(missing)}")

    if not any(path.endswith("backend/main.py") or path.endswith("main.py") for path in files):
        issues.append("falta main.py")
    else:
        if "fastapi(" not in main_py.lower() and "fastapi()" not in main_py.lower():
            issues.append("main.py no declara app FastAPI")
        if "cors" not in main_py.lower() and "corsmiddleware" not in main_py.lower():
            issues.append("main.py no configura CORS")

    if not any(path.endswith("backend/database.py") or path.endswith("database.py") for path in files):
        issues.append("falta database.py")
    else:
        if "sqlalchemy" not in database_py.lower() and "create_engine" not in database_py.lower():
            issues.append("database.py no configura SQLAlchemy")
        if "sqlite" not in database_py.lower():
            issues.append("database.py no referencia SQLite")

    if not env_file.strip():
        issues.append(".env vacío o ausente")

    for folder in ("models", "schemas", "routes"):
        if not any(f"/{folder}/" in path or path.startswith(f"{folder}/") for path in files):
            issues.append(f"falta estructura {folder}/")

    test_files = [
        path for path in files
        if path.startswith("tests/")
        or "/tests/" in path
        or Path(path).name.startswith("test_")
        or Path(path).name.endswith("_test.py")
    ]
    if not test_files:
        issues.append("faltan tests unitarios o de integración para backend")
    else:
        test_content = "\n".join(file_map[path] for path in test_files)
        if "pytest" not in test_content.lower() and "testclient" not in test_content.lower() and "assert " not in test_content.lower():
            issues.append("los tests backend no parecen ejecutar aserciones reales")

    return issues


def _check_vanilla_frontend_task_content(task: dict[str, Any], project: dict[str, Any]) -> list[str]:
    """Inspect vanilla frontend task outputs for semantic HTML/CSS/JS content."""
    file_map = _task_file_map(task, project)
    files = set(file_map.keys())
    issues: list[str] = []
    html = next((content for path, content in file_map.items() if path.endswith("index.html")), "")
    css = next((content for path, content in file_map.items() if path.endswith("styles.css")), "")
    js = next((content for path, content in file_map.items() if path.endswith(".js")), "")

    if any(path.endswith("index.html") for path in files):
        if "<!doctype html>" not in html.lower():
            issues.append("index.html no declara HTML5")
        if "<meta charset" not in html.lower():
            issues.append("index.html sin meta charset")
        if "viewport" not in html.lower():
            issues.append("index.html sin meta viewport")
    if any(path.endswith("styles.css") for path in files):
        if "body" not in css.lower():
            issues.append("styles.css parece incompleto")
    if any(path.endswith(".js") for path in files):
        if "localstorage" not in js.lower() and "queryselector" not in js.lower():
            issues.append("JavaScript sin lógica funcional aparente")
    return issues


def _check_documentation_task_content(task: dict[str, Any], project: dict[str, Any]) -> list[str]:
    file_map = _task_file_map(task, project)
    issues: list[str] = []
    readme = next((content for path, content in file_map.items() if path.lower().endswith("readme.md")), "")
    if not readme.strip():
        issues.append("README.md ausente o vacío")
    else:
        expected_sections = ["instal", "uso", "soluci", "proble", "ejempl"]
        if not any(token in readme.lower() for token in expected_sections):
            issues.append("README.md carece de secciones operativas")
    return issues


def check_task_content(task: dict[str, Any], project: dict[str, Any]) -> list[str]:
    """Consolidated entry point for task content validation (Fase 2)."""
    family = str(task.get("skill_family") or task.get("skill_profile", {}).get("family") or "").lower()

    if family == "fastapi":
        return _check_fastapi_task_content(task, project)
    elif family in {"vanilla-frontend", "frontend"}:
        return _check_vanilla_frontend_task_content(task, project)
    elif family == "documentation":
        return _check_documentation_task_content(task, project)

    return []


def has_open_tasks(tasks: list[dict[str, Any]]) -> bool:
    """Return True when at least one task is still pending, running, or blocked."""
    return any(task.get("status") != "done" for task in tasks if isinstance(task, dict))


def has_tasks_needing_correction(tasks: list[dict[str, Any]]) -> bool:
    """Return True when a task is waiting for correction before delivery."""
    return any(task.get("review_status") == "needs_correction" for task in tasks if isinstance(task, dict))


def task_matches_acceptance(task: dict[str, Any], project: dict[str, Any]) -> tuple[bool, list[str]]:
    """Lightweight final validation to catch obvious mismatches before delivery."""
    acceptance = [str(item).lower() for item in (task.get("acceptance") or []) if isinstance(item, str)]
    notes = [str(task.get("notes") or "").lower(), str(task.get("raw_response") or "").lower()]
    files = [str(path).lower() for path in _task_files_for_review(task, project)]
    observations: list[str] = []

    if not files:
        observations.append(f"{task.get('id')}: sin archivos escritos")

    for requirement in acceptance:
        if "backend/" in requirement and not any("backend/" in f for f in files):
            observations.append("falta backend/")
        if "requirements.txt" in requirement and not any("requirements.txt" in f for f in files):
            observations.append("falta requirements.txt")
        if "main.py" in requirement and not any("main.py" in f for f in files):
            observations.append("falta main.py")
        if "database.py" in requirement and not any("database.py" in f for f in files):
            observations.append("falta database.py")
        if "models/" in requirement and not any("models/" in f for f in files):
            observations.append("falta models/")
        if "schemas/" in requirement and not any("schemas/" in f for f in files):
            observations.append("falta schemas/")
        if "routes/" in requirement and not any("routes/" in f for f in files):
            observations.append("falta routes/")

    if any(re.search(r"\b(todo|placeholder|ok)\b", note) for note in notes if note):
        observations.append("notes/resultado demasiado generico")

    observations.extend(check_task_content(task, project))

    execution_dir = str(task.get("execution_dir") or "")
    if files:
        structure_violations = validate_project_structure(execution_dir, project, task, files_written=files)
        observations.extend(structure_violations)

    return (not observations, observations)


def record_task_review(task_id: str, review_round: int, issues: list[str]) -> None:
    """Persist the review result for a task in shared memory."""
    mem = load_memory()
    for task in mem.get("tasks", []):
        if task.get("id") != task_id:
            continue
        task["review_round"] = review_round
        task["review_issues"] = issues
        task["review_status"] = "needs_correction" if issues else "passed"
        task["updated_at"] = utc_now()
    refresh_project_runtime_state(mem)
    save_memory(mem)

def _task_files_existing(task: dict[str, Any], project: dict[str, Any]) -> list[str]:
    files = []
    for raw_path in task.get("files", []) or []:
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        candidate = _resolve_task_artifact_path(raw_path, project)
        if candidate is not None:
            files.append(str(candidate))
    return files


def _task_files_from_manifest(task: dict[str, Any], project: dict[str, Any]) -> list[str]:
    """Fallback file list sourced from PROJECT_MANIFEST.json."""
    output_dir = resolve_path(project.get("output_dir"), OUTPUT_DIR)
    manifest_path = output_dir / "PROJECT_MANIFEST.json"
    if not manifest_path.exists():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    task_id = task.get("id")
    if not task_id:
        return []

    results = []
    for f_entry in manifest.get("files", []):
        if f_entry.get("task_id") == task_id:
            results.append(str(output_dir / f_entry["path"]))
    return results


def _task_files_for_review(task: dict[str, Any], project: dict[str, Any]) -> list[str]:
    """Return the best available file list for review checks."""
    files = _task_files_existing(task, project)
    if files:
        return files
    return _task_files_from_manifest(task, project)


def _task_files_for_manifest(task: dict[str, Any], project: dict[str, Any]) -> list[str]:
    """Return resolved file paths for the project manifest."""
    files: list[str] = []
    for raw_path in task.get("files", []) or []:
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        candidate = _resolve_task_artifact_path(raw_path, project)
        if candidate is not None:
            files.append(normalize_output_path(candidate))
    return files


def _project_artifact_entries(mem: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    project = mem.setdefault("project", {})
    tasks = [task for task in mem.get("tasks", []) if isinstance(task, dict)]
    task_entries: list[dict[str, Any]] = []
    file_entries: list[dict[str, Any]] = []

    for task in tasks:
        task_files = _task_files_for_manifest(task, project)
        task_entries.append(
            {
                "id": task.get("id"),
                "title": task.get("title"),
                "agent": task.get("agent"),
                "status": task.get("status"),
                "skill_family": task.get("skill_family"),
                "failure_count": task.get("failure_count", 0),
                "next_action": task.get("next_action"),
                "files": task_files,
                "notes": task.get("notes"),
            }
        )
        for path in task_files:
            file_entries.append(
                {
                    "task_id": task.get("id"),
                    "agent": task.get("agent"),
                    "path": path,
                }
            )

    return project, task_entries, file_entries


def synchronize_project_artifacts(mem: dict[str, Any]) -> dict[str, Any]:
    """Write project manifest, index, and evidence files for the dashboard."""
    project, task_entries, file_entries = _project_artifact_entries(mem)
    output_dir = resolve_path(project.get("output_dir"), OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "project": {
            "id": project.get("id"),
            "name": project.get("name"),
            "status": project.get("status"),
            "runtime_status": project.get("runtime_status"),
            "repo_path": project.get("repo_path"),
            "output_dir": project.get("output_dir"),
            "branch": project.get("branch"),
            "updated_at": project.get("updated_at"),
        },
        "generated_at": utc_now(),
        "task_count": len(task_entries),
        "file_count": len(file_entries),
        "tasks": task_entries,
        "files": file_entries,
    }

    manifest_path = output_dir / "PROJECT_MANIFEST.json"
    index_path = output_dir / "PROJECT_INDEX.md"
    evidence_path = output_dir / "evidence.json"

    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        f"# {project.get('name') or project.get('id') or 'Project'}",
        "",
        f"- Project ID: {project.get('id') or 'N/A'}",
        f"- Runtime status: {project.get('runtime_status') or project.get('status') or 'idle'}",
        f"- Tasks: {len(task_entries)}",
        f"- Files: {len(file_entries)}",
        "",
        "## Task Map",
        "",
    ]
    for entry in task_entries:
        lines.append(f"### {entry['id']} - {entry['title'] or 'Sin titulo'}")
        lines.append(f"- Agent: {entry.get('agent') or 'N/A'}")
        lines.append(f"- Status: {entry.get('status') or 'N/A'}")
        if entry.get("skill_family"):
            lines.append(f"- Skill family: {entry.get('skill_family')}")
        if entry.get("next_action"):
            lines.append(f"- Next action: {entry.get('next_action')}")
        if entry.get("files"):
            lines.append("- Files:")
            for path in entry["files"]:
                lines.append(f"  - {path}")
        else:
            lines.append("- Files: none")
        lines.append("")

    if file_entries:
        lines.extend(["## Unified Files", ""])
        for item in file_entries:
            lines.append(f"- {item['path']}  ({item.get('task_id')})")
    else:
        lines.extend(["## Unified Files", "", "- No files produced yet."])

    index_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    evidence_payload = {
        "project": manifest["project"],
        "generated_at": manifest["generated_at"],
        "summary": {
            "task_count": manifest["task_count"],
            "file_count": manifest["file_count"],
            "done_tasks": sum(1 for task in task_entries if task.get("status") == "done"),
            "open_tasks": sum(1 for task in task_entries if task.get("status") != "done"),
        },
        "artifacts": {
            "manifest": normalize_output_path(manifest_path),
            "index": normalize_output_path(index_path),
            "evidence": normalize_output_path(evidence_path),
        },
        "tasks": task_entries,
        "files": file_entries,
    }
    evidence_path.write_text(
        json.dumps(evidence_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    project["artifact_manifest"] = str(manifest_path)
    project["artifact_index"] = str(index_path)
    project["artifact_evidence"] = str(evidence_path)
    project["artifacts_updated_at"] = utc_now()
    project["artifact_file_count"] = len(file_entries)
    project["artifact_task_count"] = len(task_entries)
    refresh_project_runtime_state(mem)
    save_memory(mem)
    return manifest


def _compact_review_memory(mem: dict[str, Any]) -> dict[str, Any]:
    """Return a trimmed review payload to keep ARCH under context limits."""
    project = mem.get("project") if isinstance(mem.get("project"), dict) else {}
    plan = mem.get("plan") if isinstance(mem.get("plan"), dict) else {}
    tasks = mem.get("tasks") if isinstance(mem.get("tasks"), list) else []
    agents = mem.get("agents") if isinstance(mem.get("agents"), dict) else {}
    blockers = mem.get("blockers") if isinstance(mem.get("blockers"), list) else []
    proposals = mem.get("proposals") if isinstance(mem.get("proposals"), list) else []
    milestones = mem.get("milestones") if isinstance(mem.get("milestones"), list) else []
    files_produced = mem.get("files_produced") if isinstance(mem.get("files_produced"), list) else []
    progress_files = mem.get("progress_files") if isinstance(mem.get("progress_files"), list) else []

    def _compact_task(task: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": task.get("id"),
            "agent": task.get("agent"),
            "title": task.get("title"),
            "status": task.get("status"),
            "failure_kind": task.get("failure_kind"),
            "retryable": task.get("retryable"),
            "error": task.get("error"),
            "next_action": task.get("next_action"),
            "files": task.get("files"),
            "notes": task.get("notes"),
            "last_failure_at": task.get("last_failure_at"),
            "progress_file": task.get("progress_file"),
            "workspace_context": task.get("workspace_context"),
        }

    def _compact_phase(phase: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": phase.get("id"),
            "name": phase.get("name"),
            "tasks": [
                {
                    "id": t.get("id"),
                    "agent": t.get("agent"),
                    "title": t.get("title"),
                    "status": t.get("status"),
                    "depends_on": t.get("depends_on"),
                }
                for t in (phase.get("tasks") if isinstance(phase.get("tasks"), list) else [])[:20]
            ],
        }

    compact_agents = {
        agent_id: {
            "status": data.get("status"),
            "current_task": data.get("current_task"),
            "last_seen": data.get("last_seen"),
        }
        for agent_id, data in agents.items()
        if isinstance(data, dict)
    }

    return {
        "schema_version": mem.get("schema_version"),
        "project": {
            "id": project.get("id"),
            "name": project.get("name"),
            "description": project.get("description"),
            "repo_path": project.get("repo_path"),
            "output_dir": project.get("output_dir"),
            "branch": project.get("branch"),
            "status": project.get("status"),
            "runtime_status": project.get("runtime_status"),
            "blocked_reason": project.get("blocked_reason"),
            "task_counts": project.get("task_counts"),
            "project_structure": project.get("project_structure"),
        },
        "plan": {
            "current_phase": plan.get("current_phase"),
            "phases": [_compact_phase(phase) for phase in (plan.get("phases") if isinstance(plan.get("phases"), list) else [])[:10]],
        },
        "tasks": [_compact_task(task) for task in tasks[:20]],
        "agents": compact_agents,
        "blockers": blockers[:10],
        "proposals": proposals[:10],
        "milestones": milestones[:10],
        "files_produced": files_produced[:20],
        "progress_files": progress_files[:20],
        "meta": {
            "task_count": len(tasks),
            "project_count": len(mem.get("projects", [])) if isinstance(mem.get("projects"), list) else None,
            "messages_count": len(mem.get("messages", [])) if isinstance(mem.get("messages"), list) else None,
            "log_count": len(mem.get("log", [])) if isinstance(mem.get("log"), list) else None,
        },
    }


def _compact_coordination_messages(messages: list[dict[str, Any]], limit: int = 40) -> list[dict[str, Any]]:
    """Return a compact, bounded message list for ARCH coordination calls."""
    compacted: list[dict[str, Any]] = []

    for msg in messages[-limit:]:
        if not isinstance(msg, dict):
            continue

        compact: dict[str, Any] = {
            "id": msg.get("id"),
            "from": msg.get("from"),
            "to": msg.get("to"),
            "message": msg.get("message") or msg.get("text") or msg.get("content") or "",
            "received_at": msg.get("received_at"),
        }

        for key in ("task_id", "kind", "relay_status", "source", "in_reply_to"):
            value = msg.get(key)
            if value is not None:
                compact[key] = value

        raw = msg.get("raw")
        if isinstance(raw, dict):
            raw_summary = {
                key: raw.get(key)
                for key in ("id", "type", "event", "state", "seq", "task_id", "from", "to", "sessionKey", "session_id")
                if raw.get(key) is not None
            }
            if raw_summary:
                compact["raw_summary"] = raw_summary

        message_text = str(compact.get("message") or "").strip()
        if len(message_text) > 1200:
            compact["message"] = f"{message_text[:1200]}…"

        compacted.append(compact)

    return compacted
