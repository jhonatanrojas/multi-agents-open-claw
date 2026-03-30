Run npm install after creating package.json. Verify node_modules exists.

---

## Phase 1 — Types and Constants

Create src/types/index.ts with TypeScript interfaces for every data
structure found in the audit. Required interfaces:

- AgentId: "arch" | "byte" | "pixel"
- AgentStatus: "working" | "thinking" | "speaking" | "idle" | "error"
  | "offline" | "delivered" | "planned" | "blocked" | "paused"
  | "sleeping"
- TaskStatus: "pending" | "in_progress" | "paused" | "done" | "error"
- Agent: { status, current_task, last_seen, last_updated }
- Task: { id, title, agent, status, phase, parallel_safe,
  parallel_safe_reason, scope_change_reason, last_updated,
  preview_url, preview_status, failure_count, retryable, skills,
  files, notes }
- Project: { id, name, description, status, repo_path, branch,
  tech_stack, created_at, can_resume, preview_url, preview_status,
  runtime_status, task_counts, artifact_index }
- Memory: { project, plan, tasks, agents, blockers, milestones,
  log, files_produced, plan_version, plan_history, projects }
- GatewayEvent: { agent_id, session_key, event, kind, seq,
  stateVersion, payload, received_at, ts, summary }
- ModelConfig: { available, agents }
- AvailableModel: { qualified, name, model_id, provider }
- LogEntry: { ts, agent, msg }
- Blocker: { source, msg }
- Phase: { id, name, tasks }

Create src/utils/index.ts with these functions extracted verbatim
from the Blade JS, converted to TypeScript:

- escapeHtml(value: unknown): string
- fmtTime(iso: string | null | undefined): string
- fmtDate(iso: string | null | undefined): string
- t(status: string): string  ← Spanish label lookup
- dedupeLog(log: LogEntry[]): LogEntry[]
- gatewayEventFingerprint(event: GatewayEvent): string
- dedupeGatewayEvents(events: GatewayEvent[]): GatewayEvent[]
- normalizePreviewStatus(status: unknown): string

Create src/constants/agents.ts with AGENT_META, STATUS_COLOR,
and TASK_COLOR objects extracted from the Blade source.

---

## Phase 2 — Global State Store

Create these Zustand slices in src/store/:

memory.ts
- State: memory (Memory | null), connected (boolean)
- Actions: setMemory, setConnected
- Selectors: selectTasks, selectAgents, selectProject, selectLog,
  selectBlockers, selectProjects

gateway.ts
- State: events (GatewayEvent[]), status (object)
- Actions: mergeEvent, setSnapshot, updateStatus
- Selectors: selectEventsList, selectChatEventsList,
  selectLatestChatByAgent

models.ts
- State: modelConfig (ModelConfig | null)
- Actions: setModelConfig

files.ts
- State: snapshot (object | null), loading, error, selectedPath,
  selectedPreview, selectedLoading, selectedError, scope
- Actions: setSnapshot, setSelected, setScope, clearSelected

copilot.ts
- State: contextSnapshot, contextSections, contextLoading,
  contextError, contextEditor, contextMessage, copilotTaskId
- Actions: syncContextSnapshot, beginEdit, cancelEdit,
  setMessage, setTaskId

miniverse.ts
- State: snapshot (object | null), loading, error
- Actions: setSnapshot, setLoading, setError

---

## Phase 3 — API Layer

Create one file per API domain in src/api/:

state.ts       → GET /api/state, GET /api/stream (SSE)
project.ts     → POST /api/project/start, /pause, /resume, /delete
agents.ts      → POST /api/agents/:id/steer
tasks.ts       → POST /api/tasks/:id/pause
context.ts     → GET /api/files/view (for CONTEXT.md),
                 PATCH /api/context
files.ts       → GET /api/files, GET /api/files/view,
                 GET /api/files/download
models.ts      → GET /api/models, PUT /api/models,
                 PUT /api/models/agent, POST /api/models/test
gateway.ts     → GET /api/gateway/events
runtime.ts     → GET /api/runtime/orchestrators,
                 POST /api/runtime/orchestrators/cleanup
miniverse.ts   → GET /api/miniverse

All fetch functions must:
- Read VITE_API_BASE from import.meta.env
- Include X-CSRF-TOKEN header from meta[name="csrf-token"]
- Include X-Requested-With: XMLHttpRequest
- Throw typed errors on non-ok responses
- Return typed responses

---

## Phase 4 — SSE and WebSocket Hooks

Create src/hooks/useStream.ts
Mirrors the startStream() function from Blade exactly:
- Connects to /api/stream via EventSource
- On message: calls store.setMemory with parsed JSON
- On open/error: calls store.setConnected
- Auto-reconnects on error
- Cleans up on unmount

