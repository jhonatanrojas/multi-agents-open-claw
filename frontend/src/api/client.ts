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
    credentials: 'include', // Important: include cookies for auth (F0.1)
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-TOKEN': csrf,
      'X-Requested-With': 'XMLHttpRequest',
      ...options.headers,
    },
  });
  
  const data = await response.json().catch(() => ({}));
  
  if (!response.ok) {
    // Handle 401 Unauthorized - session may have expired
    if (response.status === 401) {
      // Trigger session check in auth store
      const authStore = (await import('@/store/authStore')).useAuthStore.getState();
      authStore.checkSession();
    }
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

export interface RepoLocal {
  name: string;
  path: string;
  url: string | null;
}

export interface RepoGitHub {
  name: string;
  full_name: string;
  url: string;
  ssh_url?: string;
  description: string;
  private: boolean;
  default_branch: string;
  updated_at?: string;
  is_local: boolean;
}

export interface ReposResponse {
  local: RepoLocal[];
  github: RepoGitHub[];
  has_github_token: boolean;
  github_error?: string;
  error?: string;
}

export async function fetchRepos(): Promise<ReposResponse> {
  return apiCall<ReposResponse>('/project/repos');
}

export interface StartProjectParams {
  name: string;
  description?: string;
  brief: string;
  repo_url?: string | null;
  repo_name?: string | null;
  branch?: string | null;
  allow_init_repo?: boolean;
}

export interface ExtendProjectParams {
  brief: string;
  project_id?: string | null;
  auto_resume?: boolean;
  source?: string;
}

export interface ExtendProjectResponse {
  ok: boolean;
  project_id: string;
  task_id: string;
  task_title: string;
  agent: string;
  project_status: string;
  auto_resumed: boolean;
  message: string;
  timestamp: string;
}

export async function startProject(params: StartProjectParams): Promise<{ message: string }> {
  return apiCall('/project/start', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function loadProject(projectId: string): Promise<{ status: string; message: string; ts: string }> {
  return apiCall('/project/load', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId }),
  });
}

export async function extendProject(params: ExtendProjectParams): Promise<ExtendProjectResponse> {
  return apiCall<ExtendProjectResponse>('/project/extend', {
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

export async function retryPlanning(): Promise<{
  status: string;
  message: string;
  project_id: string;
  timestamp: string;
}> {
  return apiCall('/project/retry-planning', {
    method: 'POST',
  });
}

export async function replyClarification(params: {
  reply: string;
  auto_resume?: boolean;
  source?: string;
}): Promise<{ message: string; auto_resumed: boolean; project_id: string }> {
  return apiCall('/project/clarification/reply', {
    method: 'POST',
    body: JSON.stringify(params),
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
  const runtime = await apiCall<RuntimeSnapshot>('/runtime/orchestrators');
  return { runtime };
}

export async function cleanupRuntime(mode = 'duplicates'): Promise<{ message: string }> {
  return apiCall('/runtime/orchestrators/cleanup', {
    method: 'POST',
    body: JSON.stringify({ mode, force: true }),
  });
}

// ============ AUTH ============

export interface LoginResponse {
  ok: boolean;
  message: string;
  expires_in: number;
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const response = await fetch(`${API}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
    credentials: 'include',
  });
  
  const data = await response.json().catch(() => ({}));
  
  if (!response.ok) {
    throw new Error(data.message || data.error || 'Login failed');
  }
  
  return data;
}

export async function logout(): Promise<void> {
  await fetch(`${API}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  });
}

export async function checkSession(): Promise<{ authenticated: boolean; reason?: string }> {
  const response = await fetch(`${API}/auth/session`, {
    credentials: 'include',
  });
  
  if (!response.ok) {
    return { authenticated: false };
  }
  
  return response.json();
}
