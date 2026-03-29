import { API_BASE } from '@/constants';
import type { 
  Memory, 
  ModelConfig, 
  FilesSnapshot, 
  GatewaySnapshot, 
  MiniverseSnapshot,
  RuntimeSnapshot,
  ContextSnapshot,
} from '@/types';

const API = API_BASE;

// Helper for API calls
async function apiCall<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
  
  const response = await fetch(`${API}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-TOKEN': csrf,
      'X-Requested-With': 'XMLHttpRequest',
      ...options.headers,
    },
  });
  
  const data = await response.json().catch(() => ({}));
  
  if (!response.ok) {
    throw new Error(data.error || data.message || `HTTP ${response.status}`);
  }
  
  return data;
}

// ============ STATE ============

export async function fetchState(): Promise<Memory> {
  return apiCall<Memory>('/state');
}

// ============ MODELS ============

export async function fetchModels(): Promise<ModelConfig> {
  return apiCall<ModelConfig>('/models');
}

export async function updateModels(models: Record<string, string>): Promise<{ config: ModelConfig }> {
  return apiCall<{ config: ModelConfig }>('/models', {
    method: 'PUT',
    body: JSON.stringify(models),
  });
}

export async function updateAgentModel(
  agentId: string, 
  model: string
): Promise<{ config: ModelConfig }> {
  return apiCall<{ config: ModelConfig }>('/models/agent', {
    method: 'PUT',
    body: JSON.stringify({ agent_id: agentId, model }),
  });
}

export async function testModel(model: string): Promise<{
  ok: boolean;
  message: string;
  elapsed_ms: number;
  status?: string;
}> {
  return apiCall('/models/test', {
    method: 'POST',
    body: JSON.stringify({ model }),
  });
}

// ============ PROJECTS ============

export interface StartProjectParams {
  brief: string;
  repo_url?: string | null;
  repo_name?: string | null;
  branch?: string | null;
  allow_init_repo?: boolean;
}

export async function startProject(params: StartProjectParams): Promise<{ message: string }> {
  return apiCall('/project/start', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function pauseProject(params?: {
  task_id?: string;
  pause_running?: boolean;
  reason?: string;
}): Promise<{ message: string }> {
  return apiCall('/project/pause', {
    method: 'POST',
    body: JSON.stringify(params || { pause_running: true }),
  });
}

export async function deleteProject(projectId?: string): Promise<{ message: string }> {
  return apiCall('/project/delete', {
    method: 'POST',
    body: JSON.stringify(projectId ? { project_id: projectId } : {}),
  });
}

export async function resumeProject(params?: {
  task_id?: string;
  resume_all_failed?: boolean;
}): Promise<{ message: string }> {
  return apiCall('/project/resume', {
    method: 'POST',
    body: JSON.stringify(params || { resume_all_failed: true }),
  });
}

// ============ FILES ============

export async function fetchFiles(): Promise<FilesSnapshot> {
  return apiCall<FilesSnapshot>('/files');
}

export interface FileViewResponse {
  file: {
    path: string;
    name: string;
    content: string;
    mime: string;
    size: number;
    truncated?: boolean;
    modified_at?: string;
  };
}

export async function fetchFileView(path: string): Promise<FileViewResponse> {
  const url = `/files/view?path=${encodeURIComponent(path)}`;
  return apiCall<FileViewResponse>(url);
}

// ============ GATEWAY ============

export async function fetchGatewayEvents(limit = 200): Promise<GatewaySnapshot> {
  return apiCall<GatewaySnapshot>(`/gateway/events?limit=${limit}`);
}

// ============ CONTEXT ============

export async function fetchContext(): Promise<{ file: ContextSnapshot }> {
  const url = `/files/view?path=${encodeURIComponent('/var/www/openclaw-multi-agents/shared/CONTEXT.md')}`;
  return apiCall<{ file: ContextSnapshot }>(url);
}

export async function updateContext(params: {
  section: string;
  content: string;
  reason: string;
}): Promise<{ 
  message: string; 
  plan_version: number;
}> {
  return apiCall('/context', {
    method: 'PATCH',
    body: JSON.stringify(params),
  });
}

// ============ STEER ============

export async function sendSteer(
  agentId: string, 
  message: string
): Promise<{ message: string }> {
  return apiCall(`/agents/${encodeURIComponent(agentId)}/steer`, {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
}

// ============ MINIVERSE ============

export async function fetchMiniverse(force = false): Promise<MiniverseSnapshot> {
  return apiCall<MiniverseSnapshot>(`/miniverse${force ? '?force=1' : ''}`);
}

// ============ RUNTIME ============

export async function fetchRuntime(): Promise<{ runtime: RuntimeSnapshot }> {
  return apiCall<{ runtime: RuntimeSnapshot }>('/runtime/orchestrators');
}

export async function cleanupRuntime(mode = 'duplicates'): Promise<{ message: string }> {
  return apiCall('/runtime/orchestrators/cleanup', {
    method: 'POST',
    body: JSON.stringify({ mode, force: true }),
  });
}