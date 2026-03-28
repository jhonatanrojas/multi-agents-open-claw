# Dev Squad — Multi-Agent Programming Team with OpenClaw + Miniverse

> **ARCH** (Coordinator) → **BYTE** (Programmer) + **PIXEL** (Designer) + **JUDGE** (Reviewer)
> Cuatro agentes especializados comparten una memoria, ejecutan proyectos completos y se visualizan en el mundo pixel de Miniverse.

**OpenClaw versión soportada:** `2026.3.23-2`

---

## 🆕 Architecture v2 — Nuevas Características

La versión 2 del architecture introduce mejoras significativas en coordinación, calidad y control humano:

### 1. Contexto Narrativo Compartido
Todos los agentes leen `shared/CONTEXT.md` y `shared/CONTRACTS.md` antes de iniciar cualquier tarea. Si una interfaz no está definida, el agente se detiene y notifica a ARCH.

### 2. Análisis de Zonas de Conflicto
Antes de spawnear tareas en paralelo, ARCH realiza un análisis sistemático de conflictos potenciales:
- Rutas de archivos
- Endpoints de API
- Tipos TypeScript
- Tokens CSS

Cada tarea tiene `parallel_safe` y `parallel_safe_reason` documentados.

### 3. Detección de Estancamientos
El heartbeat de ARCH monitorea tareas estancadas (>90 segundos sin actualización):
- 90-180s: Envía mensaje steer con pista
- >180s: Mata y re-spawnea con descomposición

### 4. Memoria Institucional por Agente
BYTE y PIXEL mantienen archivos `MEMORY.md` con conocimiento acumulado:
- **BYTE**: Patrones Arquitectónicos, Errores Conocidos, Preferencias de Stack
- **PIXEL**: Sistema de Diseño, Patrones de Accesibilidad, Biblioteca de Componentes

### 5. Planes Adaptativos Versionados
`MEMORY.json` ahora rastrea:
- `plan_version`: Incrementado en cada cambio de alcance
- `plan_history`: Auditoría completa de cambios
- `scope_change_reason`: Documentación por tarea

### 6. Agente JUDGE (Revisor de Calidad)
Separación de autoridad entre planificación y aprobación:
- Acceso solo lectura, nunca escribe código
- Veredicto binario: `APPROVED` o `REJECTED: <razón>`
- Evalúa: criterios de aceptación, consistencia, contratos, defectos obvios

### 7. Controles de Intervención Humana
Dashboard API para control activo del operador:
- `POST /api/agents/{agent_id}/steer` — Envía guía a agente activo
- `POST /api/tasks/{task_id}/pause` — Pausa tarea para revisión
- `PATCH /api/context` — Actualiza contexto compartido con versionado

---

## Architecture

```
                    ┌─────────────────────────────────────┐
                    │         HUMAN OPERATOR              │
                    │    (Dashboard Intervention UI)      │
                    └──────────────┬──────────────────────┘
                                   │
                                   │ steer / pause / context
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                          ARCH (Coordinator)                       │
│  - Pre-Spawn Conflict Analysis                                     │
│  - Task State Tracking with last_updated                          │
│  - Phase Retrospective Protocol                                   │
│  - Mandatory Review Gate                                          │
│  - Heartbeat Stall Detection                                      │
└────────┬─────────────────────────────────────────┬───────────────┘
         │                                         │
         │ spawn                                   │ spawn
         ▼                                         ▼
┌────────────────────────┐               ┌────────────────────────┐
│   BYTE (Programmer)    │               │   PIXEL (Designer)     │
│ - Pre-Task Protocol    │               │ - Pre-Task Protocol    │
│ - Long-Term Memory     │◄─────────────►│ - Long-Term Memory     │
│ - Progress tracking    │  collaborate  │ - WCAG compliance      │
└────────────────────────┘               └────────────────────────┘
         │                                         │
         │ done                                    │ done
         ▼                                         ▼
┌──────────────────────────────────────────────────────────────────┐
│                    JUDGE (Reviewer)                               │
│  - Read-only evaluation                                          │
│  - Binary verdict: APPROVED / REJECTED                          │
│  - 4 dimensions: criteria, consistency, contracts, defects      │
└──────────────────────────────────────────────────────────────────┘
         │
         │ APPROVED
         ▼
┌──────────────────────────────────────────────────────────────────┐
│                    MEMORY.json                                    │
│  - plan_version, plan_history                                    │
│  - Task status: pending → in_progress → done                     │
│  - blockers[], messages[], milestones[]                          │
└──────────────────────────────────────────────────────────────────┘
```

