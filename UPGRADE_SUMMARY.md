# Dev Squad Architecture v2 — Upgrade Summary

**Completed:** 2026-03-28
**Upgrade Duration:** ~1 hour
**Source:** `/var/www/openclaw-multi-agents/Dev-Squad Architecture-v2.md`

---

## Executive Summary

The Dev Squad multi-agent system has been upgraded from a basic three-agent setup to a sophisticated collaborative architecture with:

- **Shared narrative context** for alignment across all agents
- **Conflict zone analysis** preventing parallel work collisions
- **Proactive heartbeat monitoring** for stall detection
- **Long-term memory** per agent for institutional knowledge
- **Adaptive versioned plans** that evolve with discoveries
- **Quality review separation** via dedicated JUDGE agent
- **Human intervention controls** via dashboard API

---

## Phase Changes Summary

| Phase | Name | Key Changes |
|-------|------|-------------|
| 1 | Shared Narrative Context | Created CONTEXT.md and CONTRACTS.md; added Pre-Task Protocol |
| 2 | Conflict Zone Analysis | Added Pre-Spawn Conflict Check; tagged tasks with parallel_safe |
| 3 | ARCH Proactive Heartbeat | Created HEARTBEAT.md; added Task State Transitions with last_updated |
| 4 | Per-Agent Long-Term Memory | Created MEMORY.md for BYTE and PIXEL with knowledge sections |
| 5 | Adaptive Plan with Versioning | Added plan_version, plan_history to MEMORY.json; Phase Retrospective Protocol |
| 6 | JUDGE Agent | Created reviewer workspace; Added Mandatory Review Gate |
| 7 | Dashboard Co-Pilot Surface | Documented steer, pause, context-update API endpoints |

---

## Files Created

| File | Size | Purpose |
|------|------|---------|
| `shared/CONTEXT.md` | 6,316 bytes | Project context for all agents |
| `shared/CONTRACTS.md` | 5,816 bytes | Interface contracts and schemas |
| `workspaces/coordinator/HEARTBEAT.md` | 2,914 bytes | Stall detection standing order |
| `workspaces/programmer/MEMORY.md` | 801 bytes | BYTE's long-term knowledge store |
| `workspaces/designer/MEMORY.md` | 820 bytes | PIXEL's long-term knowledge store |
| `workspaces/reviewer/SOUL.md` | 3,725 bytes | JUDGE agent identity and protocol |
| `dashboard/dashboard_api.py` | 11,298 bytes | Human intervention API endpoints |
| `dashboard/UI_SPEC.md` | 11,354 bytes | Dashboard UI component specifications |

## Files Modified

| File | Final Size | Changes |
|------|------------|---------|
| `workspaces/coordinator/SOUL.md` | 7,946 bytes | Added Pre-Spawn Conflict Check, Task State Transitions, Phase Retrospective Protocol, Mandatory Review Gate |
| `workspaces/programmer/SOUL.md` | 3,226 bytes | Added Pre-Task Protocol, Long-Term Memory Protocol |
| `workspaces/designer/SOUL.md` | 2,735 bytes | Added Pre-Task Protocol, Long-Term Memory Protocol |
| `config/gateway.yml` | 1,509 bytes | Added JUDGE agent registration |
| `shared/MEMORY.json` | — | Added plan_version, plan_history, parallel_safe fields, scope_change_reason |

---

## New Capabilities

### 1. Pre-Task Protocol
All agents now read CONTEXT.md and CONTRACTS.md before starting any task. If an interface isn't defined, they stop and notify ARCH rather than proceeding with assumptions.

### 2. Conflict Zone Analysis
Before spawning tasks in parallel, ARCH performs a systematic conflict analysis:
- File paths
- API endpoints
- TypeScript types
- CSS tokens

Tasks are tagged with `parallel_safe` and `parallel_safe_reason`.

### 3. Stall Detection
ARCH's heartbeat monitors for stalled tasks (>90 seconds without update). Response matrix:
- 90-180s: Send steer message
- >180s: Kill and re-spawn with decomposition

### 4. Institutional Memory
BYTE and PIXEL maintain long-term MEMORY.md files:
- **BYTE**: Architectural Patterns, Known Pitfalls, Tech Stack Preferences, Open Questions
- **PIXEL**: Design System, Accessibility Patterns, Component Library, Brand Decisions

### 5. Versioned Plans
MEMORY.json now tracks:
- `plan_version`: Incremented on any scope change
- `plan_history`: Full audit trail of changes
- `scope_change_reason`: Per-task change documentation

### 6. Quality Review Gate
JUDGE provides independent evaluation:
- Read-only access, no alternatives proposed
- Binary verdict: APPROVED or REJECTED
- Four dimensions: acceptance criteria, cross-agent consistency, contract compliance, obvious defects

### 7. Human Intervention Controls
Dashboard API for active operator control:
- `POST /api/agents/{agent_id}/steer` — Send guidance to active agent
- `POST /api/tasks/{task_id}/pause` — Pause a task for review
- `PATCH /api/context` — Update shared context with versioning

---

## Known Limitations

1. **JUDGE not yet spawned** — The JUDGE agent is registered but has not been tested in a real review cycle.

2. **Dashboard frontend not built** — UI_SPEC.md documents the components, but PIXEL has not built them yet.

3. **No automatic recovery from blocker loops** — If a task fails 3 times, it's logged to blockers[] but requires human intervention to resolve.

4. **Memory files are empty** — BYTE and PIXEL's MEMORY.md files are templates. They populate as tasks complete.

5. **No real MEMORY.json updates during tasks** — The last_updated field protocol is defined but not yet exercised.

---

## Recommended Next Steps

### Immediate
1. Run a test project through the full Dev Squad flow
2. Verify ARCH detects and handles stalled tasks
3. Spawn JUDGE for a completed task review

### Short-term
1. Spawn PIXEL to build the dashboard intervention UI
2. Connect dashboard_api.py to actual OpenClaw sessions_send
3. Add `/api/tasks/{task_id}/resume` endpoint

### Long-term
1. Add JUDGE review statistics to dashboard
2. Implement blocker auto-resolution suggestions
3. Add inter-agent message threading for context handoffs

---

## Agent Summary

| Agent | Model | Role | Workspace |
|-------|-------|------|-----------|
| ARCH | nvidia/z-ai/glm5 | Coordinator/Planner | workspaces/coordinator |
| BYTE | nvidia/moonshotai/kimi-k2.5 | Programmer | workspaces/programmer |
| PIXEL | deepseek/deepseek-chat | Designer | workspaces/designer |
| JUDGE | deepseek/deepseek-chat | Reviewer | workspaces/reviewer |

---

## Architecture Diagram

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

**Architecture v2 completed by main agent**
