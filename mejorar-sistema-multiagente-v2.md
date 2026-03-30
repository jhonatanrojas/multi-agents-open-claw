# Plan de Mejora — Sistema Multi-Agente v2
## ARCH / BYTE / PIXEL + OpenClaw + Runtime + Dashboard

> **Stack real:** Python / FastAPI · OpenClaw · MEMORY.json · Laravel + React  
> **Agentes:** ARCH (coordinador) · BYTE (programador) · PIXEL (diseñador) · JUDGE (revisor)  
> **Estado actual:** proto multi-agent — base fuerte, falta formalizar estado + supervisor + contratos

---

## Diagnóstico de partida

El sistema ya tiene separación de roles y un grafo de ejecución definido.
Los tres problemas raíz que bloquean el salto a plataforma real son:

1. **Estado implícito** — MEMORY.json es la única fuente de verdad pero no tiene esquema formal ni validación
2. **Orquestador sobrecargado** — orchestrator.py decide, ejecuta y controla al mismo tiempo
3. **Sin contratos entre capas** — UI infiere estado, agentes asumen interfaces, no hay verificación

El plan corrige estos tres problemas en orden estricto: estabilizar → formalizar → escalar.

---

# FASE 0 — Estabilización crítica

**Objetivo:** producción estable antes de cualquier cambio arquitectónico.
No avanzar a Fase 1 hasta que todos los ítems de Fase 0 estén en verde.

---

## F0.1 — Fix autenticación SSE

**Problema:** el stream SSE no sobrevive reinicios de sesión ni proxies.

Opciones en orden de recomendación:

- Cookie de sesión firmada (recomendado — sin tokens en URL)
- Token de corta duración en query string (firmado con HMAC, TTL 60s)
- Reverse proxy (nginx) que inyecte el header Authorization

**Criterio de aceptación:** el stream SSE reconecta automáticamente
después de un reinicio de gateway sin intervención del usuario.

---

## F0.2 — Corregir bugs en dashboard_api.py

Archivos: `dashboard_api.py`

- Eliminar duplicación de `_stop_orchestrator`
- Corregir decoradores incorrectos (`@app.get` usado donde se necesita `@app.post`)
- Separar handlers GET/POST en funciones distintas
- Agregar manejo de excepciones con respuestas HTTP correctas (no 500 genérico)
- Documentar cada endpoint con docstring de una línea

**Criterio de aceptación:** ningún endpoint devuelve 500 en condiciones normales.
Todos tienen docstring.

---

## F0.3 — Fix model_fallback.py

- Definir `MODEL_STATUS_CACHE_PATH` como constante con ruta absoluta
- Validar que el directorio de caché existe antes de escribir
- Envolver toda escritura/lectura en try/except con logging explícito
- Agregar TTL al caché (no usar entradas de más de 5 minutos)

**Criterio de aceptación:** el proceso no lanza excepciones no manejadas
cuando el archivo de caché no existe o está corrupto.

---

## F0.4 — Restringir CORS

```python
allow_origins = [
    "https://tu-dominio.com",
    "http://localhost:3000",   # solo en desarrollo
]
```

Eliminar `allow_origins=["*"]` completamente del código de producción.
Usar variable de entorno `ALLOWED_ORIGINS` para configurar por ambiente.

---

## F0.5 — Modularizar backend

Dividir `dashboard_api.py` en módulos por dominio:

```
/api/
  __init__.py
  state.py       ← GET /state, GET /stream
  projects.py    ← /project/start, /pause, /resume, /delete
  models.py      ← /models, /models/agent, /models/test
  runtime.py     ← /runtime/orchestrators, /cleanup
  gateway.py     ← /gateway/events
  streaming.py   ← SSE y WebSocket handlers
  context.py     ← PATCH /context, GET /files/view
  agents.py      ← POST /agents/:id/steer
  tasks.py       ← POST /tasks/:id/pause
```

Cada módulo tiene su propio router de FastAPI.
`dashboard_api.py` queda como punto de entrada que solo registra routers.