---

## Modelos por agente

| Agente | Rol | Modelo primario | Fallback |
|--------|-------------|-------------------------------|------------------------|
| ARCH | Coordinator | `nvidia/z-ai/glm5` | — |
| BYTE | Programmer | `nvidia/moonshotai/kimi-k2.5` | `deepseek/deepseek-chat` |
| PIXEL | Designer | `deepseek/deepseek-chat` | — |
| JUDGE | Reviewer | `deepseek/deepseek-chat` | — |

Cambia los modelos sin reiniciar el código con `PUT /api/models` o editando `models_config.json`.

---

## Arquitectura Híbrida

El orquestador (`orchestrator.py`) opera en un esquema híbrido apoyándose 100% en el **OpenClaw SDK**:

- **Gestión Nativa de Sesiones**: Se utilizan `session_id`, delegando al SDK la persistencia y proveyendo mecanismos nativos como `failure_kind` para la gestión de errores.
- **Workspace Aislado**: Antes de integrar o hacer commits, el output de los agentes se filtra a través de `validate_project_structure()`, previniendo escrituras maliciosas.
- [Análisis y bitácora del Refactor Híbrido](docs/hybrid-openclaw-architecture-phases.md)

---

## Quick Start

### 1. Instalar OpenClaw
```bash
# macOS / Linux
curl -fsSL https://get.openclaw.ai | sh

# o via npm:
npm install -g openclaw
openclaw onboard
```

### 2. Clonar e instalar dependencias
```bash
git clone https://github.com/jhonatanrojas/multi-agents-open-claw dev-squad
cd dev-squad
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
mkdir -p logs output
```

### 3. Configurar variables de entorno
```bash
cp .env.example .env
# Editar .env con tus valores reales
source .env
```

Variables clave:

| Variable | Valor ejemplo | Descripción |
|-----------------------|--------------------------------|------------------------------------|
| `DASHBOARD_API_KEY` | `dev-squad-api-key-2026` | Protege todos los endpoints del API |
| `TELEGRAM_BOT_TOKEN` | `123456:ABC-...` | Notificaciones (opcional) |
| `TELEGRAM_CHAT_ID` | `-100123456789` | Chat destino de Telegram |
| `MINIVERSE_URL` | `http://localhost:4321` | Mundo pixel local o público |
| `GIT_AUTHOR_NAME` | `OpenClaw` | Identidad para git commits |
| `GIT_AUTHOR_EMAIL` | `openclaw@example.com` | Email para git commits |
| `ARCH_MODEL` | `nvidia/z-ai/glm5` | Override de modelo ARCH |
| `BYTE_MODEL` | `nvidia/moonshotai/kimi-k2.5` | Override de modelo BYTE |
| `PIXEL_MODEL` | `deepseek/deepseek-chat` | Override de modelo PIXEL |

### 4. Configurar el Gateway de OpenClaw
```bash
cp config/gateway.yml ~/.openclaw/gateway.yml
# Verifica que las rutas relativas a skills/ y workspaces/ sean accesibles
openclaw start
```

### 5. Miniverse (opcional)
```bash
npx create-miniverse
cd my-miniverse && npm run dev
# → http://localhost:4321
export MINIVERSE_URL=http://localhost:4321
```

### 6. Iniciar el Dashboard API
```bash
uvicorn dashboard_api:app --host 127.0.0.1 --port 8001
```

### 7. Ejecutar un proyecto
```bash
python orchestrator.py --allow-init-repo \
  "Construye una app de clima con frontend React y backend FastAPI"
```

---

## CLI — Referencia de argumentos

