# Análisis del Sistema Multi-Agentes OpenClaw
## Documento Final - Plan de Mejoras

**Fecha:** 2026-03-27  
**Versión:** 1.0  
**Autor:** Claw (OpenClaw Assistant)

---

## 1. Resumen Ejecutivo

El sistema multi-agentes de OpenClaw es una arquitectura de orquestación de proyectos de software que utiliza tres agentes especializados (ARCH, BYTE, PIXEL) para automatizar el ciclo completo de desarrollo. El sistema demuestra una arquitectura híbrida bien pensada pero presenta varios puntos de mejora identificados durante las pruebas.

### Estado Actual del Sistema

| Componente | Líneas de Código | Estado | Cobertura |
|------------|------------------|--------|-----------|
| orchestrator.py | ~2,500 | Funcional | Media |
| coordination.py | ~2,000 | Funcional | Media |
| dashboard_api.py | ~2,200 | Funcional | Alta |
| openclaw_sdk.py | ~1,400 | Funcional | Alta |
| shared_state.py | ~250 | Funcional | Alta |

---

## 2. Análisis de Arquitectura

### 2.1 Diagrama de Arquitectura Actual

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DASHBOARD API                               │
│         FastAPI + WebSocket + SSE + REST Endpoints                  │
│                    Puerto: 8001                                      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR                                 │
│    asyncio pipeline · lockfile · recovery · gateway check           │
│                                                                     │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐             │
│  │    ARCH     │───▶│    BYTE     │    │   PIXEL     │             │
│  │ Coordinator │    │ Programmer  │    │  Designer   │             │
│  │   (GLM-5)   │    │  (Kimi/     │    │ (DeepSeek/  │             │
│  │             │    │  DeepSeek)  │    │  Mistral)   │             │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘             │
│         │                  │                  │                     │
│         └──────────────────┼──────────────────┘                     │
│                            │                                        │
│                            ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    MEMORY.json                               │   │
│  │         (Estado Compartido + File Locking)                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      OPENCLAW SDK                                   │
│           Wrapper async del CLI + Session Management                │
│                                                                     │
│  - Model Discovery (caché de modelos disponibles)                  │
│  - Progress Callback (streaming de progreso)                       │
│  - Failure Classification (infra/format/content/blocked)           │
│  - Session Utilities (make_session_id, truncate_prompt)            │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    OPENCLAW GATEWAY                                 │
│              WebSocket Server (puerto 18789)                        │
│                                                                     │
│  - Agent Execution                                                  │
│  - Tool Calls                                                       │
│  - Session Persistence                                              │
│  - Model Routing                                                    │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Flujo de Datos

```
Usuario (Telegram/API)
        │
        ▼
┌───────────────────┐
│ Dashboard API     │ ◄── POST /api/project/start
│ (FastAPI)         │
└─────────┬─────────┘
          │ spawn process
          ▼
┌───────────────────┐
│ Orchestrator      │ ◄── Carga MEMORY.json
│ (asyncio)         │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ ARCH (Planner)    │ ◄── Genera plan JSON
│ nvidia/z-ai/glm5  │
└─────────┬─────────┘
          │ asigna tareas
          ▼
┌───────────────────┐     ┌───────────────────┐
│ BYTE (Programmer) │     │ PIXEL (Designer)  │
│ Kimi/DeepSeek     │     │ Mistral           │
└─────────┬─────────┘     └─────────┬─────────┘
          │                         │
          └────────────┬────────────┘
                       │
                       ▼
              ┌───────────────────┐
              │ Output Files      │
              │ (HTML/CSS/JS/Py)  │
              └───────────────────┘
```

### 2.3 Componentes Principales

#### Orchestrator (orchestrator.py)
**Responsabilidades:**
- Ejecución del pipeline de fases (planning → execution → review)
- Gestión de timeouts y reintentos
- Limpieza de sesiones oversized
- Coordinación entre agentes
- Notificaciones Telegram

**Puntos Críticos:**
- Línea 1552: `_run_agent_task()` - función central de ejecución
- Línea 1919: llamada a `_run_agent_task` (arreglado)
- Línea 103: `clean_oversized_sessions()` - prevención de overflow

#### Coordination (coordination.py)
**Responsabilidades:**
- Bootstrap de repositorios
- Validación de estructura de proyecto
- Construcción de perfiles de habilidades
- Gestión de archivos de salida
- Comunicación con Telegram

**Puntos Críticos:**
- `ProjectKind` - tipos de proyecto soportados
- `validate_project_structure()` - validación de entregables
- `build_task_skill_profile()` - routing de skills

