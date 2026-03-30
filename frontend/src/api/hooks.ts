import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as api from './client';

// Query keys
export const queryKeys = {
  state: ['state'] as const,
  models: ['models'] as const,
  files: ['files'] as const,
  gateway: ['gateway'] as const,
  miniverse: ['miniverse'] as const,
  runtime: ['runtime'] as const,
  context: ['context'] as const,
  fileView: (path: string) => ['fileView', path] as const,
};

// ============ STATE ============

export function useState() {
  return useQuery({
    queryKey: queryKeys.state,
    queryFn: api.fetchState,
    refetchInterval: 5000, // Poll every 5s as fallback
    staleTime: 1000,
  });
}

// ============ MODELS ============

export function useModels() {
  return useQuery({
    queryKey: queryKeys.models,
    queryFn: api.fetchModels,
    staleTime: 60000, // 1 minute
  });
}

export function useUpdateModels() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: api.updateModels,
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.models, data.config);
    },
  });
}

export function useUpdateAgentModel() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: ({ agentId, model }: { agentId: string; model: string }) =>
      api.updateAgentModel(agentId, model),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.models, data.config);
    },
  });
}

export function useTestModel() {
  return useMutation({
    mutationFn: api.testModel,
  });
}

// ============ PROJECTS ============

export function useStartProject(options?: { 
  onSuccess?: (data: any) => void; 
  onError?: (error: any) => void;
}) {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: api.startProject,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.state });
      queryClient.invalidateQueries({ queryKey: queryKeys.files });
      options?.onSuccess?.(data);
    },
    onError: (error) => {
      options?.onError?.(error);
    },
  });
}

export function usePauseProject() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: api.pauseProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.state });
    },
  });
}

export function useDeleteProject() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: api.deleteProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.state });
      queryClient.invalidateQueries({ queryKey: queryKeys.files });
    },
  });
}

export function useResumeProject() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: api.resumeProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.state });
      queryClient.invalidateQueries({ queryKey: queryKeys.files });
    },
  });
}

// ============ FILES ============

export function useFiles() {
  return useQuery({
    queryKey: queryKeys.files,
    queryFn: api.fetchFiles,
    staleTime: 5000,
  });
}

export function useFileView(path: string | null) {
  return useQuery({
    queryKey: queryKeys.fileView(path || ''),
    queryFn: () => api.fetchFileView(path!),
    enabled: !!path,
    staleTime: 10000,
  });
}

// ============ GATEWAY ============

export function useGatewayEvents() {
  return useQuery({
    queryKey: queryKeys.gateway,
    queryFn: () => api.fetchGatewayEvents(200),
    staleTime: 1000,
  });
}

// ============ CONTEXT ============

export function useContext() {
  return useQuery({
    queryKey: queryKeys.context,
    queryFn: api.fetchContext,
    staleTime: 60000,
  });
}

export function useUpdateContext() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: api.updateContext,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.context });
    },
  });
}

// ============ STEER ============

export function useSendSteer() {
  return useMutation({
    mutationFn: ({ agentId, message }: { agentId: string; message: string }) =>
      api.sendSteer(agentId, message),
  });
}

// ============ MINIVERSE ============

export function useMiniverse(force = false) {
  return useQuery({
    queryKey: queryKeys.miniverse,
    queryFn: () => api.fetchMiniverse(force),
    staleTime: 60000, // 1 minute
    refetchInterval: 60000, // Refresh every minute
  });
}

// ============ RUNTIME ============

export function useRuntime() {
  return useQuery({
    queryKey: queryKeys.runtime,
    queryFn: api.fetchRuntime,
    staleTime: 2000,
    refetchInterval: 4000, // Poll every 4s
  });
}

export function useCleanupRuntime() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: api.cleanupRuntime,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.runtime });
    },
  });
}