---

## F0.6 — Tests mínimos

Backend (pytest):
- Test de cada endpoint: respuesta 200 con payload válido
- Test del lock de ejecución: segunda llamada retorna 409
- Test de SSE: el stream emite al menos un evento en 5 segundos

Frontend (Playwright):
- El dashboard carga sin errores de consola
- El indicador de conexión muestra "Conectado" en menos de 3 segundos
- El formulario de proyecto no permite submit con brief vacío

---

## F0.7 — Variables de entorno y configuración _(nuevo)_

**Problema no cubierto en el plan original:** configuración hardcodeada
en múltiples archivos.

Crear `/var/www/openclaw-multi-agents/.env.example` con todas las
variables necesarias:

```
OPENCLAW_GATEWAY_URL=ws://localhost:18789
OPENCLAW_GATEWAY_TOKEN=
MINIVERSE_URL=https://miniverse-public-production.up.railway.app
ALLOWED_ORIGINS=https://tu-dominio.com
MODEL_STATUS_CACHE_PATH=/var/cache/openclaw/model_status.json
DATABASE_URL=sqlite:///./runs.db
RUN_LOCK_BACKEND=file  # file | redis
REDIS_URL=redis://localhost:6379
LOG_LEVEL=INFO
```

Usar `python-dotenv` para cargarlo. Ninguna ruta ni URL debe estar
hardcodeada en el código fuente.

**Criterio de aceptación:** el sistema arranca correctamente con solo
copiar `.env.example` a `.env` y rellenar los valores reales.

---

## F0.8 — Health check endpoint _(nuevo)_

Crear `GET /health` que devuelva:

```json
{
  "status": "ok",
  "gateway": "connected | disconnected",
  "database": "ok | error",
  "lock_backend": "ok | error",
  "active_runs": 2,
  "version": "1.0.0"
}
```

Este endpoint es el que monitoreo externo (UptimeRobot, etc.) consulta.
El dashboard lo usa para mostrar el indicador de conexión global.

---

# FASE 1 — Hardening del sistema actual

**Objetivo:** estabilizar sin reescribir — evitar doble ejecución,
pérdida de estado, y desincronización UI/runtime.

---

## F1.1 — Formalizar RunContext

**Problema:** el flujo depende de variables implícitas dispersas en
memoria de proceso.

Implementar como dataclass Python (no TypeScript):

```python
from dataclasses import dataclass, field
from typing import Literal, Optional
from datetime import datetime

@dataclass
class RunContext:
    run_id: str
    project_id: str
    status: Literal[
        'planning', 'executing', 'blocked',
        'paused', 'completed', 'failed'
    ]
    current_phase: Optional[str]
    current_agent: Optional[Literal['arch', 'byte', 'pixel', 'judge']]
    plan_version: int
    tasks: list
    artifacts: list
    blockers: list
    milestones: list
    started_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> 'RunContext': ...
    def checkpoint(self) -> None:
        """Write current state to persistence layer."""
```

`orchestrator.py` siempre recibe y devuelve `RunContext`.
El `RunContext.checkpoint()` persiste después de cada cambio de estado.

**Criterio de aceptación:** puedes serializar y deserializar un `RunContext`
completo y reanudar la ejecución desde el punto exacto donde quedó.

---

## F1.2 — Capa de persistencia

Reemplazar MEMORY.json como fuente de verdad central.
MEMORY.json sigue existiendo como snapshot de debug, no como estado operacional.

```
/src/infrastructure/persistence/
  database.py        ← SQLite con SQLAlchemy (dev) / Postgres (prod)
  run_repository.py  ← CRUD de RunContext
  task_repository.py ← CRUD de Task
  event_repository.py← append-only de eventos (preparar F3.2)
```

Schema mínimo:

