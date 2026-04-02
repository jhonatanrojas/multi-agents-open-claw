

## Paso 1 — Instalar el prompt como archivo antes de tocar Telegram

```bash
cp "/var/www/openclaw-multi-agents/frontend-react-migration.md" \
   /root/.openclaw/workspace/FRONTEND_PLAN.md
```

Luego crea manualmente `/root/.openclaw/workspace/FRONTEND_STATE.md`:


# Frontend Migration — Session State

Source: /var/www/openclaw-multi-agents/FRONTEND_PLAN.md
Project: /var/www/openclaw-multi-agents/frontend/

## Phase Status

| Phase | Name                        | Status  | Completed | Files |
|-------|-----------------------------|---------|-----------|-------|
| 0     | Project Scaffold            | pending |           |       |
| 1     | Types and Constants         | pending |           |       |
| 2     | Global State Store          | pending |           |       |
| 3     | API Layer                   | pending |           |       |
| 4     | SSE and WebSocket Hooks     | pending |           |       |
| 5     | Shared UI Components        | pending |           |       |
| 6     | Feature Components          | pending |           |       |
| 7     | Layout and Routing          | pending |           |       |
| 8     | Wire Everything Together    | pending |           |       |
| 9     | Three-Panel Layout UX       | pending |           |       |
| 10    | File Tree Live Updates      | pending |           |       |
| 11    | Agent Activity Stream       | pending |           |       |
| 12    | Inline Steer Controls       | pending |           |       |

## Compaction Instructions
Always preserve: Phase Status table, files created per phase.
Discard: confirmations, npm output, intermediate logs.
```

---

## Paso 2 — Agregar a AGENTS.md

Agrega este bloque al final de `/root/.openclaw/workspace/AGENTS.md`:

```markdown
---

## Frontend Migration Task

There is an active React migration in progress.
On every session start, read FRONTEND_STATE.md and report
the phase status table silently before responding.
Full plan is in FRONTEND_PLAN.md — load only the active
phase section when executing, not the entire file.
```

---

## Paso 3 — Primer mensaje desde Telegram

```
Read FRONTEND_STATE.md and report phase table.
Then read only the "Before You Start" and "Phase 0"
sections of FRONTEND_PLAN.md.

Audit the Blade source at:
/var/www/openclaw-portal/resources/views/devsquad/dashboard.blade.php

Report the AUDIT COMPLETE summary. Wait for confirmation.
```

---

## Cadencia de compactación

Compacta cada 3 fases — no cada 2 como en el upgrade anterior, porque las fases de código son más cortas que las de arquitectura:

```
Fases 0-2  → /compact
Fases 3-5  → /compact
Fases 6-8  → /compact
Fases 9-12 → /compact final
```

Antes de cada compact:

```
/compact Focus on: phase status table from FRONTEND_STATE.md,
files created per phase under frontend/src/.
Discard: npm install output, TypeScript compiler warnings,
file content listings.
```

---

## La regla más importante

Después del audit y antes de Phase 0, manda este mensaje para fijar el contexto técnico que debe sobrevivir toda la sesión:

```
Before starting Phase 0, write a FRONTEND_CONTEXT.md file
at /root/.openclaw/workspace/ with:
- Every API endpoint found in the audit
- Every data structure (Memory, Task, Agent, GatewayEvent)
- The three agent IDs, colors, and models
- The SSE and WebSocket URLs

This file is your external memory for this migration.
Read it at the start of any phase where you need API details.
