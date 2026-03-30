
## Meta-prompt de arranque

Guarda esto en `/var/www/openclaw-multi-agents/BOOTSTRAP_MULTIAGENT.md`:

```
You are the main OpenClaw agent. The user has given you an improvement
plan for a multi-agent system. Your job in this session is NOT to
implement the plan. Your job is to read it, reconcile it with the
actual codebase, and install everything needed so that future sessions
can execute it phase by phase via Telegram without losing context.

---

## Step 1 — Read the plan

Read this file completely:
/var/www/openclaw-multi-agents/mejorar-sistema-multiagente.md

After reading, extract and report exactly:

PLAN AUDIT
- Total phases found: [N]
- Phase names and objectives: [list]
- Technologies assumed by plan: [list]
- Files referenced by plan: [list every filename mentioned]
- New files the plan wants to create: [list]
- Interfaces/types defined: [list every interface block]

Then read the actual codebase to reconcile:

CODEBASE AUDIT
Read these paths and report what actually exists:

/var/www/openclaw-multi-agents/
  - List all .py, .ts, .js files found (max 2 levels deep)
  - Identify: which files the plan references that DO exist
  - Identify: which files the plan references that DO NOT exist
  - Identify: which files exist that the plan does not mention

/var/www/openclaw-multi-agents/dev-squad/dashboard_api.py
  - List every route decorator found (@app.get, @app.post, etc)
  - Identify the _stop_orchestrator duplication mentioned in plan
  - Identify the incorrect decorators mentioned in plan

/var/www/openclaw-multi-agents/orchestrator.py
  - Confirm it exists and report its entry point

Report as:

RECONCILIATION
- Plan assumes TypeScript for: [list files]
- Reality is Python for: [list actual files]
- Conflicts requiring resolution before execution: [list]
- Plan tasks that can execute as-is: [list]
- Plan tasks that need adaptation to actual stack: [list]

Wait for user confirmation before continuing to Step 2.

---

## Step 2 — Resolve stack conflict

The plan references botOrchestrator.service.ts and salesGraphRunner.ts
which may not exist in this Python-based system. Before installing
the plan, create an adaptation map.

Write /root/.openclaw/workspace/CONTEXT_multiagent.md with:

# Multi-Agent System — Technical Context

## Actual stack
[fill from codebase audit]

## Plan → Reality mapping
| Plan reference          | Actual file                    | Action needed |
|-------------------------|--------------------------------|---------------|
| botOrchestrator.service | orchestrator.py                | adapt         |
| salesGraphRunner.ts     | [actual equivalent or missing] | create/adapt  |
| persistence layer       | shared/MEMORY.json             | formalize     |
| RunContext interface    | [TypeScript vs Python]         | port to Python |
| SupervisorService       | [missing]                      | create        |
[fill all rows from the plan]

## API endpoints that exist today
[list from dashboard_api.py audit]

## API endpoints the plan wants to add
[list from plan]

## Environment
- Backend: Python / FastAPI
- Runtime: OpenClaw
- State file: shared/MEMORY.json
- Dashboard: Laravel Blade + React (in progress)

## Critical bugs to fix first (Phase 0)
[list from F0.1 through F0.6 with actual file paths]

---

## Step 3 — Install state tracker

Create /root/.openclaw/workspace/STATE_multiagent.md:

# Multi-Agent Hardening — Session State

Installed: [today YYYY-MM-DD]
Source: /var/www/openclaw-multi-agents/mejorar-sistema-multiagente.txt
Context: /root/.openclaw/workspace/CONTEXT_multiagent.md
Plan file: /root/.openclaw/workspace/PLAN_multiagent.md

## Stack reality
Backend: Python / FastAPI
Orchestrator: orchestrator.py
State: dev-squad/shared/MEMORY.json
Dashboard API: dev-squad/dashboard_api.py

## Phase Status

| Phase | Name                                  | Status  | Completed | Files |
|-------|---------------------------------------|---------|-----------|-------|
| F0.1  | Fix auth SSE                          | pending |           |       |
| F0.2  | Fix dashboard_api.py bugs             | pending |           |       |
| F0.3  | Fix model_fallback.py                 | pending |           |       |
| F0.4  | Restrict CORS                         | pending |           |       |
| F0.5  | Modularize backend                    | pending |           |       |
| F0.6  | Minimum tests                         | pending |           |       |
| F1.1  | Formalize RunContext                  | pending |           |       |
| F1.2  | Persistence layer                     | pending |           |       |
| F1.3  | Execution lock                        | pending |           |       |
| F1.4  | UI sync endpoint                      | pending |           |       |
| F1.5  | Normalize Sales Graph states          | pending |           |       |
| F2.1  | Create SupervisorService              | pending |           |       |
| F2.2  | Graph as intent generator             | pending |           |       |
| F2.3  | Task entity                           | pending |           |       |
| F2.4  | Agents as workers only                | pending |           |       |
| F2.5  | New execution flow                    | pending |           |       |
| F3.1  | Event bus                             | pending |           |       |
| F3.2  | Event log                             | pending |           |       |
| F3.3  | Timeline UI                           | pending |           |       |
| F3.4  | Replay                                | pending |           |       |
| F3.5  | Observability                         | pending |           |       |

## Compaction Schedule
| Compact after | Reason                                    |
|---------------|-------------------------------------------|
| F0.6          | Phase 0 complete, heavy bug fix context   |
| F1.5          | Phase 1 complete, persistence established |
| F2.5          | Phase 2 complete, supervisor built        |
| F3.5          | Phase 3 complete, full platform done      |

## Active Blockers
(none)

## Milestones
(none yet)

## Compaction Checkpoint
(filled automatically before each /compact)

## Compaction Instructions
Always preserve: Phase Status table with current values,
Stack reality section, Active Blockers, Milestones,
Compaction Checkpoint. Discard: code listings, test output,
pip/npm logs, file content dumps, intermediate confirmations.

---

## Step 4 — Copy plan with Python adaptations noted

Copy the source plan verbatim to:
/root/.openclaw/workspace/PLAN_multiagent.md

Then append a section at the end called
"## Python Adaptation Notes" with one note per phase
explaining which TypeScript constructs must be implemented
in Python instead, based on your reconciliation in Step 2.

For example:
- RunContext interface → Python dataclass or TypedDict
- Redis setnx lock → file lock or Redis if available
- repository pattern → SQLite or JSON file abstraction
- SupervisorService class → Python class in supervisor.py

---

## Step 5 — Patch AGENTS.md

Read /root/.openclaw/workspace/AGENTS.md.
Append this block at the end:

---

## Active Plan: Multi-Agent System Hardening

State file: /root/.openclaw/workspace/STATE_multiagent.md
Plan file: /root/.openclaw/workspace/PLAN_multiagent.md
Context file: /root/.openclaw/workspace/CONTEXT_multiagent.md
Project root: /var/www/openclaw-multi-agents/

On every session start:
1. Read STATE_multiagent.md silently
2. Report the Phase Status table to the user
3. Read CONTEXT_multiagent.md when you need technical details
4. Do not load PLAN_multiagent.md fully — read only the active
   phase section when the user asks to execute it
5. After completing any phase: update STATE_multiagent.md
   status and files columns immediately
6. Before any /compact: write current phase table to
   STATE_multiagent.md under Compaction Checkpoint

Critical constraint: this system is Python/FastAPI, not
TypeScript. When the plan mentions .ts files, implement the
equivalent in Python. Check CONTEXT_multiagent.md for the
mapping before writing any file.

---

Verify AGENTS.md was patched correctly.

---

## Step 6 — Generate Telegram script

Create /root/.openclaw/workspace/TELEGRAM_multiagent.md:

# Telegram Script — Multi-Agent Hardening

## Send this first in every session
```
Read STATE_multiagent.md and report the phase status table.
```

## Before starting Phase 0 (send once)
```
Read CONTEXT_multiagent.md and the F0.1 through F0.6 sections
of PLAN_multiagent.md. List every file you will modify and
what change you will make. Wait for confirmation.
```

## To execute any phase (replace CODE with F0.1, F1.2, etc)
```
Read phase [CODE] from PLAN_multiagent.md and CONTEXT_multiagent.md.
Execute it completely. Update STATE_multiagent.md when done.
End with: ✅ [CODE] COMPLETE
```

## Compaction (check schedule in STATE_multiagent.md first)
```
Before compacting, write the current phase table to
STATE_multiagent.md under Compaction Checkpoint with today's date.
Then: /compact Focus on: Compaction Checkpoint from
STATE_multiagent.md, CONTEXT_multiagent.md key points.
Discard: code output, test results, file listings.
```

## If a phase is blocked
```
Phase [CODE] is blocked: [describe the issue].
Read CONTEXT_multiagent.md and diagnose before retrying.
Add the blocker to STATE_multiagent.md under Active Blockers.
```

## After a session gap or restart
```
Read STATE_multiagent.md and CONTEXT_multiagent.md.
Tell me which phase to execute next and any open blockers.
```

## Check progress at any time
```
Read STATE_multiagent.md and report the full phase table.
```

---

## Step 7 — Final verification

Run these checks, report pass or fail for each:

1. /root/.openclaw/workspace/PLAN_multiagent.md exists with
   Python Adaptation Notes section appended
2. /root/.openclaw/workspace/STATE_multiagent.md exists with
   all 20 phases listed as pending
3. /root/.openclaw/workspace/CONTEXT_multiagent.md exists with
   the Plan → Reality mapping table filled
4. /root/.openclaw/workspace/AGENTS.md ends with the Active Plan
   block and references CONTEXT_multiagent.md
5. /root/.openclaw/workspace/TELEGRAM_multiagent.md exists with
   the complete script including all message templates

Fix any failed check before reporting completion.

When all pass, send:
"✅ Multi-agent hardening plan installed.
20 phases tracked in STATE_multiagent.md.
Start execution from Telegram using TELEGRAM_multiagent.md.
Critical: read CONTEXT_multiagent.md reconciliation section
before executing Phase 0 — the plan uses TypeScript but your
system is Python."
```

---

## Cómo activarlo desde Telegram

Un solo mensaje:

```
Read /var/www/openclaw-multi-agents/BOOTSTRAP_MULTIAGENT.md
and execute it completely. The source plan is at:
/var/www/openclaw-multi-agents/mejorar-sistema-multiagente.txt
```
conflicto TypeScript vs Python, instala los trackers, y te entrega el script de Telegram listo para ejecutar las 20 fases.