#### Dashboard API (dashboard_api.py)
**Responsabilidades:**
- REST API para control del sistema
- WebSocket para actualizaciones en tiempo real
- SSE para streaming de estado
- Proxy a Miniverse
- Gestión de modelos dinámicos

**Endpoints Principales:**
- `GET /api/state` - snapshot de MEMORY.json
- `POST /api/project/start` - lanzar proyecto
- `PUT /api/models` - cambiar modelos
- `WS /ws/state` - WebSocket de actualizaciones

---

## 3. GAPs (Carencias) Identificados

### GAP-1: Gestión de Estado de Proyectos Múltiples
**Descripción:** El sistema usa un único `MEMORY.json` global que mezcla proyectos activos con históricos.

**Impacto:**
- Tareas de proyectos anteriores se mezclan con nuevos proyectos
- Estado `in_progress` persiste entre ejecuciones
- "Recuperadas X tareas bloqueadas" en cada inicio

**Severidad:** Alta

### GAP-2: Sistema de Fallbacks de Modelos
**Descripción:** No hay rotación automática cuando un modelo falla por rate limit o saldo.

**Impacto:**
- Rate limit en GLM5 (429) bloquea ARCH
- Saldo insuficiente en DeepSeek (402) bloquea BYTE/PIXEL
- Requiere intervención manual para cambiar modelos

**Severidad:** Alta

### GAP-3: Validación de Argumentos en Runtime
**Descripción:** `_run_agent_task()` fue llamada con argumentos incorrectos sin validación previa.

**Impacto:**
- Error de SDK difícil de debuggear
- Fallos silenciosos hasta que se ejecuta

**Severidad:** Media (arreglado)

### GAP-4: Limpieza de Estado al Iniciar
**Descripción:** No existe mecanismo para forzar un estado limpio en nuevos proyectos.

**Impacto:**
- Tareas bloqueadas se arrastran entre proyectos
- Comportamiento impredecible en reinicios

**Severidad:** Media

### GAP-5: Observabilidad de Errores de API
**Descripción:** Errores como 429/402 se muestran en logs pero no en el dashboard.

**Impacto:**
- Usuario no ve que hay problemas de API
- Diagnóstico requiere revisar logs manuales

**Severidad:** Media

### GAP-6: MiniverseBridge Incompleto
**Descripción:** Faltaba método `check_inbox()` causando loop de errores.

**Impacto:**
- 2 errores por segundo en logs
- Degrada rendimiento del sistema

**Severidad:** Alta (arreglado)

### GAP-7: Documentación de API Insuficiente
**Descripción:** Los endpoints del dashboard no están documentados con OpenAPI/Swagger.

**Impacto:**
- Integración requiere leer código fuente
- No hay contrato formal de API

**Severidad:** Baja

---

## 4. Plan de Mejoras Detallado

### Fase 1: Estabilización (Prioridad Alta)

#### Tarea 1.1: Sistema de Estado Por Proyecto
**Objetivo:** Separar estado por proyecto activo.

**Implementación:**
```python
# Nuevo schema en shared_state.py
DEFAULT_MEMORY = {
    "schema_version": "3.0",
    "active_project_id": None,
    "projects": {
        # "<project_id>": { ... proyecto completo ... }
    },
    "archived_projects": [],  # últimos 10 proyectos
    "system": {
        "orchestrator": { ... },
        "agents": { ... }
    }
}
```

**Archivos a modificar:**
- `shared_state.py` (nuevo schema)
- `orchestrator.py` (carga/guardado de estado)
- `dashboard_api.py` (endpoints de estado)

**Estimación:** 4 horas

---

#### Tarea 1.2: Limpieza Automática de Tareas Bloqueadas
**Objetivo:** Limpiar tareas en `in_progress` al iniciar nuevo proyecto.

**Implementación:**
```python
def clean_blocked_tasks(mem: dict) -> int:
    """Move in_progress tasks to cancelled when starting fresh."""
    cleaned = 0
    for task in mem.get("tasks", []):
        if task.get("status") == "in_progress":
            task["status"] = "cancelled"
            task["cancelled_reason"] = "new_project_started"
            cleaned += 1
    return cleaned
```

**Archivos a modificar:**
- `orchestrator.py` (llamar al iniciar)

**Estimación:** 1 hora

---

#### Tarea 1.3: Sistema de Fallbacks Automáticos
**Objetivo:** Rotar modelos cuando hay errores de API.

