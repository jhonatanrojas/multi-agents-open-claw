"""
skills/plugins/ - Sistema de Skills Extensible

Cada skill es un módulo Python independiente que puede:
- Detectar si aplica a un proyecto
- Mejorar el prompt para tareas específicas
- Validar la salida generada

Para añadir un nuevo skill:
1. Crear archivo en skills/plugins/<nombre>.py
2. Definir SKILL_META con metadatos
3. Implementar funciones detect(), enhance_prompt(), validate_output()
"""

# Skills discovery y registry

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from enum import Enum

log = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).resolve().parent
PLUGINS_DIR = SKILLS_DIR / "plugins"


class SkillPriority(Enum):
    CRITICAL = 10  # Siempre aplicar (ej: seguridad)
    HIGH = 20      # Aplicar antes que otros
    NORMAL = 30    # Prioridad por defecto
    LOW = 40       # Aplicar si otros no coinciden


@dataclass
class SkillMeta:
    """Metadatos de un skill."""
    name: str
    family: str  # backend, frontend, devops, documentation
    stacks: list[str] = field(default_factory=list)  # ej: ["laravel", "php"]
    tools: list[str] = field(default_factory=list)  # ej: ["artisan", "composer"]
    file_patterns: list[str] = field(default_factory=list)  # ej: ["*.blade.php"]
    priority: int = SkillPriority.NORMAL.value
    description: str = ""
    
    # Funciones opcionales
    detect_func: Callable | None = None
    enhance_func: Callable | None = None
    validate_func: Callable | None = None


# Registry de skills
_SKILL_REGISTRY: dict[str, SkillMeta] = {}


def register_skill(skill: SkillMeta) -> None:
    """Registrar un skill en el registry."""
    _SKILL_REGISTRY[skill.name] = skill
    log.info(f"[skills] Registered skill: {skill.name} (family={skill.family})")


def get_skill(name: str) -> SkillMeta | None:
    """Obtener un skill por nombre."""
    return _SKILL_REGISTRY.get(name)


def get_skills_for_stack(stack: str) -> list[SkillMeta]:
    """Obtener skills que aplican a un stack."""
    return [
        s for s in _SKILL_REGISTRY.values()
        if stack.lower() in [st.lower() for st in s.stacks]
    ]


def get_skills_for_file(filename: str) -> list[SkillMeta]:
    """Obtener skills que aplican a un archivo."""
    import fnmatch
    results = []
    for skill in _SKILL_REGISTRY.values():
        for pattern in skill.file_patterns:
            if fnmatch.fnmatch(filename, pattern):
                results.append(skill)
                break
    return results


def detect_skills(project_structure: dict[str, Any]) -> list[SkillMeta]:
    """
    Detectar skills que aplican a un proyecto.
    
    Args:
        project_structure: Estructura del proyecto con archivos y directorios
        
    Returns:
        Lista de skills detectados, ordenados por prioridad
    """
    detected = []
    
    for skill in _SKILL_REGISTRY.values():
        # Verificar por stack
        project_stack = project_structure.get("stack", "").lower()
        if project_stack in [s.lower() for s in skill.stacks]:
            detected.append(skill)
            continue
        
        # Verificar por herramientas
        project_tools = project_structure.get("tools", [])
        if any(t in skill.tools for t in project_tools):
            detected.append(skill)
            continue
        
        # Verificar por archivos
        project_files = project_structure.get("files", [])
        for f in project_files:
            if any(
                f.endswith(pattern.replace("*", ""))
                for pattern in skill.file_patterns
            ):
                detected.append(skill)
                break
        
        # Usar función de detección personalizada si existe
        if skill.detect_func:
            try:
                if skill.detect_func(project_structure):
                    detected.append(skill)
            except Exception as e:
                log.warning(f"[skills] Detection failed for {skill.name}: {e}")
    
    # Ordenar por prioridad
    detected.sort(key=lambda s: s.priority)
    return detected