Create src/hooks/useGatewayStream.ts
Mirrors startGatewayStream() from Blade exactly:
- Connects to VITE_GATEWAY_WS_URL via WebSocket
- Handles snapshot, event, and status message types
- Merges events into gateway store using dedupeGatewayEvents
- Reconnects after 4 seconds on close
- Cleans up on unmount

Create src/hooks/usePolling.ts
- Generic hook: takes fetch function + interval
- Calls fetch on mount and every N ms
- Cleans up on unmount

---

## Phase 5 — Shared UI Components

Create these components in src/components/:

Badge.tsx
- Props: state (AgentStatus | TaskStatus | string)
- Renders colored badge with dot using STATUS_COLOR or TASK_COLOR
- Exact visual match to Blade badge()

StatusDot.tsx
- Props: connected (boolean)
- Small colored dot for connection indicator

AgentAvatar.tsx
- Props: agentId (AgentId)
- Shows emoji + name from AGENT_META

ProgressBar.tsx
- Props: value (number 0-100), color? (string)
- Animated fill bar matching Blade .progress-fill

Chip.tsx
- Props: children, bg?, color?
- Small rounded label matching Blade .chip

LogFeed.tsx
- Props: log (LogEntry[]), maxLines? (default 80)
- Scrollable monospace feed, auto-scrolls to bottom
- Exact match to Blade renderLog()

EmptyState.tsx
- Props: message (string)
- Matches Blade .empty style

---

## Phase 6 — Feature Components (Blade Parity)

Build each feature section as a standalone component inside
its src/features/ folder. Each must be a pixel-accurate
functional migration of its Blade counterpart.

features/agents/AgentCard.tsx
- Exact migration of Blade renderAgents()
- Shows: emoji, name, role, status badge, model, latest gateway
  chat, current task, last seen, recent logs
- Reads from memory store and gateway store

features/agents/AgentsGrid.tsx
- 3-column responsive grid of AgentCard
- Collapses to 1 column on mobile

features/tasks/TaskRow.tsx
- Exact migration of Blade renderTasks()
- Shows: id, title, agent, status badge, preview badge,
  open preview link, pause button, resume button,
  failure count, skills

features/tasks/TasksPanel.tsx
- Full list of TaskRow with empty state

features/log/LogPanel.tsx
- Wraps LogFeed with the deduped memory log

features/gateway/GatewayEvent.tsx
- Renders a single gateway event card
- Exact migration of Blade renderGatewayEvent()

features/gateway/GatewayChatCard.tsx
- Renders a chat event card
- Exact migration of Blade renderGatewayChatCard()

features/gateway/GatewayTab.tsx
- Toolbar with connection status and event count
- List of GatewayEvent cards
- Reads from gateway store

features/files/FileRow.tsx
- Single file row with view and download buttons

features/files/FilePreview.tsx
- Dark code panel showing file content
- Matches Blade .file-preview

features/files/FilesTab.tsx
- Scope toolbar (running / finished / all)
- Two-column layout: file groups + FilePreview
- Calls fetchFilesSnapshot on mount

features/copilot/CopilotTab.tsx
- Exact migration of Blade renderCopilotTab()
- Left column: preview iframe + steer input
- Right column: CONTEXT.md section editor
- Reads from copilot store

features/miniverse/MiniverseWorld.tsx
- Canvas-based or CSS-grid pixel world
- Exact migration of Blade renderMiniverseWorld()
- Renders floor tiles, props, and citizen badges

features/miniverse/MiniverseTab.tsx
- Wraps MiniverseWorld with iframe fallback
- Mock local world when API is offline

features/models/ModelSelect.tsx
- Per-agent model dropdown with Test button
- Exact migration of Blade renderModelSelect()

features/models/ModelsPanel.tsx
- 3 ModelSelect rows + Save button

features/projects/ProjectItem.tsx
- Single project row with status badge and actions

features/projects/ProjectsPanel.tsx
- Scope toolbar + list of ProjectItem
- Matches Blade renderProjects()

features/projects/ProjectBar.tsx
- Active project progress bar
- Phase timeline
- Stat chips
- Matches Blade renderProject()

features/projects/StartProjectForm.tsx
- Exact migration of Blade start-form
- Fields: brief, repo_url, repo_name, branch, allow_init
- Saves models before submitting

---

## Phase 7 — Layout and Routing

Create src/App.tsx as the root component:

- Calls useStream() and useGatewayStream() at root level
- These hooks run for the entire app lifetime
- Renders the main layout

Create src/components/Layout.tsx:

Three-panel layout:

LEFT PANEL (280px fixed, scrollable)
- Header: "Dev Squad" title + connection dot
- SummaryBar (preview status + context status)
- AgentsGrid
- StartProjectForm

CENTER PANEL (flex: 1, scrollable)
- ProjectBar (when project exists)
- ProjectsPanel
- RuntimePanel
- ModelsPanel (collapsed by default)
- BlockersBar
- Tab navigation: Tasks | Log | Gateway | Files | Co-pilot | Miniverse
- Tab content panel

