# Dev Squad — Architecture Upgrade v2

## Who This Prompt Is For

This prompt is for you, the OpenClaw main agent.
You are not ARCH. You are the user's personal assistant
and your mission in this session is to build and fully
deploy the Dev Squad multi-agent system version 2.

Do not delegate this work to sub-agents yet. You execute
each phase directly — you create the files, update the
configurations, verify they exist. Only in Phase 6 will
you spawn a sub-agent (JUDGE), and in Phase 7 you will
spawn PIXEL for the dashboard. Everything else is your
work to do directly.

---

## Before You Start

Read these files in order and confirm you understand them
before touching anything:

1. `~/.openclaw/workspace/AGENTS.md` — your own rules
2. `dev-squad/shared/MEMORY.json` — current project state
3. `dev-squad/workspaces/coordinator/SOUL.md` — ARCH identity
4. `dev-squad/workspaces/programmer/SOUL.md` — BYTE identity
5. `dev-squad/workspaces/designer/SOUL.md` — PIXEL identity
6. `dev-squad/config/gateway.yml` — gateway configuration

If any of these files does not exist, stop and report it
before continuing. Do not assume their contents.

When you finish reading them, write in your response:
"Context loaded. Summary: [two lines of what you found]"
and wait for user confirmation before starting Phase 1.

---

## Execution Rules (apply to all phases)

- Execute → Verify → Report. No exceptions.
- Verify that every file you create exists and has
  non-empty content before marking it as done.
- After completing each phase, write an entry in
  `~/.openclaw/workspace/MEMORY.md` with this format:
  `[UPGRADE Phase N — date] Completed. Files: list.`
- If you encounter a blocker, describe it precisely
  and wait for user instruction. Do not attempt to
  resolve ambiguous blockers on your own.
- Maximum 3 attempts per failing step. On the third
  failed attempt, report and wait.
- End each phase with the exact message:
  `✅ PHASE [N] COMPLETE` followed by the list of
  files created or modified.

---

## Phase 1 — Shared Narrative Context

**Goal:** create the natural-language sources of truth
that all agents will read before every task.

**Step 1.1 — Create `dev-squad/shared/CONTEXT.md`**

This file is prose, not JSON or bullet points for the
decisions section. It must contain these sections:

- What is being built and why
- Architectural decisions already made with the
  reasoning behind each one (write in prose — the
  reasoning matters as much as the decision itself)
- Tradeoffs chosen and what was explicitly ruled out
- Non-obvious dependencies between modules
- Open questions that have not been resolved yet

Write it as if a senior engineer is onboarding a new
team member who has never seen the project.

**Step 1.2 — Create `dev-squad/shared/CONTRACTS.md`**

This file defines the explicit interface agreements
between BYTE and PIXEL. It must include:

- All API endpoint schemas that PIXEL's components
  will consume
- All TypeScript types or data shapes that cross
  the frontend/backend boundary
- Component prop interfaces that BYTE's API responses
  must match
- Shared constants (status codes, enums, error formats)

Write this rule at the top of the file:
"ARCH is the only agent authorized to modify this file.
If BYTE and PIXEL disagree on an interface,
this file wins."

**Step 1.3 — Update SOUL.md for BYTE and PIXEL**

Add this instruction at the top of each agent's task
execution protocol:

> Before starting any task, read `shared/CONTEXT.md`
> and `shared/CONTRACTS.md`. If your task requires
> producing or consuming an interface not defined in
> CONTRACTS.md, stop and notify ARCH before proceeding.

**Verification:**

- `shared/CONTEXT.md` exists with content in all
  sections
- `shared/CONTRACTS.md` exists with the authority
  rule at the top
- BYTE and PIXEL's SOUL.md files explicitly reference
  both files

---

## Phase 2 — Conflict Zone Analysis Before Parallel Work

**Goal:** prevent BYTE and PIXEL from producing
conflicting artifacts when working in parallel.

**Step 2.1 — Update ARCH's SOUL.md**

Add a section `## Pre-Spawn Conflict Check` with
this rule:

Before spawning two tasks in parallel, ARCH must
perform a conflict zone analysis. A conflict zone is
any file path, API endpoint, TypeScript type, or CSS
token that both tasks will touch.

The analysis has three outcomes:

- No overlap → spawn both in parallel
- Overlap resolvable by contract → write the contract
  to CONTRACTS.md first, then spawn both
- Overlap requiring sequential execution → spawn in
  order, never in parallel

**Step 2.2 — Update task schema in MEMORY.json**

Add the `parallel_safe` boolean field to every existing
task object in `MEMORY.json`. Evaluate each task using
the conflict criterion and assign the correct value.
Document the reasoning in a `parallel_safe_reason`
field for each task.

**Verification:**

