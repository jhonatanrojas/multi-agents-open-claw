# Dev Squad — Multi-Agent Programming Team with OpenClaw + Miniverse

> **ARCH** (Coordinator) → **BYTE** (Programmer) + **PIXEL** (Designer)
> Tres agentes especializados comparten una memoria, ejecutan proyectos completos y se visualizan en el mundo pixel de Miniverse.

**OpenClaw versión soportada:** `2026.3.23-2`

---

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│                      orchestrator.py                      │
│   asyncio pipeline · lockfile · recovery · gateway check  │
└────────┬───────────────────┬──────────────────────────────┘
         │                   │
    ┌────▼─────┐        ┌────▼────────┐
    │   ARCH   │        │ Dashboard   │
    │ GLM-5    │        │   API       │
    └────┬─────┘        └──┬──────────┘
         │ assign          │ SSE / WebSocket
    ┌────▼─────┐   ┌───────▼──────────┐
    │   BYTE   │   │      PIXEL       │
    │ Kimi-K2.5│   │  DeepSeek Chat   │
    └────┬─────┘   └──────┬───────────┘
         │                │
    ┌────▼────────────────▼───────┐
    │       shared/MEMORY.json    │  ← bus de estado compartido
    │  file-locked · truncating   │
    └────────────────────────────-┘
         │                │
    ┌────▼────────────────▼───────┐
    │    Miniverse Pixel World    │  ← visualización en tiempo real
    └─────────────────────────────┘
```

---

## Modelos por agente

| Agente | Rol         | Modelo primario               | Fallback               |
|--------|-------------|-------------------------------|------------------------|
| ARCH   | Coordinator | `nvidia/z-ai/glm5`            | —                      |
| BYTE   | Programmer  | `nvidia/moonshotai/kimi-k2.5` | `deepseek/deepseek-chat` |
| PIXEL  | Designer    | `deepseek/deepseek-chat`      | —                      |

Cambia los modelos sin reiniciar el código con `PUT /api/models` o editando `models_config.json`.

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
source .env   # o usa un gestor como direnv
```

Variables clave:

| Variable              | Valor ejemplo                  | Descripción                        |
|-----------------------|--------------------------------|------------------------------------|
| `DASHBOARD_API_KEY`   | `dev-squad-api-key-2026`       | Protege todos los endpoints del API |
| `TELEGRAM_BOT_TOKEN`  | `123456:ABC-...`               | Notificaciones (opcional)          |
| `TELEGRAM_CHAT_ID`    | `-100123456789`                | Chat destino de Telegram           |
| `MINIVERSE_URL`       | `http://localhost:4321`        | Mundo pixel local o público        |
| `GIT_AUTHOR_NAME`     | `OpenClaw`                     | Identidad para git commits         |
| `GIT_AUTHOR_EMAIL`    | `openclaw@example.com`         | Email para git commits             |
| `ARCH_MODEL`          | `nvidia/z-ai/glm5`             | Override de modelo ARCH            |
| `BYTE_MODEL`          | `nvidia/moonshotai/kimi-k2.5`  | Override de modelo BYTE            |
| `PIXEL_MODEL`         | `deepseek/deepseek-chat`       | Override de modelo PIXEL           |

### 4. Configurar el Gateway de OpenClaw
```bash
cp config/gateway.yml ~/.openclaw/gateway.yml
# Verifica que las rutas relativas a skills/ y workspaces/ sean accesibles
openclaw start
```

### 5. Miniverse (opcional — o usar el mundo público)
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

Con opciones avanzadas:
```bash
python orchestrator.py \
  --repo-url https://github.com/tu-usuario/repo.git \
  --branch codex/feature \
  --max-parallel-byte 2 \
  --max-parallel-pixel 1 \
  --webhook-url https://ci.ejemplo.com/hooks/devsquad \
  "Descripción del proyecto..."
```

---

## CLI — Referencia de argumentos

| Argumento              | Default  | Descripción                                              |
|------------------------|----------|----------------------------------------------------------|
| `brief`                | —        | Descripción del proyecto (posicional, requerido)        |
| `--repo-url`           | —        | URL de repositorio a clonar                              |
| `--repo-name`          | —        | Nombre del repo local                                    |
| `--branch`             | auto     | Rama a crear o usar                                      |
| `--allow-init-repo`    | false    | Inicializar git local si no hay URL                     |
| `--dry-run`            | false    | Probar orquestación sin llamar a OpenClaw               |
| `--task-timeout-sec`   | 1800     | Timeout por tarea (segundos)                            |
| `--phase-timeout-sec`  | 7200     | Timeout por fase (segundos)                             |
| `--retry-attempts`     | 3        | Reintentos por agente                                   |
| `--retry-delay-sec`    | 2.0      | Delay inicial entre reintentos                          |
| `--max-parallel-byte`  | 1        | Tareas BYTE en paralelo por ronda                       |
| `--max-parallel-pixel` | 1        | Tareas PIXEL en paralelo por ronda                      |
| `--webhook-url`        | —        | URL que recibe POST JSON al entregar el proyecto        |