RIGHT PANEL (360px fixed, scrollable)
- Shows when a file is selected in Files tab: FilePreview
- Shows when Co-pilot tab is active: context editor shortcut
- Shows when Gateway tab is active: latest chat cards per agent
- Otherwise: empty

On screens < 1200px: collapse to single column, panels stack vertically
On screens < 768px: hide right panel, show as bottom sheet on demand

---

## Phase 8 — Wire Everything Together

In src/App.tsx, after rendering the layout:

1. Call useStream() — connects SSE, updates memory store
2. Call useGatewayStream() — connects WS, updates gateway store
3. Call usePolling(fetchModels, 60000) — refreshes model list
4. Call usePolling(fetchRuntimeSnapshot, 4000) — runtime polling
5. Call fetchInitialState() on mount — loads first state snapshot
6. Call fetchFilesSnapshot(true) on mount
7. Call fetchGatewayEventsSnapshot(true) on mount
8. Call fetchContextSnapshot(true) on mount
9. Call fetchMiniverseSnapshot(true) on mount

Verify the app builds without TypeScript errors:
  cd /var/www/openclaw-multi-agents/frontend && npm run build

Report the build output size and any warnings.

---

## Phase 9 — UX Pattern: Three-Panel Layout

This phase upgrades the layout from Phase 7 with the Blink-style
panel system. The panel boundaries are now permanent and resizable.

LEFT PANEL upgrades:
- Add a slim vertical activity indicator per agent
  (a colored bar that pulses when agent status is "working")
- Add collapse toggle — panel slides to 48px icon-only rail
- Persist collapse state in localStorage

CENTER PANEL upgrades:
- Tab bar becomes sticky at the top of the center panel
- Active tab content scrolls independently
- Add keyboard shortcuts: 1-6 map to each tab

RIGHT PANEL upgrades:
- When Files tab is active: right panel shows FilePreview always
- When Co-pilot tab is active: right panel shows steer input
  and context editor inline, not inside the tab
- When Gateway tab is active: right panel shows the three latest
  gateway chat cards, one per agent, updating in real time
- Add a resize handle between center and right panels
  (drag to adjust right panel width 240px–480px)
  Persist width in localStorage

---

## Phase 10 — UX Pattern: File Tree with Live Updates

Replace the current files list with a file tree component.

Create src/features/files/FileTree.tsx:

- Tree structure derived from files_produced[] in memory store
- Group files by directory path automatically
- Each directory node is collapsible
- New files added to files_produced[] animate in with a 300ms
  highlight flash (yellow background fading to transparent)
- Click any file → opens in right panel FilePreview
- Show file extension icon (use text labels: .py .ts .md .json .css)
- Show the agent who created the file (read from task.files mapping)
- Show timestamp of creation from task.last_updated

The file tree updates in real time from the SSE stream.
No manual refresh needed.

---

## Phase 11 — UX Pattern: Agent Activity Stream

Replace the current agent log rows with a live activity stream
component that shows what each agent is doing token by token.

Create src/features/agents/ActivityStream.tsx:

- Reads from gateway store, filtered by agent_id
- Shows the last gateway chat event content for each agent
- If event kind is "thinking": show content in italic gray
- If event kind is "tool": show tool name + truncated args
- If event kind is "message": show assistant text
- Text appears progressively using a typewriter effect
  (append characters at 20ms intervals from the full string)
- Maximum 4 lines visible per agent, older content fades out
- Add to each AgentCard below the model badge
- Replace the static agent-task div

---

## Phase 12 — UX Pattern: Inline Steer Controls

Add steer controls directly on AgentCard without modals.

Upgrade AgentCard.tsx:

- Add a "Steer" button below the activity stream
- On click: expands an inline textarea below the card
  (no modal, no tab switch, no page scroll)
- Textarea has a 140-character counter
- Send button calls POST /api/agents/:id/steer
- On success: textarea collapses with a green flash
- On error: textarea stays open with red border + error message
- The expand/collapse animates in 200ms

Remove the steer input from CopilotTab — it now lives on AgentCard.
Keep CopilotTab for task selection and CONTEXT.md editing only.

---

## Final Deliverable

When all 12 phases are complete:

1. Verify the production build succeeds:
   cd /var/www/openclaw-multi-agents/frontend && npm run build

2. Create /var/www/openclaw-multi-agents/frontend/MIGRATION.md with:
   - All API endpoints the frontend calls (with method and path)
   - All environment variables required
   - How to serve the built dist/ folder from Laravel
     (proxy /devsquad/* to the React app or serve dist/index.html)
   - Any behavior differences from the original Blade dashboard
   - Screenshot descriptions of each panel in plain text

3. Send the user this exact message:
   "✅ React frontend complete. 12 phases done.
   Build output in frontend/dist/.
   See MIGRATION.md for integration instructions."