- ARCH's SOUL.md contains the `## Pre-Spawn Conflict
Check` section
- Every task in MEMORY.json has both `parallel_safe`
  and `parallel_safe_reason` fields set

---

## Phase 3 — ARCH Proactive Heartbeat

**Goal:** replace passive timeout-waiting with active
stall detection every 60 seconds.

**Step 3.1 — Create
`dev-squad/workspaces/coordinator/HEARTBEAT.md`**

OpenClaw injects this file automatically into every
coordinator session. It must contain exactly this
Standing Order:

```
## Program: Sub-Agent Health Monitor

**Authority:** Read sub-agent logs, send steer messages,
kill and re-spawn blocked runs.
**Trigger:** Every heartbeat cycle (~60 seconds)
**Approval gate:** None for steer messages. Human
approval required before killing a run active for
less than 120 seconds.

### Checks to perform each cycle

1. Read inbox for any messages prefixed with QUESTION:
2. Scan MEMORY.json for tasks in in_progress with
   last_updated older than 90 seconds
3. If a stalled task is found, read the last 15 lines
   of that sub-agent's log before acting

### Response Matrix

| Condition                          | Action                                       |
|------------------------------------|----------------------------------------------|
| QUESTION: received                 | Answer via sessions_send, log in MEMORY.json |
| Stalled < 90s                      | No action                                    |
| Stalled 90–180s                    | sessions_steer with hint or clarification    |
| Stalled > 180s, tool loop          | Kill run, decompose task, re-spawn           |
| Stalled > 180s, unknown cause      | Read full log, diagnose, decide              |
| Failed announce received           | Read log, update MEMORY.json, re-plan        |

### Escalation

If the same task fails or stalls 3 times: log to
blockers[] and pause spawning new tasks until the
blocker is resolved or the task is re-scoped. Never
escalate to the human if the blocker can be resolved
by task decomposition.
```

**Step 3.2 — Add `last_updated` rule to ARCH's protocol**

In ARCH's SOUL.md, inside the MEMORY.json update
section, add:

> Every task state transition (pending → in_progress
> → done/error) must include updating the `last_updated`
> field with the current UTC timestamp. This field is
> what the heartbeat monitor uses to detect stalls.

**Verification:**

- `workspaces/coordinator/HEARTBEAT.md` exists with
  the complete Standing Order
- ARCH's SOUL.md references `last_updated` in its
  task state transition protocol

---

## Phase 4 — Per-Agent Long-Term Memory

**Goal:** make BYTE and PIXEL accumulate institutional
knowledge across projects, not only within a single one.

**Step 4.1 — Create
`dev-squad/workspaces/programmer/MEMORY.md`**

Initialize it with these sections, each with a one-line
description of its purpose but otherwise empty:

- `## Architectural Patterns` — code patterns used
  and confirmed working
- `## Known Pitfalls` — mistakes made in previous
  tasks and how they were resolved
- `## Tech Stack Preferences` — library versions,
  configurations, and setups that have worked well
- `## Open Questions` — technical decisions that are
  still uncertain

**Step 4.2 — Create
`dev-squad/workspaces/designer/MEMORY.md`**

Initialize it with these sections:

- `## Design System` — tokens, component patterns,
  and conventions established for reuse
- `## Accessibility Patterns` — proven WCAG-compliant
  implementation patterns
- `## Component Library` — components already built
  that can be reused in future projects
- `## Brand Decisions` — design decisions that have
  been approved and must be consistent across projects

**Step 4.3 — Add two rules to BYTE and PIXEL**

In the SOUL.md of each agent, at the top of the task
execution section:

Rule 1: At the start of every task, read your own
MEMORY.md before reading anything else.

Rule 2: At the end of every successfully completed
task, append a brief note to the relevant section of
your MEMORY.md. One to three sentences maximum. If
nothing new was learned, write nothing.

**Verification:**

- Both MEMORY.md files exist with all their sections
- BYTE and PIXEL's SOUL.md files have both new rules
  at the top of their execution protocol

---

## Phase 5 — Adaptive Plan with Versioning

**Goal:** allow the plan to evolve as technical reality
emerges, instead of treating the initial plan as
immutable.

**Step 5.1 — Evolve MEMORY.json schema**

Add these fields at the root level:

- `plan_version`: integer, initialize at 1
- `plan_history`: empty array, with this entry schema:
  `{ version, timestamp, changed_tasks[], reason }`

Add this optional field to every existing task object:

- `scope_change_reason`: string, empty by default

**Step 5.2 — Add Phase Retrospective Protocol to ARCH**

In ARCH's SOUL.md, add the section
`## Phase Retrospective Protocol`:

After every phase of tasks completes (not every task —
every phase), before spawning the next phase:

1. Read all files produced in the completed phase
2. Compare against the original task descriptions
3. Identify any discoveries that affect pending tasks
4. If a pending task needs to change: update it,
   increment `plan_version`, log the change in
   `plan_history[]` with the reason, and fill
   `scope_change_reason` on the task object
