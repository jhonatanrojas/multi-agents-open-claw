# CONTEXT.md — Dev Squad Project Context

This document provides the narrative context for all agents working on Dev Squad projects. Read this before starting any task.

## What Is Being Built and Why

Dev Squad is a multi-agent programming team orchestrated by ARCH (Coordinator) with specialized workers: BYTE (Programmer) and PIXEL (Designer). The system exists to transform natural-language project briefs into production-ready code without requiring the human operator to write implementation details.

The motivation is straightforward: project owners often have clear requirements but lack the time or expertise to translate those requirements into working software. Dev Squad bridges this gap by providing a coordinated team of AI agents that can plan, implement, and deliver complete projects autonomously.

## Architectural Decisions Already Made

### Multi-Agent Architecture
We chose a coordinator-worker pattern over a single-agent approach. The reasoning is simple: specialization improves quality. A coordinator agent (ARCH) focuses on planning and task decomposition, while worker agents (BYTE for code, PIXEL for design) focus on their domains. This separation allows each agent to use models optimized for their task type rather than forcing a single model to excel at everything.

### Shared Memory Model
All agents read from and write to a single `MEMORY.json` file. This centralizes state and prevents the coordination problems that arise from distributed state. The tradeoff is potential contention when multiple agents write simultaneously—we mitigate this with a lock file and careful write ordering.

### Task-Based Execution
Work proceeds in discrete tasks, each with explicit acceptance criteria. Tasks are the atomic unit of work. This granularity allows for clear progress tracking, easy resumption after failures, and straightforward retry logic when agents encounter problems.

### Orchestrator Pattern
An external orchestrator script manages the lifecycle of agent runs. The orchestrator spawns agents, monitors their progress, handles timeouts, and manages retries. This separation keeps agent logic focused on their work rather than infrastructure concerns.

### Gateway Integration
Agents communicate through OpenClaw's session spawning mechanism (`sessions_spawn`). This provides bidirectional control—the orchestrator can steer, pause, or kill agent runs as needed. The alternative (unidirectional messaging via Miniverse) was rejected because it lacked the control needed for production reliability.

## Tradeoffs Chosen

### JSON Response Format (Accepted)
ARCH responds in structured JSON because the orchestrator needs to parse responses programmatically. This adds overhead to ARCH's output but enables reliable downstream processing. We rejected free-form text responses because parsing would be brittle and error-prone.

### Sequential Task Execution by Default (Accepted)
Tasks can run in parallel, but the default is sequential execution. Parallel execution requires conflict zone analysis (Phase 2) and adds complexity. Sequential execution is safer and easier to reason about. The tradeoff is longer project completion time, which we accept for reliability.

### No Direct Inter-Agent Communication (Accepted)
BYTE and PIXEL do not communicate directly. All communication flows through ARCH. This eliminates coordination chaos but adds latency when agents need to sync. We accept this latency for the guarantee that ARCH always has full visibility.

### Mandatory Tests for Backend (Accepted)
BYTE must ship tests for backend work. This is non-negotiable. The tradeoff is increased implementation time, but the benefit is caught bugs before delivery. Frontend tests are encouraged but not mandatory because visual testing is harder to automate.

### WCAG 2.1 AA Compliance (Accepted)
PIXEL must ensure accessibility on all components. This is a hard requirement, not a nice-to-have. The tradeoff is additional design constraints, but accessible design benefits everyone.

## Non-Obvious Dependencies

### MEMORY.json Schema Version
The shared memory uses schema version 2.0. If you modify the schema, you must update the `schema_version` field and ensure backward compatibility. Older orchestrator versions may fail on newer schemas.

### Gateway Configuration and Agent Workspaces
The `gateway.yml` file defines agent workspaces relative to the project root. If you move the project, update the workspace paths. The orchestrator expects workspaces at `./workspaces/{coordinator,programmer,designer}`.

### Task Progress Files
Each agent maintains progress files in `workspaces/{agent}/progress/{task_id}.json`. These files are the source of truth for task status during execution. The orchestrator reads them to determine retry behavior.

### Model Fallback Chain
BYTE has a fallback model configured. If the primary model (Kimi K2.5) fails, the system automatically retries with DeepSeek. ARCH and PIXEL do not have fallbacks configured—they fail fast on model errors.

## Open Questions

### Conflict Zone Analysis Automation
Currently, ARCH performs conflict zone analysis manually. Phase 2 introduces a structured protocol, but the analysis itself is still agent-driven. Should we automate conflict detection based on file path patterns? This would reduce ARCH's cognitive load but might miss subtle conflicts.

### JUDGE Agent Authority
Phase 6 introduces JUDGE for quality review. The open question is whether JUDGE's verdict is final or whether ARCH can override. Current design gives JUDGE final say, but this may need adjustment based on real-world usage.

### Parallel Execution Limits
The orchestrator has `max_parallel_byte` and `max_parallel_pixel` settings. What are optimal values? Too many parallel runs may overwhelm the system; too few wastes time. We need empirical data from production runs.

### Long-Term Memory Persistence
Phase 4 introduces per-agent MEMORY.md files for institutional knowledge. How should this knowledge be validated? Outdated patterns could mislead agents on future projects.

### Dashboard Intervention Scope
Phase 7 adds human intervention controls to the dashboard. What interventions should require confirmation versus immediate execution? Killing a run should probably require confirmation; steering might not.