| Argumento | Default | Descripción |
|------------------------|----------|----------------------------------------------------------|
| `brief` | — | Descripción del proyecto (posicional, requerido) |
| `--repo-url` | — | URL de repositorio a clonar |
| `--repo-name` | — | Nombre del repo local |
| `--branch` | auto | Rama a crear o usar |
| `--allow-init-repo` | false | Inicializar git local si no hay URL |
| `--dry-run` | false | Probar orquestación sin llamar a OpenClaw |
| `--task-timeout-sec` | 1800 | Timeout por tarea (segundos) |
| `--phase-timeout-sec` | 7200 | Timeout por fase (segundos) |
| `--retry-attempts` | 3 | Reintentos por agente |
| `--retry-delay-sec` | 2.0 | Delay inicial entre reintentos |
| `--max-parallel-byte` | 1 | Tareas BYTE en paralelo por ronda |
| `--max-parallel-pixel` | 1 | Tareas PIXEL en paralelo por ronda |
| `--webhook-url` | — | URL que recibe POST JSON al entregar el proyecto |

---

## Dashboard API — Endpoints

El dashboard API escucha en `http://127.0.0.1:8001`. Todos los endpoints excepto `/health` y `/api/health` requieren el header:

```
X-API-Key: <valor de DASHBOARD_API_KEY>
```

| Método | Ruta | Descripción |
|--------|---------------------|-----------------------------------------------------|
| GET | `/health` | Health check público (no requiere auth) |
| GET | `/api/health` | Alias de `/health` |
| GET | `/api/state` | Snapshot completo de `MEMORY.json` |
| GET | `/api/stream` | SSE — actualizaciones cada 2 s con keepalive |
| WS | `/ws/state` | WebSocket — push a ~1 s (preferido sobre SSE) |
| GET | `/api/logs` | Últimas 100 entradas de log |
| GET | `/api/agents/world` | Proxy al listado de agentes en Miniverse |
| POST | `/api/project/start`| Lanzar nuevo proyecto |
| GET | `/api/models` | Ver configuración de modelos actual |
| PUT | `/api/models` | Actualizar modelo de un agente |
| POST | `/api/agents/{id}/steer` | 🆕 Enviar guía a agente activo |
| POST | `/api/tasks/{id}/pause` | 🆕 Pausar tarea para revisión |
| PATCH | `/api/context` | 🆕 Actualizar contexto compartido |

---

## Project Structure

```
dev-squad/
├── orchestrator.py              ← Punto de entrada principal
├── coordination.py              ← Bootstrap de repos, skills, git commit
├── shared_state.py              ← Memoria compartida (file-locked)
├── dashboard_api.py             ← FastAPI: SSE + WebSocket + REST
├── miniverse_bridge.py          ← Bridge HTTP a Miniverse
├── DevSquadDashboard.jsx        ← Dashboard React
├── gateway.yml                  ← Config OpenClaw (raíz)
├── models_config.json           ← Modelos por agente
├── .env.example                 ← Variables de entorno documentadas
├── requirements.txt
│
├── workspaces/
│   ├── coordinator/
│   │   ├── SOUL.md              ← Identidad de ARCH
│   │   └── HEARTBEAT.md         ← 🆕 Stall detection standing order
│   ├── programmer/
│   │   ├── SOUL.md              ← Identidad de BYTE
│   │   └── MEMORY.md            ← 🆕 Long-term knowledge store
│   ├── designer/
│   │   ├── SOUL.md              ← Identidad de PIXEL
│   │   └── MEMORY.md            ← 🆕 Long-term knowledge store
│   └── reviewer/
│       └── SOUL.md              ← 🆕 Identidad de JUDGE
│
├── skills/
│   ├── miniverse-bridge/        ← Skill de heartbeat Miniverse
│   └── stack-router/            ← Skill de routing por stack
│
├── config/
│   └── gateway.yml              ← Config OpenClaw
│
├── shared/
│   ├── MEMORY.json              ← Estado compartido
│   ├── CONTEXT.md               ← 🆕 Project context for all agents
│   └── CONTRACTS.md             ← 🆕 Interface contracts and schemas
│
├── dashboard/
│   ├── dashboard_api.py         ← 🆕 Human intervention API
│   └── UI_SPEC.md               ← 🆕 UI component specifications
│
├── deploy/
│   ├── systemd/
│   │   ├── openclaw-multiagent.service
│   │   └── openclaw-dashboard.service
│   └── apache/
│       └── openclaw-dashboard.conf
│
├── scripts/
│   ├── check_health.py          ← Health check CLI
│   └── install_systemd.sh       ← Instalador de servicios systemd
│
├── output/                      ← Código y archivos generados
└── logs/
    ├── orchestrator.log         ← Stdout del orquestador
    └── orchestrator.jsonl       ← Logs estructurados (JSON Lines)
```