5. Only then spawn the next phase

**Verification:**

- MEMORY.json has `plan_version` and `plan_history`
  at the root level
- Every task object has the `scope_change_reason` field
- ARCH's SOUL.md has the `## Phase Retrospective
Protocol` section

---

## Phase 6 — JUDGE Agent (Quality Reviewer)

**Goal:** separate planning authority from approval
authority. ARCH must not be the sole reviewer of work
that ARCH planned.

**Step 6.1 — Create
`dev-squad/workspaces/reviewer/SOUL.md`**

This is JUDGE's SOUL.md. It must contain these
constraints as a permanent, immutable part of its
identity:

- Read-only access to all files. JUDGE never writes
  to code or design files under any circumstance.
- JUDGE never proposes alternative implementations.
  It only evaluates against defined criteria.
- JUDGE has no model of how the solution "should"
  look — only whether it meets the acceptance
  criteria stated in the task.
- JUDGE's verdict is binary:
  `APPROVED` or `REJECTED: <specific reason>`.
  No partial approvals. No conditional approvals.

JUDGE evaluates four dimensions for every deliverable:

1. Does the output meet every acceptance criterion
   listed in the task?
2. Are BYTE's implementations consistent with PIXEL's
   component interfaces, and vice versa?
3. Are there any direct contradictions with
   CONTRACTS.md?
4. Are there any obvious defects — missing referenced
   files, broken imports, empty implementations?

Recommended model for JUDGE: a lighter model than ARCH.
JUDGE needs precision, not deep reasoning.

**Step 6.2 — Add JUDGE to `config/gateway.yml`**

Add JUDGE as the fourth agent in the agents list, with
its workspace pointing to
`dev-squad/workspaces/reviewer`.

**Step 6.3 — Add Mandatory Review Gate to ARCH's
SOUL.md**

Add the section `## Mandatory Review Gate`:

Before marking any task as `done` in MEMORY.json,
ARCH must spawn JUDGE as a one-shot sub-agent with:

- The complete task description
- The acceptance criteria
- The file paths of all produced artifacts

Only update the task to `done` after receiving
`APPROVED` from JUDGE.

If JUDGE returns `REJECTED: <reason>`:

- Update the task status to `needs_revision`
- Notify the responsible agent with the exact
  rejection reason
- Re-spawn the task with the rejection context
  included in the new task prompt

**Verification:**

- `workspaces/reviewer/SOUL.md` exists with all
  constraints and evaluation dimensions
- JUDGE is registered in `config/gateway.yml`
- ARCH's SOUL.md has the `## Mandatory Review Gate`
  section with the full protocol

---

## Phase 7 — Dashboard as Co-Pilot Surface

**Goal:** give the human operator active intervention
controls, not just passive observation.

**Step 7.1 — Document three new endpoints**

In `dev-squad/dashboard_api.py`, document these three
endpoints with full docstrings and design comments.
Do not implement the frontend yet — that is PIXEL's job:

- `POST /api/agents/{agent_id}/steer` — sends a steer
  message to an active sub-agent session
- `POST /api/tasks/{task_id}/pause` — flags a task as
  paused in MEMORY.json for ARCH to detect on its
  next heartbeat cycle
- `PATCH /api/context` — updates a specific section
  of CONTEXT.md and logs the change in `plan_history[]`

**Step 7.2 — Spawn PIXEL for the intervention UI**

Spawn PIXEL as a one-shot sub-agent with this task:

"Build the intervention UI components for the dashboard.
Read CONTRACTS.md and CONTEXT.md before writing any
code. Build these three components:

1. A steer input field that appears alongside each
   active agent card, wired to
   POST /api/agents/{agent_id}/steer

2. A pause/resume toggle on each in_progress task row,
   wired to POST /api/tasks/{task_id}/pause

3. An inline CONTEXT.md editor with a save button,
   wired to PATCH /api/context

Each component must handle loading and error states.
Reply with DONE: when finished, listing all files
produced."

Wait for PIXEL's announce before continuing.

**Verification:**

- The three endpoints are documented in
  `dashboard_api.py` with docstrings
- PIXEL completed its task and components exist
  under `dev-squad/dashboard/`

---

## Final Deliverable

When all seven phases are complete:

1. Create `dev-squad/UPGRADE_SUMMARY.md` containing:
   - What changed in each phase
   - What files were created or modified
   - New capabilities the system now has
   - Known limitations and recommended next steps

2. Update `dev-squad/shared/MEMORY.json`:
   - Set `project.status` to `"architecture_v2"`
   - Add a final entry to `milestones[]`:
     `"Architecture v2 completed by main agent"`

3. Send the user this exact message:
   "✅ Dev Squad Architecture v2 complete.
   See UPGRADE_SUMMARY.md for the full details."
