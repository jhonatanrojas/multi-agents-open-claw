import { useEffect, useRef } from 'react';
import { useMemoryStore, useGatewayStore, useModelsStore, useRuntimeStore, useFilesStore, useContextStore, useUIStore, useMiniverseStore } from '@/store';
import { useSSE } from './useSSE';
import { useGatewayWS } from './useGatewayWS';
import { fetchModels, fetchGatewayEvents, fetchMiniverse, fetchRuntime, fetchFiles, fetchContext, fetchState } from '@/api/client';

import { useAuthStore } from '@/store/authStore';

interface UseDevSquadInitOptions {
  enabled?: boolean;
}

/**
 * Hook that initializes all data sources for the Dev Squad dashboard.
 * Combines SSE for state updates, WebSocket for gateway events,
 * and periodic polling for supplementary data.
 */
export function useDevSquadInit(options: UseDevSquadInitOptions = {}) {
  const { enabled = true } = options;
  const activeTab = useUIStore((state) => state.activeTab);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  
  // Only initialize if enabled and authenticated
  const shouldInit = enabled && isAuthenticated;
  
  // Connect SSE and WebSocket
  useSSE({ enabled: shouldInit });
  useGatewayWS({ enabled: shouldInit });
  
  // Track if we've already initialized to prevent double-fetch
  const hasInitialized = useRef(false);
  
  // Fetch initial state on mount only
  useEffect(() => {
    // Only run once on mount - auth changes are handled by SSE reconnect
    if (hasInitialized.current) return;
    
    hasInitialized.current = true;
    
    // Fetch initial state (projects, tasks, agents, etc.)
    const loadState = async () => {
      try {
        const state = await fetchState();
        useMemoryStore.getState().setMemory(state);
        console.log('[DevSquad] Initial state loaded:', {
          project: state.project?.name,
          projects: state.projects?.length,
          tasks: state.tasks?.length,
        });
      } catch (e) {
        // Silently ignore auth errors (user not logged in yet)
        if (e instanceof Error && e.message.includes('401')) {
          console.log('[DevSquad] Not authenticated, skipping state load');
          hasInitialized.current = false; // Allow retry after auth
          return;
        }
        console.error('[DevSquad] Failed to load initial state:', e);
      }
    };
    
    // Fetch models on mount
    const loadModels = async () => {
      try {
        useModelsStore.getState().setLoading(true);
        const config = await fetchModels();
        useModelsStore.getState().setConfig(config);
      } catch (e) {
        useModelsStore.getState().setError(String(e));
      }
    };
    
    // Fetch gateway events on mount
    const loadGatewayEvents = async () => {
      try {
        const snapshot = await fetchGatewayEvents(200);
        useGatewayStore.getState().setSnapshot(snapshot);
      } catch (e) {
        console.error('Failed to load gateway events:', e);
      }
    };
    
    // Fetch files on mount
    const loadFiles = async () => {
      try {
        useFilesStore.getState().setLoading(true);
        const snapshot = await fetchFiles();
        useFilesStore.getState().setSnapshot(snapshot);
      } catch (e) {
        useFilesStore.getState().setError(String(e));
      } finally {
        useFilesStore.getState().setLoading(false);
      }
    };
    
    // Fetch context on mount
    const loadContext = async () => {
      try {
        useContextStore.getState().setLoading(true);
        const { file } = await fetchContext();
        useContextStore.getState().setContent(file.content);
      } catch (e) {
        useContextStore.getState().setError(String(e));
      }
    };
    
    // Run all initial fetches
    loadState(); // Load state first
    Promise.all([loadModels(), loadGatewayEvents(), loadFiles(), loadContext()]);
    
    // Refresh models every minute
    const modelsInterval = setInterval(loadModels, 60000);
    
    // Refresh state every 3 seconds as backup to SSE
    const stateInterval = setInterval(loadState, 3000);
    
    return () => {
      clearInterval(modelsInterval);
      clearInterval(stateInterval);
    };
  // Empty dependency array - only run on mount
  // Auth state changes are handled by SSE/WebSocket reconnection logic
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  
  // Fetch miniverse when tab is active
  useEffect(() => {
    if (activeTab !== 'miniverse') return;
    
    const loadMiniverse = async () => {
      try {
        const snapshot = await fetchMiniverse();
        useMiniverseStore.getState().setSnapshot(snapshot);
      } catch (e) {
        useMiniverseStore.getState().setError(String(e));
      }
    };
    
    loadMiniverse();
    
    // Refresh miniverse every minute while tab is active
    const interval = setInterval(loadMiniverse, 60000);
    return () => clearInterval(interval);
  }, [activeTab]);
  
  // Fetch runtime periodically
  useEffect(() => {
    const loadRuntime = async () => {
      try {
        const { runtime } = await fetchRuntime();
        // Map processes to orchestrators format
        const orchestrators = (runtime?.processes || []).map((p, i) => ({
          id: `orch-${i}`,
          name: p.cmdline?.[0] || 'Runtime Process',
          status: p.role === 'primary' ? 'running' : 'paused',
          started_at: new Date(Date.now() - p.elapsed_sec * 1000).toISOString(),
          tasks: 0,
          pid: p.pid,
        }));
        useRuntimeStore.getState().setOrchestrators(orchestrators);
        useRuntimeStore.getState().setProcesses(runtime?.processes || []);
      } catch (e) {
        console.error('Failed to load runtime:', e);
      }
    };
    
    loadRuntime();
    
    // Refresh runtime every 4 seconds
    const interval = setInterval(loadRuntime, 4000);
    return () => clearInterval(interval);
  }, []);
  
  return {
    isConnected: useMemoryStore((state) => state.isConnected),
    gatewayConnected: useGatewayStore((state) => state.status.connected),
  };
}