---

## Dashboard API — Endpoints

El dashboard API escucha en `http://127.0.0.1:8001`.
Todos los endpoints excepto `/health` y `/api/health` requieren el header:

```
X-API-Key: <valor de DASHBOARD_API_KEY>
```

| Método | Ruta                | Descripción                                         |
|--------|---------------------|-----------------------------------------------------|
| GET    | `/health`           | Health check público (no requiere auth)             |
| GET    | `/api/health`       | Alias de `/health`                                  |
| GET    | `/api/state`        | Snapshot completo de `MEMORY.json`                  |
| GET    | `/api/stream`       | SSE — actualizaciones cada 2 s con keepalive        |
| WS     | `/ws/state`         | WebSocket — push a ~1 s (preferido sobre SSE)       |
| GET    | `/api/logs`         | Últimas 100 entradas de log (memoria + JSONL)       |
| GET    | `/api/agents/world` | Proxy al listado de agentes en Miniverse            |
| POST   | `/api/project/start`| Lanzar nuevo proyecto (spawnea orchestrator)        |
| GET    | `/api/models`       | Ver configuración de modelos actual                 |
| PUT    | `/api/models`       | Actualizar modelo de un agente (sin reiniciar)      |

### Ejemplo: lanzar proyecto vía API
```bash
curl -X POST http://127.0.0.1:8001/api/project/start \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-squad-api-key-2026" \
  -d '{
    "brief": "Construye una API REST de tareas con FastAPI y SQLite",
    "allow_init_repo": true,
    "max_parallel_byte": 2,
    "dry_run": false
  }'
```

### Ejemplo: cambiar modelo de BYTE
```bash
curl -X PUT http://127.0.0.1:8001/api/models \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-squad-api-key-2026" \
  -d '{"byte": "deepseek/deepseek-chat"}'
```

---

## Producción con systemd

El repo incluye servicios listos para VPS en `deploy/systemd/`:

```bash
sudo bash scripts/install_systemd.sh /var/www/openclaw-multi-agents
sudo systemctl start openclaw-multiagent
sudo systemctl start openclaw-dashboard
sudo systemctl status openclaw-multiagent --no-pager
sudo systemctl status openclaw-dashboard --no-pager
```

El archivo de entorno compartido es `/etc/default/openclaw-multiagent`.
Agrega ahí `DASHBOARD_API_KEY`, `TELEGRAM_BOT_TOKEN`, etc.

Health check desde CLI:
```bash
python scripts/check_health.py --url http://127.0.0.1:8001/health
journalctl -u openclaw-multiagent -f
journalctl -u openclaw-dashboard -f
```

---

## Project Structure

```
dev-squad/
├── orchestrator.py            ← Punto de entrada principal
├── coordination.py            ← Bootstrap de repos, skills, git commit
├── shared_state.py            ← Memoria compartida (file-locked, truncante)
├── dashboard_api.py           ← FastAPI: SSE + WebSocket + REST
├── miniverse_bridge.py        ← Bridge HTTP a Miniverse
├── DevSquadDashboard.jsx      ← Dashboard React (SSE + WebSocket)
├── gateway.yml                ← Config OpenClaw (raíz)
├── models_config.json         ← Modelos por agente (editable en runtime)
├── .env.example               ← Variables de entorno documentadas
├── requirements.txt
│
├── workspaces/
│   ├── coordinator/SOUL.md    ← Identidad e instrucciones de ARCH
│   ├── programmer/SOUL.md     ← Identidad e instrucciones de BYTE
│   └── designer/SOUL.md       ← Identidad e instrucciones de PIXEL
│
├── skills/
│   ├── miniverse-bridge/      ← Skill de heartbeat Miniverse
│   └── stack-router/          ← Skill de routing por stack tecnológico
│
├── config/
│   └── gateway.yml            ← Config OpenClaw (copia para ~/.openclaw/)
│
├── shared/
│   └── MEMORY.json            ← Estado compartido (todos los agentes)
│
├── deploy/
│   ├── systemd/
│   │   ├── openclaw-multiagent.service
│   │   └── openclaw-dashboard.service
│   └── apache/
│       └── openclaw-dashboard.conf
│
├── scripts/
│   ├── check_health.py        ← Health check CLI
│   └── install_systemd.sh     ← Instalador de servicios systemd
│
├── prompts/
│   └── orchestrator-systemd-phases.md  ← Guía de despliegue en VPS
│
├── output/                    ← Código y archivos generados
└── logs/
    ├── orchestrator.log       ← Stdout del orquestador
    └── orchestrator.jsonl     ← Logs estructurados (JSON Lines)
```