**Implementación:**
```python
# Nuevo en models_config.json
{
    "fallback_chain": {
        "arch": ["nvidia/z-ai/glm5", "deepseek/deepseek-chat", "mistral/mistral-large-latest"],
        "byte": ["nvidia/moonshotai/kimi-k2.5", "deepseek/deepseek-chat", "mistral/mistral-large-latest"],
        "pixel": ["deepseek/deepseek-chat", "mistral/mistral-large-latest", "nvidia/z-ai/glm5"]
    },
    "error_codes_to_trigger_fallback": [429, 402, 503, 502]
}
```

```python
# Nuevo en orchestrator.py
async def execute_with_fallback(agent_id, prompt, primary_model):
    models = get_fallback_chain(agent_id)
    for model in models:
        try:
            return await execute_agent(agent_id, prompt, model)
        except (RateLimitError, InsufficientBalanceError):
            log_event(f"Fallback: {model} → next", agent_id)
            continue
    raise AllModelsExhaustedError(agent_id)
```

**Archivos a modificar:**
- `models_config.json` (fallback chains)
- `orchestrator.py` (lógica de fallback)
- `openclaw_sdk.py` (detección de errores)

**Estimación:** 3 horas

---

### Fase 2: Observabilidad (Prioridad Media)

#### Tarea 2.1: Dashboard de Estado de APIs
**Objetivo:** Mostrar estado de APIs en tiempo real.

**Implementación:**
```python
# Nuevo endpoint en dashboard_api.py
@app.get("/api/health/models")
async def get_models_health():
    return {
        "models": {
            "nvidia/z-ai/glm5": {"status": "rate_limited", "last_error": "429"},
            "deepseek/deepseek-chat": {"status": "insufficient_balance", "last_error": "402"},
            "mistral/mistral-large-latest": {"status": "ok"}
        },
        "recommendations": [
            "Consider switching BYTE to mistral/mistral-large-latest"
        ]
    }
```

**Estimación:** 2 horas

---

#### Tarea 2.2: Logs Estructurados con Niveles
**Objetivo:** Categorizar logs por severidad.

**Implementación:**
```python
# Añadir a JSONL logs
{
    "ts": "2026-03-27T12:00:00",
    "agent": "byte",
    "level": "error",  # debug, info, warning, error, critical
    "category": "api_error",  # nueva categoría
    "msg": "Rate limit exceeded",
    "details": {
        "model": "nvidia/z-ai/glm5",
        "error_code": 429,
        "retry_after": 60
    }
}
```

**Estimación:** 2 horas

---

#### Tarea 2.3: Notificaciones Inteligentes
**Objetivo:** Notificar solo errores relevantes por Telegram.

**Implementación:**
```python
# Solo notificar si:
# - Error crítico que para el proyecto
# - Tarea completada
# - Proyecto entregado
# NO notificar:
# - Rate limits con fallback exitoso
# - Errores de retry
# - Progress updates

TELEGRAM_NOTIFICATION_RULES = {
    "always": ["project_delivered", "critical_error", "blocked_waiting_user"],
    "never": ["rate_limit_fallback", "retry_attempt", "progress_update"],
    "throttled": ["task_completed", "phase_completed"]  # max 1 por minuto
}
```

**Estimación:** 2 horas

---

### Fase 3: Arquitectura (Prioridad Media-Baja)

#### Tarea 3.1: Plugin de Skills Mejorado
**Objetivo:** Sistema de skills extensible sin modificar código core.

**Implementación:**
```python
# Nuevo directorio skills/plugins/
# Cada skill es un módulo independiente:

# skills/plugins/laravel.py
SKILL_META = {
    "name": "laravel",
    "family": "backend",
    "stacks": ["laravel", "php"],
    "tools": ["artisan", "composer"],
    "file_patterns": ["*.blade.php", "*.php"],
    "priority": 10
}

def detect(project_structure):
    return "artisan" in project_structure.get("files", [])

def enhance_prompt(task, context):
    return f"{context}\n\nLaravel-specific instructions..."

def validate_output(files):
    # Validación específica de Laravel
    pass
```

**Estimación:** 4 horas

---

#### Tarea 3.2: Circuit Breaker para APIs
**Objetivo:** No intentar APIs que han fallado recientemente.

**Implementación:**
```python
class ModelCircuitBreaker:
    def __init__(self, cooldown_seconds=300):
        self.failures = {}  # model -> [timestamps]
        self.cooldown = cooldown_seconds
    
    def is_available(self, model):
        if model not in self.failures:
            return True
        # Eliminar fallos antiguos
        cutoff = time.time() - self.cooldown
        self.failures[model] = [t for t in self.failures[model] if t > cutoff]
        return len(self.failures[model]) < 3
    
    def record_failure(self, model):
        self.failures.setdefault(model, []).append(time.time())
```

