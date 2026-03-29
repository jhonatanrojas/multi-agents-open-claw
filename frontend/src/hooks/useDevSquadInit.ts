import { useEffect } from 'react';
import { useMemoryStore, useGatewayStore, useModelsStore, useRuntimeStore, useFilesStore, useContextStore, useUIStore, useMiniverseStore } from '@/store';
import { useSSE } from './useSSE';
import { useGatewayWS } from './useGatewayWS';
import { fetchModels, fetchGatewayEvents, fetchMiniverse, fetchRuntime, fetchFiles, fetchContext } from '@/api/client';

/**
 * Hook that initializes all data sources for the Dev Squad dashboard.
 * Combines SSE for state updates, WebSocket for gateway events,
 * and periodic polling for supplementary data.
 */
export function useDevSquadInit() {
  const activeTab = useUIStore((state) => state.activeTab);
  
  // Connect SSE and WebSocket
  useSSE({ enabled: true });
  useGatewayWS({ enabled: true });
  
  // Fetch initial state on mount
  useEffect(() => {
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
    Promise.all([loadModels(), loadGatewayEvents(), loadFiles(), loadContext()]);
    
    // Refresh models every minute
    const modelsInterval = setInterval(loadModels, 60000);
    
    return () => clearInterval(modelsInterval);
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