---

## Flujo de ejecución

```
main()
├── acquire_run_lock()           ← previene instancias duplicadas
├── task recovery                ← resetea in_progress → pending
├── _check_gateway_health()      ← verifica gateway
│
├── Phase 1: plan_project()
│   └── ARCH genera plan JSON con fases y tareas
│
├── bootstrap_repository()       ← clona o inicializa repo
│
├── Phase 2: execution loop
│   ├── relay_team_messages()    ← drena inboxes Miniverse
│   ├── asyncio.gather(N×BYTE + M×PIXEL)
│   │   ├── agent.execute(session_id)
│   │   └── validate_project_structure()
│   ├── 🆕 Pre-Spawn Conflict Check
│   ├── 🆕 Task state tracking with last_updated
│   └── commit_task_output()     ← git add -A + git commit
│
├── 🆕 Phase Retrospective
│   ├── Read all produced files
│   ├── Compare against original tasks
│   ├── Identify discoveries affecting pending tasks
│   └── Update plan_version if needed
│
├── 🆕 Mandatory Review Gate
│   └── Spawn JUDGE for quality review
│
└── Phase 3: final_review()
    ├── ARCH genera DELIVERY.md
    ├── Telegram notification
    └── POST webhook-url
```

---

## Miniverse Integration

Cada agente envía heartbeats cada 30 segundos:

| Agente | Estado | Comportamiento en Miniverse |
|--------|------------|------------------------------|
| ARCH | `thinking` | Burbuja de pensamiento 💭 |
| ARCH | `working` | Camina al escritorio y teclea |
| BYTE | `working` | Camina al escritorio y teclea |
| PIXEL | `working` | Camina al escritorio y teclea |
| Any | `speaking` | Burbuja de diálogo 💬 |
| Any | `idle` | Deambula |
| Any | `error` | Indicador rojo |

---

## Seguridad

- **Auth API Key**: todos los endpoints (excepto `/health`) requieren `X-API-Key`
- **Validación de brief**: longitud 10–2000 chars; caracteres de control eliminados
- **CORS**: configurado en `allow_origins=["*"]` — restringir en producción
- **File locking**: `fcntl.flock(LOCK_EX)` en cada escritura a `MEMORY.json`
- 🆕 **Pre-Task Protocol**: agentes leen CONTEXT.md y CONTRACTS.md antes de ejecutar
- 🆕 **Conflict Zone Analysis**: ARCH analiza conflictos antes de spawn paralelo

---

## Troubleshooting

**Gateway no responde al arrancar**
```
RuntimeError: Gateway OpenClaw no responde...
```
→ Ejecutar `openclaw start` y verificar `~/.openclaw/gateway.yml`.

**Tarea bloqueada en `in_progress`**
→ Al reiniciar el orquestador se resetea automáticamente a `pending`.
→ 🆕 ARCH detecta stalls >90s y envía steer o re-spawnea.

**MEMORY.json crece demasiado**
→ Truncación automática: `log` ≤ 500, `messages` ≤ 200, `blockers` ≤ 100.

**Dry-run para validar sin gastar tokens**
```bash
python orchestrator.py --dry-run "Mi proyecto de prueba"
```

---

## Changelog

### v2.0.0 — 2026-03-28
- ✨ Added shared CONTEXT.md and CONTRACTS.md for narrative alignment
- ✨ Added Pre-Spawn Conflict Zone Analysis
- ✨ Added ARCH heartbeat stall detection (>90s threshold)
- ✨ Added per-agent MEMORY.md for long-term knowledge
- ✨ Added plan_version and plan_history for adaptive versioning
- ✨ Added JUDGE agent for quality review separation
- ✨ Added human intervention API endpoints (steer, pause, context)
- 📝 Updated all SOUL.md files with Pre-Task Protocol
- 📝 Added HEARTBEAT.md for coordinator standing orders
- 📝 Added UPGRADE_SUMMARY.md with full documentation

### v1.0.0 — 2026-03-25
- Initial release with ARCH, BYTE, PIXEL agents
- Miniverse integration with heartbeats
- Dashboard API with SSE and WebSocket
- Systemd deployment support

---

## Licencia

MIT License — ver [LICENSE](LICENSE) para detalles.

---

**Construido con ❤️ usando OpenClaw**