**Estimación:** 2 horas

---

#### Tarea 3.3: Cache de Modelos Disponibles
**Objetivo:** No descubrir modelos en cada ejecución.

**Implementación:**
```python
# Ya existe en openclaw_sdk.py pero mejorar:
_MODEL_DISCOVERY_CACHE = {
    "signature": None,
    "expires_at": 0.0,
    "models": [],
    "status": {}  # Nuevo: estado por modelo
}

def get_available_models_with_status():
    """Return models with their last known status."""
    models = get_available_models()
    for m in models:
        m["last_status"] = _MODEL_DISCOVERY_CACHE["status"].get(m["qualified"], "unknown")
    return models
```

**Estimación:** 1 hora

---

### Fase 4: Testing y Documentación (Prioridad Baja)

#### Tarea 4.1: Tests de Integración
**Objetivo:** Validar flujo completo end-to-end.

**Implementación:**
```python
# tests/test_integration.py
import pytest

@pytest.mark.asyncio
async def test_full_project_lifecycle():
    # 1. Iniciar proyecto
    # 2. Verificar plan generado
    # 3. Verificar tareas ejecutadas
    # 4. Verificar archivos creados
    # 5. Verificar proyecto entregado
    pass

@pytest.mark.asyncio
async def test_model_fallback():
    # 1. Forzar rate limit en modelo primario
    # 2. Verificar fallback a secundario
    # 3. Verificar tarea completada
    pass
```

**Estimación:** 6 horas

---

#### Tarea 4.2: Documentación OpenAPI
**Objetivo:** Generar spec Swagger automáticamente.

**Implementación:**
```python
# Añadir a dashboard_api.py
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="OpenClaw Multi-Agent API",
        version="1.0.0",
        description="API para orquestar agentes ARCH, BYTE y PIXEL",
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema
```

**Estimación:** 2 horas

---

## 5. Resumen del Plan de Tareas

| ID | Tarea | Fase | Prioridad | Estimación | Dependencias |
|----|-------|------|-----------|------------|--------------|
| 1.1 | Sistema de estado por proyecto | 1 | Alta | 4h | - |
| 1.2 | Limpieza de tareas bloqueadas | 1 | Alta | 1h | 1.1 |
| 1.3 | Sistema de fallbacks automáticos | 1 | Alta | 3h | - |
| 2.1 | Dashboard de estado de APIs | 2 | Media | 2h | 1.3 |
| 2.2 | Logs estructurados | 2 | Media | 2h | - |
| 2.3 | Notificaciones inteligentes | 2 | Media | 2h | 2.2 |
| 3.1 | Plugin de skills mejorado | 3 | Media | 4h | - |
| 3.2 | Circuit breaker para APIs | 3 | Media | 2h | 1.3 |
| 3.3 | Cache de modelos con status | 3 | Baja | 1h | 2.1 |
| 4.1 | Tests de integración | 4 | Baja | 6h | 1.1, 1.3 |
| 4.2 | Documentación OpenAPI | 4 | Baja | 2h | - |

**Total estimado:** 29 horas

---

## 6. Métricas de Éxito

### Métricas Técnicas
- Tasa de éxito de proyectos (target: >90%)
- Tiempo promedio de entrega (target: <30 min)
- Tasa de errores recuperables (target: >95%)
- Uptime del sistema (target: >99%)

### Métricas de Usuario
- Satisfacción del usuario (NPS)
- Tiempo hasta primera entrega válida
- Número de intervenciones manuales requeridas

---

## 7. Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| APIs de modelos inestables | Alta | Alto | Fallbacks + Circuit Breaker |
| Estado corrupto | Media | Alto | Backup automático + Validación |
| Timeout en proyectos grandes | Media | Medio | Timeouts configurables + Checkpoints |
| Rate limits prolongados | Alta | Medio | Distribución de carga + Cola de espera |

---

## 8. Conclusiones

El sistema multi-agentes de OpenClaw tiene una arquitectura sólida con una separación clara de responsabilidades. Los principales puntos de mejora identificados son:

1. **Gestión de estado** - Necesita separación por proyecto
2. **Resiliencia a fallos de API** - Fallbacks automáticos
3. **Observabilidad** - Mejor visibilidad de errores

Con las mejoras propuestas, el sistema pasará de ser funcional a ser robusto y listo para producción.

---

**Documento generado por:** Claw (OpenClaw Assistant)  
**Fecha:** 2026-03-27  
**Ubicación:** `/var/www/openclaw-multi-agents/ANALYSIS_AND_IMPROVEMENTS.md`