---

## Flujo de ejecución

```
main()
 ├── acquire_run_lock()          ← previene instancias duplicadas
 ├── task recovery               ← resetea in_progress → pending al arrancar
 ├── _check_gateway_health()     ← verifica gateway antes de consumir tokens
 ├── Phase 1: plan_project()
 │     └── ARCH genera plan JSON con fases y tareas
 ├── bootstrap_repository()      ← clona, inicializa o usa repo existente
 ├── Phase 2: execution loop
 │     ├── relay_team_messages() ← drena inboxes Miniverse (dedup)
 │     ├── asyncio.gather(N×BYTE + M×PIXEL)  ← paralelo configurable
 │     └── commit_task_output()  ← git add -A + git commit por tarea
 └── Phase 3: final_review()
       ├── ARCH genera DELIVERY.md
       ├── Telegram notification
       └── POST webhook-url (si configurado)
```

---

## Miniverse Integration

Cada agente envía heartbeats cada 30 segundos:

| Agente | Estado      | Comportamiento en Miniverse |
|--------|------------|------------------------------|
| ARCH   | `thinking` | Burbuja de pensamiento 💭    |
| ARCH   | `working`  | Camina al escritorio y teclea |
| BYTE   | `working`  | Camina al escritorio y teclea |
| PIXEL  | `working`  | Camina al escritorio y teclea |
| Any    | `speaking` | Burbuja de diálogo 💬        |
| Any    | `idle`     | Deambula                     |
| Any    | `error`    | Indicador rojo               |

Los agentes también se envían **mensajes directos** a través de `/api/act` (type: `message`). Los mensajes duplicados se descartan automáticamente.

---

## Seguridad

- **Auth API Key**: todos los endpoints (excepto `/health`) requieren `X-API-Key`.
  Clave de ejemplo para desarrollo: `dev-squad-api-key-2026`.
- **Validación de brief**: longitud 10–2000 chars; caracteres de control eliminados.
- **CORS**: configurado en `allow_origins=["*"]` — restringir en producción si el dashboard se publica.
- **File locking**: `fcntl.flock(LOCK_EX)` en cada escritura a `MEMORY.json` previene corrupción entre procesos.

---

## Troubleshooting

**Gateway no responde al arrancar**
```
RuntimeError: Gateway OpenClaw no responde. Verifica que openclaw-gateway esté activo...
```
→ Ejecutar `openclaw start` y verificar `~/.openclaw/gateway.yml`.

**Tarea bloqueada en `in_progress`**
→ Al reiniciar el orquestador se resetea automáticamente a `pending`.

**MEMORY.json crece demasiado**
→ Truncación automática: `log` ≤ 500, `messages` ≤ 200, `blockers` ≤ 100 entradas.

**Dry-run para validar sin gastar tokens**
```bash
python orchestrator.py --dry-run "Mi proyecto de prueba"
```

---

## Example Session

```
Dev Squad iniciando - Proyecto: Build a TODO app...

Fase 1: Planificación...
[miniverse] arch heartbeat started → https://miniverse-public-production.up.railway.app
[ARCH speaks] "Plan listo. 8 tareas en 3 fases."

Fase 2: Ejecutando tareas...
[recovery] 0 tarea(s) reseteadas a pending.
[BYTE speaks]  "Iniciando T-001: FastAPI project scaffold"
[PIXEL speaks] "Iniciando T-002: Design system tokens"
[BYTE speaks]  "Completada T-001: se escribieron 4 archivo(s)."
[git] Commit creado: [byte] T-001: FastAPI project scaffold
...

Fase 3: Revisión final...
[ARCH speaks] "Proyecto entregado. Revisa DELIVERY.md"
[webhook] POST https://ci.ejemplo.com/hooks/devsquad → 200

Dev Squad finalizado. Revisa ./output/ para ver todos los archivos.
```
