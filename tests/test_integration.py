"""
tests/test_integration.py - Tests de Integración del Sistema Multi-Agentes

Ejecutar con: pytest tests/test_integration.py -v
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Añadir directorio padre al path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestModelFallback:
    """Tests para el sistema de fallback de modelos."""
    
    def test_fallback_manager_initialization(self):
        """Verificar que el fallback manager se inicializa correctamente."""
        from model_fallback import ModelFallbackManager, DEFAULT_FALLBACK_CHAINS
        
        manager = ModelFallbackManager()
        
        assert manager.fallback_chains is not None
        assert "arch" in manager.fallback_chains
        assert "byte" in manager.fallback_chains
        assert "pixel" in manager.fallback_chains
    
    def test_get_fallback_chain(self):
        """Verificar obtención de cadena de fallback."""
        from model_fallback import ModelFallbackManager
        
        manager = ModelFallbackManager()
        
        chain = manager.get_fallback_chain("arch")
        
        assert isinstance(chain, list)
        assert len(chain) > 0
        assert "nvidia/z-ai/glm5" in chain or "deepseek" in chain[0].lower()
    
    def test_circuit_breaker_blocks_after_failures(self):
        """Verificar que el circuit breaker bloquea después de fallos."""
        from model_fallback import CircuitBreaker
        
        cb = CircuitBreaker(cooldown_seconds=300, max_failures=3)
        
        # Debe estar disponible al inicio
        assert cb.is_available("test-model") is True
        
        # Registrar 3 fallos
        for _ in range(3):
            cb.record_failure("test-model")
        
        # Ahora debe estar bloqueado
        assert cb.is_available("test-model") is False
    
    def test_circuit_breaker_resets_on_success(self):
        """Verificar que el circuit breaker se resetea con éxito."""
        from model_fallback import CircuitBreaker
        
        cb = CircuitBreaker()
        
        cb.record_failure("test-model")
        assert len(cb._failures.get("test-model", [])) == 1
        
        cb.record_success("test-model")
        assert len(cb._failures.get("test-model", [])) == 0
    
    def test_should_trigger_fallback_on_rate_limit(self):
        """Verificar detección de rate limits."""
        from model_fallback import should_trigger_fallback
        
        assert should_trigger_fallback("Rate limit exceeded", 429) is True
        assert should_trigger_fallback("API rate limit", None) is True
    
    def test_should_trigger_fallback_on_balance(self):
        """Verificar detección de saldo insuficiente."""
        from model_fallback import should_trigger_fallback
        
        assert should_trigger_fallback("Insufficient balance", 402) is True
        assert should_trigger_fallback("Quota exceeded", None) is True
    
    def test_error_categorization(self):
        """Verificar categorización de errores."""
        from model_fallback import ModelFallbackManager, ErrorCategory
        
        manager = ModelFallbackManager()
        
        assert manager.categorize_error("Rate limit", 429) == ErrorCategory.RATE_LIMIT
        assert manager.categorize_error("No balance", 402) == ErrorCategory.INSUFFICIENT_BALANCE
        assert manager.categorize_error("Service down", 503) == ErrorCategory.SERVICE_ERROR


class TestNotifications:
    """Tests para el sistema de notificaciones."""
    
    def test_notification_manager_initialization(self):
        """Verificar inicialización del notification manager."""
        from notifications import NotificationManager
        
        manager = NotificationManager()
        
        assert manager.rules is not None
        assert len(manager.rules) > 0
    
    def test_always_policy(self):
        """Verificar política 'always'."""
        from notifications import NotificationManager, NotificationCategory
        
        manager = NotificationManager()
        
        should, reason = manager.should_notify(NotificationCategory.PROJECT_DELIVERED.value)
        
        assert should is True
        assert reason is None
    
    def test_never_policy(self):
        """Verificar política 'never'."""
        from notifications import NotificationManager, NotificationCategory
        
        manager = NotificationManager()
        
        should, reason = manager.should_notify(NotificationCategory.MODEL_FALLBACK.value)
        
        assert should is False
        assert "fallback" in reason.lower()
    
    def test_throttle_policy(self):
        """Verificar política 'throttled'."""
        from notifications import NotificationManager, NotificationCategory
        import time
        
        manager = NotificationManager()
        
        # Primera notificación debe pasar
        should, _ = manager.should_notify(NotificationCategory.TASK_COMPLETED.value)
        assert should is True
        
        # Registrar envío
        manager.record_notification(NotificationCategory.TASK_COMPLETED.value)
        
        # Segunda inmediata debe ser bloqueada
        should, reason = manager.should_notify(NotificationCategory.TASK_COMPLETED.value)
        assert should is False
        assert "throttl" in reason.lower()
    
    def test_format_message(self):
        """Verificar formateo de mensajes."""
        from notifications import NotificationManager, NotificationCategory
        
        manager = NotificationManager()
        
        msg = manager.format_message(
            NotificationCategory.PROJECT_DELIVERED.value,
            name="Mi App",
            summary="Una app de prueba"
        )
        
        assert "Mi App" in msg
        assert "app de prueba" in msg


class TestSharedState:
    """Tests para gestión de estado compartido."""
    
    def test_default_memory_structure(self):
        """Verificar estructura de memoria por defecto."""
        from shared_state import DEFAULT_MEMORY
        
        assert "schema_version" in DEFAULT_MEMORY
        assert "project" in DEFAULT_MEMORY
        assert "tasks" in DEFAULT_MEMORY
        assert "agents" in DEFAULT_MEMORY
    
    def test_utc_now_format(self):
        """Verificar formato de timestamp."""
        from shared_state import utc_now
        
        ts = utc_now()
        
        assert isinstance(ts, str)
        assert "T" in ts  # ISO format
    
    def test_project_state_functions_exist(self):
        """Verificar que existen funciones de estado."""
        from shared_state import (
            archive_current_project,
            start_fresh_project,
            clean_blocked_tasks,
            get_active_project,
            is_project_active,
        )
        
        # Solo verificar que existen
        assert callable(archive_current_project)
        assert callable(start_fresh_project)
        assert callable(clean_blocked_tasks)
        assert callable(get_active_project)
        assert callable(is_project_active)
    
    def test_clean_blocked_tasks(self):
        """Verificar limpieza de tareas bloqueadas."""
        from shared_state import clean_blocked_tasks, DEFAULT_MEMORY
        from copy import deepcopy
        
        mem = deepcopy(DEFAULT_MEMORY)
        
        # Añadir tarea en progreso
        mem["tasks"] = [
            {"id": "T-001", "status": "in_progress"},
            {"id": "T-002", "status": "pending"},
        ]
        
        cleaned = clean_blocked_tasks(mem)
        
        assert cleaned == 1
        assert mem["tasks"][0]["status"] == "cancelled"


@pytest.mark.skip(reason="Import conflict con estructura de directorios")
class TestSkillsPlugins:
    """Tests para el sistema de skills/plugins."""
    
    def test_skill_meta_dataclass(self):
        """Verificar SkillMeta dataclass."""
        # Importar del archivo correcto
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "skills"))
        from plugins import SkillMeta, SkillPriority
        
        skill = SkillMeta(
            name="test-skill",
            family="backend",
            stacks=["python"],
        )
        
        assert skill.name == "test-skill"
        assert skill.family == "backend"
        assert skill.priority == SkillPriority.NORMAL.value
    
    def test_register_and_get_skill(self):
        """Verificar registro y obtención de skills."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "skills"))
        from plugins import (
            register_skill,
            get_skill,
            SkillMeta,
        )
        
        skill = SkillMeta(
            name="test-register-unique",
            family="test",
        )
        
        register_skill(skill)
        
        retrieved = get_skill("test-register-unique")
        assert retrieved is not None
        assert retrieved.name == "test-register-unique"
    
    def test_get_skills_for_stack(self):
        """Verificar obtención de skills por stack."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "skills"))
        from plugins import get_skills_for_stack
        
        # Laravel skill debe aparecer para stack "laravel"
        skills = get_skills_for_stack("laravel")
        
        # Verificar que hay al menos un skill de laravel
        assert any(s.name == "laravel" for s in skills)


class TestLaravelPlugin:
    """Tests para el plugin de Laravel."""
    
    def test_detect_laravel_project(self):
        """Verificar detección de proyectos Laravel."""
        from skills.plugins.laravel import detect
        
        # Proyecto con artisan
        project = {"files": ["artisan", "composer.json"]}
        assert detect(project) is True
        
        # Proyecto sin Laravel
        project = {"files": ["index.html", "app.js"]}
        assert detect(project) is False
    
    def test_enhance_prompt_adds_instructions(self):
        """Verificar que enhance_prompt añade instrucciones."""
        from skills.plugins.laravel import enhance_prompt
        
        task = {"title": "Create User model", "description": ""}
        context = "Create a model for users"
        
        enhanced = enhance_prompt(task, context)
        
        assert "Laravel Best Practices" in enhanced
        assert "Eloquent" in enhanced or "Model" in enhanced
    
    def test_validate_output_check_fillable(self):
        """Verificar validación de $fillable."""
        from skills.plugins.laravel import validate_output
        
        # Model sin $fillable - debe fallar
        files = [
            {"path": "app/Models/User.php", "content": "class User extends Model {}"}
        ]
        
        valid, issues = validate_output(files)
        
        assert valid is False
        assert any("fillable" in i.lower() for i in issues)
    
    def test_validate_migration_has_up_down(self):
        """Verificar validación de migrations."""
        from skills.plugins.laravel import validate_output
        
        # Migration sin down()
        files = [
            {"path": "database/migrations/create_users.php", "content": "def up(): pass"}
        ]
        
        valid, issues = validate_output(files)
        
        assert valid is False
        assert any("down" in i.lower() for i in issues)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_memory_file():
    """Crear archivo de memoria temporal para tests."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"schema_version": "3.0", "project": {}, "tasks": []}, f)
        yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def mock_telegram():
    """Mock para envío de Telegram."""
    with patch("coordination.send_telegram_message") as mock:
        mock.return_value = {"sent": True}
        yield mock


# ── Test runner config ───────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
