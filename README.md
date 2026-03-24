# Dev Squad — Multi-Agent Programming Team with OpenClaw + Miniverse

> **ARCH** (Coordinator) → **BYTE** (Programmer) + **PIXEL** (Designer)  
> All agents share one memory, run in Miniverse's pixel world, and deliver code end-to-end.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     orchestrator.py                     │
│   asyncio + openclaw-sdk Pipeline                       │
└────────┬─────────────────┬──────────────────────────────┘
         │                 │
    ┌────▼────┐       ┌────▼────┐
    │  ARCH   │       │Dashboard│
    │ Opus 4  │       │   API   │
    └────┬────┘       └────┬────┘
         │ assigns         │ SSE
    ┌────▼────┐   ┌───────▼──────┐
    │  BYTE   │   │  PIXEL       │
    │Sonnet 4 │   │  Sonnet 4    │
    └────┬────┘   └──────┬───────┘
         │               │
    ┌────▼───────────────▼───────┐
    │       shared/MEMORY.json   │  ← shared state bus
    └────────────────────────────┘
         │               │
    ┌────▼───────────────▼───────┐
    │   Miniverse Pixel World    │  ← live visualization
    └────────────────────────────┘
```

---

## Quick Start

### 1. Install OpenClaw
```bash
# macOS / Linux
curl -fsSL https://get.openclaw.ai | sh
# or via npm:
npm install -g openclaw
openclaw onboard
```

### 2. Clone & install deps
```bash
git clone <this-repo> dev-squad
cd dev-squad
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
mkdir -p logs output
```

### 3. Configure OpenClaw Gateway
```bash
cp config/gateway.yml ~/.openclaw/gateway.yml
# Edit model API keys if needed (OpenClaw uses your onboarded credentials)
```

If you copy the gateway file into `~/.openclaw/`, make sure the relative paths
it references are also available there. The simplest options are:
- copy or symlink this repo's `skills/`, `workspaces/`, and `shared/`
  directories into `~/.openclaw/`, or
- keep a local copy of the gateway file next to the repo and launch OpenClaw
  from that root so the relative paths resolve correctly.

### 4. Start Miniverse (local) — optional, or use public world
```bash
npx create-miniverse
cd my-miniverse && npm run dev
# → http://localhost:4321
# Set env var:
export MINIVERSE_URL=http://localhost:4321
```

### 5. Start the OpenClaw Gateway
```bash
openclaw start
```

### 6. Start the Dashboard API
```bash
uvicorn dashboard_api:app --reload --port 8080
```

### 7. Run a project!
```bash
python orchestrator.py --allow-init-repo "Build a weather app with React frontend and a FastAPI backend that fetches real weather data"
```

If you already have a repository, pass it explicitly:

```bash
python orchestrator.py --repo-url https://github.com/you/repo.git --branch codex/weather-app "Build a weather app..."
```

If no repo is supplied and local init is disabled, ARCH will pause and request
repository approval over Telegram.

Or via the dashboard UI (open `dashboard.html` or the React app on port 3000).

---

## Project Structure

```
dev-squad/
├── workspaces/
│   ├── coordinator/SOUL.md    ← ARCH personality & instructions
│   ├── programmer/SOUL.md     ← BYTE personality & instructions
│   └── designer/SOUL.md       ← PIXEL personality & instructions
├── skills/
│   └── shared/
│       └── miniverse_bridge.py  ← Miniverse HTTP integration
├── config/
│   └── gateway.yml            ← OpenClaw multi-agent config
├── shared/
│   └── MEMORY.json            ← Shared memory (all agents read/write)
├── output/                    ← All generated code & design files
├── logs/
│   └── orchestrator.log
├── orchestrator.py            ← Main entry point
├── dashboard_api.py           ← FastAPI SSE server for dashboard
└── requirements.txt
```

---

## Miniverse Integration

Each agent sends heartbeats every 30 seconds:

| Agent | State        | Miniverse behavior        |
|-------|-------------|---------------------------|
| ARCH  | `thinking`  | Thought bubble 💭          |
| ARCH  | `working`   | Walks to desk, types       |
| BYTE  | `working`   | Walks to desk, types       |
| PIXEL | `working`   | Walks to desk, types       |
| Any   | `speaking`  | Speech bubble 💬           |
| Any   | `idle`      | Wanders around             |
| Any   | `error`     | Red indicator              |

Agents also send **direct messages** to each other via `/api/act` (type: `message`).

---

## Dashboard

The React dashboard (`dashboard/`) connects to:
- `GET /api/stream` — SSE for live MEMORY.json updates
- `GET /api/agents/world` — proxied Miniverse agent list
- `POST /api/project/start` — submit a new project

---

## Environment Variables

| Variable               | Default                                         | Description              |
|------------------------|-------------------------------------------------|--------------------------|
| `MINIVERSE_URL`        | `https://miniverse-public-production.up.railway.app` | Miniverse server    |
| `OPENCLAW_GATEWAY_WS_URL` | auto-detect                                 | OpenClaw gateway WS URL  |

---

## Example Session

```
🚀 Dev Squad starting — Project: Build a TODO app...

📋 Phase 1: Planning...
[miniverse] arch heartbeat started
[ARCH speaks] "Plan ready! 8 tasks across 3 phases."

⚙️  Phase 2: Executing tasks...
[BYTE speaks] "Starting T-001: FastAPI project scaffold"
[PIXEL speaks] "Starting T-002: Design system tokens"
[BYTE speaks] "✅ T-001 complete! 4 file(s) written."
...

🔍 Phase 3: Final review...
[ARCH speaks] "🎉 Project delivered! See output/DELIVERY.md"

✅ Dev Squad done. Check ./output/ for all files.
```
