# CONTRACTS.md — Interface Agreements

> **ARCH is the only agent authorized to modify this file.**  
> If BYTE and PIXEL disagree on an interface, this file wins.

---

## Purpose

This document defines the explicit interface agreements between BYTE (backend) and PIXEL (frontend). Both agents must read this file before producing or consuming any interface.

### Frontend Preview Contract

For frontend tasks, BYTE is responsible for bringing up a short-lived preview and publishing its URL in task memory.

- Preferred preview mechanism: `cloudflared tunnel --url http://localhost:3000`
- Fallbacks when a public IP is already available: `npx serve` or `npm run dev`
- BYTE must write the resulting URL to `MEMORY.json.preview_url`
- BYTE must set `MEMORY.json.preview_status` to `running` while the preview is live
- ARCH must include the preview URL in the final announce after JUDGE approves the task
- ARCH must tell BYTE to stop the preview after human confirmation
- JUDGE must verify that a frontend preview exists and is reachable before approving the task

### Output Boundary Contract

The system must keep design artifacts and project deliverables separate.

- Design artifacts live in the agent workspace under `workspaces/<agent>/<project>/design/` and are used for iteration, review, and handoff.
- Project deliverables live in the repository path for the project, such as `projects/<repo>/index.html`, `css/*.css`, and `js/*.js`.
- A task is not `done` unless the files listed for that task exist in the project repository, not only in the agent workspace.
- Workspace-only files are evidence of work in progress, not final delivery.
- JUDGE must validate repository paths, not just workspace artifacts, before approving frontend or design tasks.

---

## API Endpoint Schemas

### Task Progress API

PIXEL's dashboard components consume this endpoint to display task status.

`artifacts` in this API refers to project deliverables that exist in the repository path, not workspace-only design artifacts.

**Endpoint:** `GET /api/tasks`

**Response Schema:**
```json
{
  "tasks": [
    {
      "id": "string (T-NNN format)",
      "title": "string",
      "agent": "byte | pixel",
      "status": "pending | in_progress | done | error | needs_revision",
      "preview_url": "string | null",
      "preview_status": "running | stopped | not_applicable",
      "priority": "high | medium | low",
      "depends_on": ["string (task_id)"],
      "acceptance_criteria": ["string"],
      "artifacts": ["string (file path)"],
      "last_updated": "ISO-8601 timestamp"
    }
  ]
}
```

### Agent Status API

**Endpoint:** `GET /api/agents`

**Response Schema:**
```json
{
  "agents": {
    "arch": {
      "status": "idle | planning | coordinating | reviewing",
      "current_task": "string | null",
      "last_seen": "ISO-8601 timestamp"
    },
    "byte": {
      "status": "idle | working | error",
      "current_task": "string | null",
      "last_seen": "ISO-8601 timestamp"
    },
    "pixel": {
      "status": "idle | designing | error",
      "current_task": "string | null",
      "last_seen": "ISO-8601 timestamp"
    }
  }
}
```

### Health Check API

**Endpoint:** `GET /api/health/summary`

**Response Schema:**
```json
{
  "status": "healthy | degraded | down",
  "gateway": {
    "status": "ok | error",
    "error": "string | null"
  },
  "orchestrator": {
    "status": "running | paused | stopped",
    "pid": "number | null",
    "alive": "boolean"
  },
  "models": {
    "models": {}
  }
}
```

---

## TypeScript Types

### Shared Types

These types cross the frontend/backend boundary and must remain synchronized.

```typescript
// Task status enum - must match MEMORY.json task.status values
type TaskStatus = 
  | 'pending' 
  | 'in_progress' 
  | 'done' 
  | 'error' 
  | 'needs_revision';

// Agent identifiers
type AgentId = 'arch' | 'byte' | 'pixel' | 'judge';

// Priority levels - must match ARCH's task.priority values
type Priority = 'high' | 'medium' | 'low';

// Task interface for frontend display
interface Task {
  id: string;
  title: string;
  description: string;
  agent: AgentId;
  status: TaskStatus;
  preview_url: string | null;
  preview_status: 'running' | 'stopped' | 'not_applicable';
  priority: Priority;
  depends_on: string[];
  acceptance_criteria: string[];
  artifacts: string[];
  last_updated: string; // ISO-8601
}

// Agent status for dashboard
interface AgentStatus {
  status: 'idle' | 'working' | 'error' | 'planning' | 'designing';
  current_task: string | null;
  last_seen: string | null;
}

// Project status enum
type ProjectStatus = 
  | 'idle'
  | 'in_progress'
  | 'paused'
  | 'delivered'
  | 'architecture_v2';
```

---

## Component Prop Interfaces

PIXEL's components must accept these prop shapes when displaying BYTE's API responses.

### TaskCard Component

```typescript
interface TaskCardProps {
  task: Task;
  onSteer?: (taskId: string, message: string) => void;
  onPause?: (taskId: string) => void;
  onResume?: (taskId: string) => void;
  isSteerable: boolean;
  isPausable: boolean;
}
```

### AgentStatusCard Component

```typescript
interface AgentStatusCardProps {
  agentId: AgentId;
  status: AgentStatus;
  onSteer?: (message: string) => void;
  activeDuration?: number; // seconds
}
```

### ProjectOverview Component

```typescript
interface ProjectOverviewProps {
  project: {
    id: string;
    name: string;
    status: ProjectStatus;
    task_counts: {
      total: number;
      done: number;
      pending: number;
      in_progress: number;
      error: number;
    };
  };
}
```

---

## Shared Constants

### Status Codes

```typescript
// HTTP status codes for API responses
const API_STATUS = {
  OK: 200,
  CREATED: 201,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  NOT_FOUND: 404,
  INTERNAL_ERROR: 500,
} as const;

// WebSocket message types
const WS_MESSAGE_TYPES = {
  STATE_UPDATE: 'state_update',
  TASK_COMPLETE: 'task_complete',
  TASK_ERROR: 'task_error',
  AGENT_SPAWN: 'agent_spawn',
  AGENT_TERMINATE: 'agent_terminate',
} as const;
```

### Error Formats

BYTE's API error responses must follow this structure:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error description",
    "details": {}
  }
}
```

Standard error codes:
- `VALIDATION_ERROR` — Request validation failed
- `NOT_FOUND` — Resource not found
- `UNAUTHORIZED` — Authentication required
- `RATE_LIMITED` — Too many requests
- `MODEL_ERROR` — LLM API failure
- `INTERNAL_ERROR` — Unexpected server error

### Enums

```typescript
// Task types - must match ARCH's task.type values
enum TaskType {
  CODE = 'code',
  DESIGN = 'design',
  REVIEW = 'review',
  DOCUMENTATION = 'documentation',
}

// Review verdicts (for JUDGE)
enum ReviewVerdict {
  APPROVED = 'APPROVED',
  REJECTED = 'REJECTED',
}
```

---

## Change Log

| Date | Change | Authorized By |
|------|--------|---------------|
| 2026-03-28 | Initial creation | ARCH |

---

## Notes for Agents

**For BYTE:** When adding new API endpoints, update this file with the schema before implementing. PIXEL will need to build consuming components.

**For PIXEL:** When designing components that consume API data, verify the prop interfaces match what BYTE's endpoints return. If there's a mismatch, do NOT proceed—notify ARCH.

**For ARCH:** This file is your authority. When resolving interface disputes, the contract here wins. Update this file when requirements change, not during ad-hoc negotiations between BYTE and PIXEL.
