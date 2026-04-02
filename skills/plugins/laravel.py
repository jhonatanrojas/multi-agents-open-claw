"""
Laravel Skill Plugin - Extensión para proyectos Laravel

Este plugin proporciona:
- Detección automática de proyectos Laravel
- Instrucciones específicas para tareas Laravel
- Validación de archivos Blade y Eloquent models
"""

from __future__ import annotations
from typing import Any

# Metadatos del skill
SKILL_META = {
    "name": "laravel",
    "family": "backend",
    "stacks": ["laravel", "php", "lumen"],
    "tools": ["artisan", "composer", "phpunit"],
    "file_patterns": ["*.blade.php", "app/Models/*.php", "routes/*.php", "database/migrations/*.php"],
    "priority": 20,  # HIGH
    "description": "Laravel framework guidance: Eloquent, Blade, migrations, validation",
}

# Instrucciones específicas para Laravel
LARAVEL_INSTRUCTIONS = """
## Laravel Best Practices

### Eloquent Models
- Usar $fillable o $guarded para protección de asignación masiva
- Definir relaciones con métodos claros: belongsTo, hasMany, belongsToMany
- Usar scopes para consultas frecuentes
- Añadir casts para atributos JSON/dates

### Blade Templates
- Usar @extends y @section para layouts
- Evitar lógica compleja en vistas, usar ViewComposers
- Usar @foreach, @forelse, @empty para iteraciones

### Migrations
- Nombrar descriptivamente: create_users_table, add_status_to_posts
- Usar $table->id() como convención
- Añadir foreign keys con constrained()

### Validation
- Usar Form Requests para validación compleja
- Mensajes de error personalizados en languaje files

### Testing
- Usar factories para crear datos de prueba
- Feature tests para endpoints, Unit tests para models
"""


def detect(project_structure: dict[str, Any]) -> bool:
    """
    Detectar si el proyecto es Laravel.
    
    Busca:
    - artisan en la raíz
    - composer.json con laravel/framework
    - Directorios típicos: app/, routes/, resources/views/
    """
    files = project_structure.get("files", [])
    directories = project_structure.get("directories", [])
    
    # Verificar artisan
    if "artisan" in files:
        return True
    
    # Verificar directorios típicos
    laravel_dirs = {"app", "routes", "resources", "config", "database"}
    if laravel_dirs.intersection(set(directories)):
        return True
    
    # Verificar por stack explícito
    stack = project_structure.get("stack", "").lower()
    if stack in ["laravel", "php", "lumen"]:
        return True
    
    return False


def enhance_prompt(task: dict[str, Any], context: str) -> str:
    """
    Mejorar el prompt con instrucciones Laravel.
    
    Añade:
    - Best practices de Laravel
    - Estructura esperada según tipo de tarea
    - Referencias a documentación
    """
    task_title = task.get("title", "").lower()
    task_desc = task.get("description", "").lower()
    
    # Añadir instrucciones base
    enhanced = f"{context}\n\n{LARAVEL_INSTRUCTIONS}"
    
    # Instrucciones específicas por tipo de tarea
    if "model" in task_title or "eloquent" in task_desc:
        enhanced += "\n\n### Para esta tarea de Model:\n"
        enhanced += "- Crear en app/Models/\n"
        enhanced += "- Incluir relaciones, casts, scopes\n"
        enhanced += "- Añadir factory si aplica\n"
    
    if "migration" in task_title or "migrat" in task_desc:
        enhanced += "\n\n### Para esta tarea de Migration:\n"
        enhanced += "- Usar php artisan make:migration\n"
        enhanced += "- Incluir down() method\n"
        enhanced += "- Nomenclatura: create_<table>_table\n"
    
    if "controller" in task_title or "api" in task_desc:
        enhanced += "\n\n### Para esta tarea de Controller:\n"
        enhanced += "- Usar Form Requests para validación\n"
        enhanced += "- Resource para respuestas API\n"
        enhanced += "- Incluir authorize() method\n"
    
    if "blade" in task_title or "view" in task_desc:
        enhanced += "\n\n### Para esta tarea de View:\n"
        enhanced += "- Crear en resources/views/\n"
        enhanced += "- Usar layout principal si existe\n"
        enhanced += "- Componentes para UI reutilizable\n"
    
    return enhanced


def validate_output(files: list[dict[str, str]]) -> tuple[bool, list[str]]:
    """
    Validar archivos Laravel generados.
    
    Verifica:
    - Modelos tienen $fillable o $guarded
    - Migrations tienen up() y down()
    - Controllers no tienen lógica de negocio
    """
    issues = []
    
    for file in files:
        path = file.get("path", "")
        content = file.get("content", "")
        
        # Validar Models
        if "app/Models/" in path and path.endswith(".php"):
            if "$fillable" not in content and "$guarded" not in content:
                issues.append(f"Model {path} necesita $fillable o $guarded")
            
            if "extends Model" in content and "use Illuminate\\" not in content:
                issues.append(f"Model {path} falta import de Model base")
        
        # Validar Migrations
        if "database/migrations/" in path:
            if "def up(" not in content:
                issues.append(f"Migration {path} necesita método up()")
            if "def down(" not in content:
                issues.append(f"Migration {path} necesita método down()")
        
        # Validar Controllers
        if "app/Http/Controllers/" in path:
            # Detectar lógica de negocio en controller (básico)
            if "DB::" in content or "query(" in content:
                issues.append(f"Controller {path} tiene lógica de BD - mover a Service")
    
    return len(issues) == 0, issues