```sql
CREATE TABLE runs (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  status TEXT NOT NULL,
  context_json TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tasks (
  id TEXT PRIMARY KEY,
  run_id TEXT REFERENCES runs(id),
  agent TEXT NOT NULL,
  status TEXT NOT NULL,
  input_json TEXT,
  output_json TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Criterio de aceptación:** reiniciar el proceso completo y recuperar
el estado de todos los runs activos desde la base de datos.

---

## F1.3 — Lock de ejecución anti doble run

```python
import fcntl
import os

class RunLock:
    def __init__(self, project_id: str):
        self.path = f"/tmp/run-lock-{project_id}.lock"
        self._file = None

    def acquire(self) -> bool:
        try:
            self._file = open(self.path, 'w')
            fcntl.flock(self._file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def release(self):
        if self._file:
            fcntl.flock(self._file, fcntl.LOCK_UN)
            self._file.close()
            os.unlink(self.path)
```

Si Redis está disponible (`RUN_LOCK_BACKEND=redis`):

```python
await redis.set(f"run-lock:{project_id}", run_id, nx=True, ex=300)
```

**Criterio de aceptación:** dos llamadas simultáneas a `/project/start`
con el mismo `project_id` — la segunda retorna HTTP 409.

---

## F1.4 — Endpoint de sincronización UI

```
GET /projects/:id/runtime-state
```

Respuesta:

```json
{
  "run_id": "...",
  "status": "executing",
  "current_phase": "phase-2",
  "current_agent": "byte",
  "plan_version": 3,
  "tasks": [...],
  "agents": {...},
  "blockers": [],
  "logs": [...],
  "updated_at": "2026-03-30T10:00:00Z"
}
```

La UI consume este endpoint al cargar y el SSE stream para actualizaciones.
La UI nunca infiere estado — lo lee directamente.

---

## F1.5 — Normalizar estados del grafo

Definir estados explícitos como enum Python:

```python
from enum import Enum

class GraphState(str, Enum):
    DISCOVERY = "discovery"
    QUALIFICATION = "qualification"
    RECOMMENDATION = "recommendation"
    PRICE_DISCUSSION = "price_discussion"
    NEGOTIATION = "negotiation"
    PURCHASE_INTENT = "purchase_intent"
    CHECKOUT = "checkout"
    POST_SALE = "post_sale"
    ESCALATE = "escalate"
    BLOCKED = "blocked"
    COMPLETED = "completed"
```

Guardar el estado actual en `RunContext.current_phase`.
Ningún código usa strings literales para referirse a estados del grafo.

---

## F1.6 — Circuit breaker por agente _(nuevo)_

**Problema no cubierto:** si un agente falla repetidamente, el sistema
sigue intentando asignarle tareas indefinidamente.

```python
class AgentCircuitBreaker:
    def __init__(self, agent_id: str, threshold: int = 3, cooldown: int = 300):
        self.agent_id = agent_id
        self.failures = 0
        self.threshold = threshold
        self.cooldown_until = None

    def record_failure(self):
        self.failures += 1
        if self.failures >= self.threshold:
            self.cooldown_until = datetime.utcnow() + timedelta(seconds=self.cooldown)

    def is_available(self) -> bool:
        if self.cooldown_until and datetime.utcnow() < self.cooldown_until:
            return False
        return True

    def record_success(self):
        self.failures = 0
        self.cooldown_until = None
```

El supervisor consulta `is_available()` antes de asignar cualquier tarea.
Estado del circuit breaker se incluye en `/health` y en el dashboard.

---

## F1.7 — Retry con backoff exponencial _(nuevo)_

**Problema:** las tareas que fallan se reintentan inmediatamente,
lo que agota tokens y tiempo sin dar margen de recuperación.

```python
def retry_delay(attempt: int, base: float = 2.0, max_delay: float = 60.0) -> float:
    return min(base ** attempt, max_delay)
```

Reglas de retry por tipo de fallo:
- Error de modelo (timeout, rate limit) → retry con backoff, máximo 3 intentos
- Error de herramienta (archivo no encontrado) → no retry, marcar como bloqueada
- Error de formato (JSON inválido) → retry con prompt diferente, máximo 2 intentos
- Error desconocido → retry 1 vez, luego escalar a supervisor

---

# FASE 2 — Supervisor + Task System

**Objetivo:** separar decisión, ejecución y flujo en capas independientes.

---

## F2.1 — SupervisorService

```python
# /src/application/supervisor.py

class SupervisorService:
    def __init__(self, run_repo, task_repo, event_bus, circuit_breakers):
        ...

    def decide_next_step(self, run: RunContext) -> Optional[TaskIntent]:
        """
        Reads run state and returns the next task to create.
        Returns None if run is complete or blocked.
        """

    def assign_task(self, intent: TaskIntent, run: RunContext) -> Task:
        """
        Creates a Task from an intent and assigns it to the best
        available agent based on circuit breaker state.
        """

    def review_result(self, task: Task, run: RunContext) -> ReviewVerdict:
        """
        Evaluates task output against acceptance criteria.
        Returns APPROVED, REJECTED (with reason), or NEEDS_INFO.
        """

    def handle_blocker(self, task: Task, run: RunContext) -> BlockerResolution:
        """
        Decides whether to retry, reassign, decompose, or escalate.
        """

    def run_heartbeat_cycle(self, run: RunContext):
        """
        Called every 60 seconds. Detects stalls and intervenes.
        """
```

El supervisor es el único componente que modifica el estado del run.
Los agentes solo reciben tareas y devuelven resultados.

---

## F2.2 — Grafo como generador de intenciones

El grafo deja de ejecutar lógica directamente.
Devuelve una intención que el supervisor convierte en tarea:

```python
@dataclass
class TaskIntent:
    next_stage: GraphState
    required_agent: Literal['arch', 'byte', 'pixel']
    task_type: Literal['analysis', 'coding', 'design', 'review']
    priority: Literal['high', 'medium', 'low']
    depends_on: list[str]      # IDs de tareas previas
    acceptance_criteria: list[str]
    context_files: list[str]   # archivos que el agente debe leer
    parallel_safe: bool
```

---

## F2.3 — Task entity completa

```python
@dataclass
class Task:
    id: str
    run_id: str
    project_id: str
    phase: str
    task_type: Literal['analysis', 'coding', 'design', 'review']
    assigned_agent: Literal['arch', 'byte', 'pixel', 'judge']
    status: Literal[
        'pending', 'in_progress', 'needs_revision',
        'done', 'error', 'paused', 'cancelled'
    ]
    priority: Literal['high', 'medium', 'low']
    depends_on: list[str]
    acceptance_criteria: list[str]
    context_files: list[str]
    input: dict
    output: Optional[dict]
    judge_verdict: Optional[str]      # APPROVED | REJECTED: reason
    failure_count: int
    failure_kind: Optional[str]
    parallel_safe: bool
    parallel_safe_reason: str
    scope_change_reason: Optional[str]
    preview_url: Optional[str]
    preview_status: Optional[str]
    files_produced: list[str]
    last_updated: datetime
    created_at: datetime
```

---

## F2.4 — Agentes como workers puros

Cada agente implementa una única interfaz:

```python
class AgentWorker(ABC):
    @abstractmethod
    def execute(self, task: Task, context: RunContext) -> TaskResult:
        """
        Receives a task with full context.
        Returns a TaskResult with files, output, and status.
        Never makes decisions about what to do next.
        """

@dataclass
class TaskResult:
    task_id: str
    status: Literal['done', 'error', 'needs_clarification']
    output: dict
    files_produced: list[str]
    notes: str
    question: Optional[str]   # si status == 'needs_clarification'
    error_kind: Optional[str] # si status == 'error'
```

---

## F2.5 — Flujo completo con JUDGE integrado

```
User input / Telegram
        ↓
SupervisorService.decide_next_step()
        ↓
GraphRunner (devuelve TaskIntent)
        ↓
SupervisorService.assign_task()
        ↓
AgentWorker.execute() — ARCH / BYTE / PIXEL
        ↓
TaskResult
        ↓
SupervisorService.review_result() — spawna JUDGE
        ↓
APPROVED → marcar done, siguiente tarea
REJECTED → needs_revision, notificar agente, reintentar
        ↓
SupervisorService.decide_next_step() (siguiente ciclo)
```

---

## F2.6 — JUDGE como agente formal _(nuevo)_

JUDGE ya existe en el plan de arquitectura v2 pero no está integrado
en el flujo del supervisor.

```python
class JudgeWorker(AgentWorker):
    """
    Read-only evaluator. Never modifies files.
    Evaluates against 4 dimensions:
    1. Acceptance criteria compliance
    2. BYTE/PIXEL interface consistency
    3. CONTRACTS.md compliance
    4. Obvious defects (missing files, broken imports)
    """

    def execute(self, task: Task, context: RunContext) -> TaskResult:
        # Returns status='done' with output containing:
        # { verdict: 'APPROVED' | 'REJECTED', reason: str, dimension: str }
```

El supervisor spawna JUDGE automáticamente antes de marcar
cualquier tarea como `done`. No requiere intervención manual.

---

## F2.7 — Memoria diferenciada por agente _(nuevo)_

Cada agente tiene su propio archivo de memoria persistente que
acumula conocimiento entre proyectos:

```
/workspaces/coordinator/MEMORY.md   ← decisiones de ARCH
/workspaces/programmer/MEMORY.md    ← patrones de BYTE
/workspaces/designer/MEMORY.md      ← sistema de diseño de PIXEL
/workspaces/reviewer/MEMORY.md      ← criterios de JUDGE
```

El supervisor inyecta el MEMORY.md del agente en cada tarea
como contexto adicional (no como parte del prompt principal).
Al completar una tarea exitosamente, el agente agrega una nota
breve (máximo 3 oraciones) a su propio MEMORY.md.

---

# FASE 3 — Event-driven + Observabilidad + Plataforma

**Objetivo:** convertir el sistema en plataforma auditable y escalable.

---

## F3.1 — Event Bus

Eventos del dominio:

```python
class EventType(str, Enum):
    RUN_STARTED = "run.started"
    RUN_PAUSED = "run.paused"
    RUN_RESUMED = "run.resumed"
    RUN_BLOCKED = "run.blocked"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_NEEDS_REVISION = "task.needs_revision"
    AGENT_ASSIGNED = "agent.assigned"
    AGENT_EXECUTED = "agent.executed"
    AGENT_STALLED = "agent.stalled"
    CIRCUIT_OPENED = "circuit.opened"
    CIRCUIT_CLOSED = "circuit.closed"
    JUDGE_APPROVED = "judge.approved"
    JUDGE_REJECTED = "judge.rejected"
    SUPERVISOR_INTERVENED = "supervisor.intervened"
    PLAN_VERSION_INCREMENTED = "plan.versioned"
    PREVIEW_CREATED = "preview.created"
    PREVIEW_STOPPED = "preview.stopped"
```

Implementación inicial: in-process con lista de subscribers.
Upgrade posterior: Redis Pub/Sub o similar.

---

## F3.2 — Event Log persistente

```sql
CREATE TABLE events (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  run_id TEXT,
  task_id TEXT,
  agent TEXT,
  payload_json TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_events_run ON events(run_id, created_at);
CREATE INDEX idx_events_type ON events(type, created_at);
```

El event log es append-only. Ningún evento se modifica ni elimina.
TTL de 90 días para runs completados.

---

## F3.3 — Timeline UI

El dashboard muestra una línea de tiempo por run:

```
[10:01:00] ▶ Run iniciado — project: Todo App
[10:01:05] 📋 ARCH — Plan creado (8 tareas, 3 fases)
[10:01:08] 💻 BYTE — T-001: FastAPI scaffold → iniciada
[10:01:09] 🎨 PIXEL — T-002: Design tokens → iniciada
[10:01:41] ✅ BYTE — T-001 completada (4 archivos)
[10:01:52] ✅ PIXEL — T-002 completada
[10:01:53] ⚖️ JUDGE — T-001 APPROVED
[10:01:54] ⚖️ JUDGE — T-002 APPROVED
[10:02:00] ⚠️ Supervisor — T-004 estancada (190s) → steer enviado
```

Cada evento es expandible para ver el payload completo.
Los eventos de error se muestran en rojo con la razón específica.

---

## F3.4 — Replay de runs

```python
async def replay_run(run_id: str, speed: float = 1.0):
    """
    Re-emits all events of a completed run in order,
    at the original timing scaled by speed factor.
    Useful for debugging and post-mortems.
    """
    events = await event_repo.get_by_run(run_id, ordered=True)
    for i, event in enumerate(events):
        if i > 0:
            delay = (event.created_at - events[i-1].created_at).seconds
            await asyncio.sleep(delay / speed)
        await event_bus.emit(event)
```

Endpoint: `POST /runs/:id/replay?speed=2.0`
El dashboard entra en modo replay y reproduce la timeline.

---

## F3.5 — Observabilidad y métricas

Métricas por run:
- Tiempo total de ejecución
- Tiempo por agente y por tarea
- Número de intervenciones del supervisor
- Número de rechazos de JUDGE y razones
- Número de retries por tarea
- Tokens consumidos por agente (si el modelo lo expone)
- Tasa de éxito por tipo de tarea

Endpoint: `GET /runs/:id/metrics`

Dashboard debe mostrar:
- Histograma de duración por tipo de tarea
- Tasa de error por agente en los últimos 10 runs
- Circuit breaker status en tiempo real

---

## F3.6 — Alertas y notificaciones _(nuevo)_

Condiciones que disparan alerta al operador:

```python
ALERT_RULES = [
    # Tarea estancada más de 10 minutos
    AlertRule("task.stalled", threshold_seconds=600),
    # Mismo agente falla 3 veces consecutivas
    AlertRule("agent.repeated_failure", threshold=3),
    # Run sin actividad más de 30 minutos
    AlertRule("run.inactive", threshold_seconds=1800),
    # Circuit breaker abierto
    AlertRule("circuit.opened", threshold=1),
    # Menos del 10% de tareas completadas en 1 hora
    AlertRule("run.slow_progress", threshold_pct=10, window_seconds=3600),
]
```

Canales de notificación:
- Miniverse (heartbeat con estado `error`)
- OpenClaw Gateway (mensaje directo al agente principal)
- Webhook configurable (para Slack, PagerDuty, etc.)

---

## F3.7 — Preview management formal _(nuevo)_

Integrar el flujo de Cloudflare Tunnel como componente de primera clase:

```python
class PreviewManager:
    def start_preview(self, task_id: str, port: int) -> str:
        """Starts cloudflared tunnel, returns public URL."""

    def stop_preview(self, task_id: str) -> None:
        """Kills the tunnel process."""

    def get_preview_url(self, task_id: str) -> Optional[str]:
        """Returns active URL or None."""

    def cleanup_all(self) -> None:
        """Kills all tunnels on process exit."""
```

El supervisor llama a `start_preview` automáticamente cuando PIXEL
o BYTE producen un artefacto de frontend.
La URL se almacena en `Task.preview_url` y se incluye en el announce.
El supervisor llama a `stop_preview` después de que JUDGE aprueba la tarea.

---

# FASE 4 — Resiliencia y operaciones _(nueva)_

**Objetivo:** el sistema sobrevive fallos de infraestructura
sin pérdida de runs activos.

---

## F4.1 — Graceful shutdown

Cuando el proceso recibe SIGTERM:
1. Marcar todos los runs activos como `paused`
2. Escribir checkpoint de todos los RunContext a base de datos
3. Matar todos los tunnels de Cloudflare activos
4. Cerrar conexiones al gateway de OpenClaw limpiamente
5. Responder al SIGTERM después de máximo 30 segundos

---

## F4.2 — Startup recovery

Al iniciar el proceso:
1. Leer todos los runs con status `executing` o `paused`
2. Para cada uno: verificar si el orquestador externo sigue activo
3. Si activo: reconectar y continuar monitoreando
4. Si inactivo: marcar como `paused` y notificar al operador
5. Nunca auto-reanudar sin confirmación explícita del operador

---

## F4.3 — Database migrations

Usar Alembic para gestionar el schema de la base de datos:

```
/migrations/
  env.py
  versions/
    0001_initial_schema.py
    0002_add_events_table.py
    0003_add_preview_fields.py
```

Antes de cualquier deploy: `alembic upgrade head`
El startup del proceso verifica que las migraciones estén aplicadas.

---

## F4.4 — Rate limiting por agente _(nuevo)_

Evitar que un agente consuma todos los tokens disponibles:

```python
AGENT_RATE_LIMITS = {
    'arch': RateLimit(requests_per_minute=10, tokens_per_hour=100_000),
    'byte': RateLimit(requests_per_minute=15, tokens_per_hour=150_000),
    'pixel': RateLimit(requests_per_minute=15, tokens_per_hour=150_000),
    'judge': RateLimit(requests_per_minute=20, tokens_per_hour=50_000),
}
```

Si un agente alcanza su límite: sus tareas pasan a `paused` hasta
que el ventana de tiempo se resetea. El supervisor asigna las tareas
pendientes a otro agente si es posible, o espera.

---

# Roadmap de implementación

## Semanas 1–2 — Fase 0

Estabilizar producción.
Todas las tareas F0.x deben completarse antes de continuar.
Criterio de salida: cero errores 500 en producción, tests pasando.

## Semanas 3–4 — Fase 1

RunContext, persistencia, locks, circuit breakers, retry.
Criterio de salida: reinicio del proceso no pierde ningún run activo.

## Semanas 5–6 — Fase 2

Supervisor, Task system, JUDGE formal, memoria por agente.
Criterio de salida: un run completo ejecuta sin intervención manual
y JUDGE valida cada tarea automáticamente.

## Semanas 7–8 — Fase 3

Event bus, observabilidad, replay, alertas, preview management.
Criterio de salida: puedes reproducir cualquier run pasado en el dashboard
y recibir alertas antes de que un run falle completamente.

## Semanas 9–10 — Fase 4

Resiliencia, graceful shutdown, migrations, rate limiting.
Criterio de salida: deploy sin downtime, proceso sobrevive reinicios
sin pérdida de estado.

---

# Arquitectura final (objetivo)

```
Operador / Telegram
        ↓
OpenClaw Gateway (WebSocket)
        ↓
SupervisorService
   ├── GraphRunner (TaskIntent)
   ├── CircuitBreaker × 4 agentes
   ├── PreviewManager
   └── EventBus
        ↓
AgentWorkers
   ├── ARCHWorker    (claude-opus)
   ├── BYTEWorker    (claude-sonnet)
   ├── PIXELWorker   (claude-sonnet)
   └── JUDGEWorker   (claude-haiku)
        ↓
Persistence Layer
   ├── RunRepository
   ├── TaskRepository
   └── EventRepository (append-only)
        ↓
Dashboard (React + SSE)
   ├── Three-panel layout
   ├── File tree en tiempo real
   ├── Activity stream por agente
   ├── Timeline de eventos
   └── Inline steer controls
```

---

# Los 5 cambios que más impacto tienen

En orden de ROI:

1. **RunContext formal** — resuelve el 80% de los bugs de estado de golpe
2. **Lock de ejecución** — elimina los runs duplicados que consumen tokens
3. **SupervisorService** — desacopla decisión de ejecución, todo lo demás es más fácil
4. **Event log** — hace debuggeable lo que hoy es opaco
5. **Circuit breaker** — evita que un agente roto bloquee el sistema entero

El resto son mejoras importantes pero no urgentes.
Completar estos cinco es suficiente para pasar de "proto multi-agent"
a "plataforma multi-agent" en términos operacionales.