def enhance_prompt(
    task: dict[str, Any],
    context: str,
    skills: list[SkillMeta] | None = None,
) -> str:
    """
    Mejorar el prompt de una tarea con skills aplicables.
    
    Args:
        task: Tarea con id, title, description, skills
        context: Contexto base del prompt
        skills: Skills a aplicar (si None, detectar automáticamente)
        
    Returns:
        Prompt mejorado con instrucciones específicas
    """
    enhanced = context
    
    # Obtener skills de la tarea o detectar
    if skills is None:
        task_skills = task.get("skills", [])
        skills = [get_skill(s) for s in task_skills if get_skill(s)]
    
    for skill in skills:
        if skill.enhance_func:
            try:
                enhanced = skill.enhance_func(task, enhanced)
            except Exception as e:
                log.warning(f"[skills] Enhancement failed for {skill.name}: {e}")
    
    return enhanced


def validate_output(
    files: list[dict[str, str]],
    skills: list[SkillMeta] | None = None,
) -> tuple[bool, list[str]]:
    """
    Validar archivos de salida con skills aplicables.
    
    Args:
        files: Lista de archivos con path y content
        skills: Skills a usar para validación
        
    Returns:
        Tupla (is_valid, list_of_issues)
    """
    issues = []
    
    for skill in (skills or []):
        if skill.validate_func:
            try:
                valid, skill_issues = skill.validate_func(files)
                if not valid:
                    issues.extend([f"[{skill.name}] {i}" for i in skill_issues])
            except Exception as e:
                issues.append(f"[{skill.name}] Validation error: {e}")
    
    return len(issues) == 0, issues


def discover_plugins() -> None:
    """
    Descubrir y cargar todos los plugins de skills.
    
    Busca en skills/plugins/*.py y registra cada skill.
    """
    if not PLUGINS_DIR.exists():
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        log.info(f"[skills] Created plugins directory: {PLUGINS_DIR}")
        return
    
    for plugin_file in PLUGINS_DIR.glob("*.py"):
        if plugin_file.name.startswith("_"):
            continue
        
        try:
            # Importar módulo
            module_name = plugin_file.stem
            spec = importlib.util.spec_from_file_location(
                f"skills.plugins.{module_name}",
                plugin_file
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Registrar si tiene SKILL_META
                if hasattr(module, "SKILL_META"):
                    meta_dict = module.SKILL_META
                    skill = SkillMeta(
                        name=meta_dict.get("name", module_name),
                        family=meta_dict.get("family", "general"),
                        stacks=meta_dict.get("stacks", []),
                        tools=meta_dict.get("tools", []),
                        file_patterns=meta_dict.get("file_patterns", []),
                        priority=meta_dict.get("priority", SkillPriority.NORMAL.value),
                        description=meta_dict.get("description", ""),
                        detect_func=getattr(module, "detect", None),
                        enhance_func=getattr(module, "enhance_prompt", None),
                        validate_func=getattr(module, "validate_output", None),
                    )
                    register_skill(skill)
                    
        except Exception as e:
            log.warning(f"[skills] Failed to load plugin {plugin_file}: {e}")


# Inicializar al importar
def _init_skills():
    """Inicializar sistema de skills."""
    discover_plugins()


# ── Skills básicos incluidos ───────────────────────────────────────────────────

# Skill para proyectos Laravel
LARAVEL_SKILL = SkillMeta(
    name="laravel",
    family="backend",
    stacks=["laravel", "php"],
    tools=["artisan", "composer"],
    file_patterns=["*.blade.php", "app/**/*.php", "routes/*.php"],
    priority=SkillPriority.HIGH.value,
    description="Laravel PHP framework specific guidance",
)

# Skill para proyectos React
REACT_SKILL = SkillMeta(
    name="react",
    family="frontend", 
    stacks=["react", "react-native", "nextjs"],
    tools=["npm", "yarn", "vite"],
    file_patterns=["*.tsx", "*.jsx", "src/**/*.tsx"],
    priority=SkillPriority.NORMAL.value,
    description="React/React Native specific guidance",
)

# Skill para API REST
REST_API_SKILL = SkillMeta(
    name="rest-api",
    family="backend",
    stacks=["fastapi", "express", "flask", "django"],
    tools=[],
    file_patterns=[],
    priority=SkillPriority.NORMAL.value,
    description="REST API best practices",
)

# Registrar skills básicos
register_skill(LARAVEL_SKILL)
register_skill(REACT_SKILL)
register_skill(REST_API_SKILL)
