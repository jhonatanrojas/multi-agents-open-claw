// Agent types
export interface AgentMeta {
  name: string;
  rol: string;
  model: string;
  emoji: string;
  color: string;
}

export type AgentStatus =
  | 'working'
  | 'thinking'
  | 'idle'
  | 'error'
  | 'offline'
  | 'delivered'
  | 'planned'
  | 'blocked'
  | 'paused'
  | 'sleeping'
  | 'speaking';

export interface Agent {
  status: AgentStatus;
  current_task?: string;
  last_seen?: string;
}

// Task types
export type TaskStatus = 'pending' | 'in_progress' | 'done' | 'error' | 'paused';

export type PreviewStatus = 'running' | 'stopped' | 'not_applicable';

export interface Task {
  id: string;
  title: string;
  status: TaskStatus;
  agent: string;
  phase?: string;
  skills?: string[];
  preview_url?: string;
  preview_status?: PreviewStatus;
  failure_count?: number;
  suggested_agent?: string;
  retryable?: boolean;
}

// Project types
export interface Project {
  id: string;
  name: string;
  description?: string;
  status: string;
  repo_path?: string;
  branch?: string;
  created_at?: string;
  artifact_index?: string;
  task_counts?: { open: number; done: number; total: number };
  tech_stack?: { backend?: string };
  runtime_status?: string;
  can_resume?: boolean;
  preview_url?: string;
  preview_status?: string;
}

// Phase types
export interface Phase {
  id: string;
  name: string;
  tasks?: string[];
}

// Log types
export interface LogEntry {
  ts: string;
  agent: string;
  msg: string;
}

// Blocker types
export interface Blocker {
  source: string;
  msg: string;
}

// Memory (full state)
export interface Memory {
  agents: Record<string, Agent>;
  tasks: Task[];
  project: Project | null;
  projects: Project[];
  log: LogEntry[];
  blockers: Blocker[];
  plan: { phases: Phase[] };
}

// Gateway event types
export type GatewayEventKind = 'thinking' | 'tool' | 'message';

export interface GatewayEvent {
  agent_id: string;
  session_key: string;
  event: string;
  kind: GatewayEventKind;
  payload: Record<string, unknown>;
  received_at: string;
  seq?: number;
  stateVersion?: number;
  summary?: string;
}

export interface GatewayStatus {
  connected: boolean;
  last_error?: string;
  last_event_at?: string;
  url?: string;
}

export interface GatewaySnapshot {
  status: GatewayStatus;
  events: GatewayEvent[];
}

// Miniverse types
export interface MiniverseAnchor {
  name: string;
  ox: number;
  oy: number;
  type: string;
}

export interface MiniverseProp {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  layer: 'above' | 'below';
  anchors: MiniverseAnchor[];
}

export interface MiniverseCitizen {
  agentId: string;
  name: string;
  sprite: string;
  position: string;
  type: string;
}

export interface MiniverseEvent {
  id: string;
  type: string;
  agent: string;
  message: string;
}

export interface MiniverseWorld {
  base_url?: string;
  api_url?: string;
  ui_url?: string;
  info?: Record<string, unknown>;
  agents?: Record<string, unknown> | { online?: number; total?: number };
  events?: MiniverseEvent[];
  observe?: Record<string, unknown>;
  // Grid data (when available)
  gridCols?: number;
  gridRows?: number;
  floor?: string[][];
  props?: MiniverseProp[];
  citizens?: MiniverseCitizen[];
}

export interface MiniverseSnapshot {
  repo?: {
    html_url?: string;
    name?: string;
    full_name?: string;
  };
  world: MiniverseWorld;
  links?: {
    repo?: string;
    api?: string;
    world?: string;
    ui?: string;
    docs?: string;
  };
  ui?: {
    url: string;
    final_url?: string;
    embeddable?: boolean;
    blocked_by?: string[];
    checked_at?: string;
    status?: string;
  };
  meta?: {
    source?: string;
    cached?: boolean;
    error?: string | null;
    fallback?: string;
    stale?: boolean;
  };
}

// Model types
export interface AvailableModel {
  qualified: string;
  provider: string;
  model_id: string;
  name?: string;
}

export interface ModelConfig {
  agents: Record<string, { model: string }>;
  available: AvailableModel[];
}

// File types
export interface FileItem {
  path: string;
  extension?: string;
  group?: string;
}

export interface FileRoot {
  path: string;
  label?: string;
  files: FileItem[];
}

export interface FileProject {
  id: string;
  name: string;
  status: string;
  roots: FileRoot[];
  total_files: number;
}

export interface FilesSnapshot {
  projects: FileProject[];
  files_produced?: string[];
  progress_files?: string[];
}

// Runtime types
export interface RuntimeProcess {
  pid: number;
  cmdline: string;
  role: 'primary' | 'lock' | 'duplicate';
  is_lock_pid: boolean;
  is_mem_pid: boolean;
  elapsed_sec: number;
}

export interface RuntimeSnapshot {
  primary_pid?: number;
  lockfile: { pid?: number };
  processes: RuntimeProcess[];
  duplicates: RuntimeProcess[];
  issues: string[];
  cleanup_available: boolean;
}

// Context types
export interface ContextSection {
  title: string;
  body: string;
}

export interface ContextSnapshot {
  path: string;
  modified_at?: string;
  mime: string;
  size: number;
  content: string;
  title: string;
}