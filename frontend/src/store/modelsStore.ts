import { create } from 'zustand';
import type { ModelConfig, AvailableModel } from '@/types';

interface ModelsState {
  // Data
  config: ModelConfig | null;
  isLoading: boolean;
  error: string | null;
  
  // Actions
  setConfig: (config: ModelConfig) => void;
  updateAgentModel: (agentId: string, model: string) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

const initialState = {
  config: null as ModelConfig | null,
  isLoading: false,
  error: null as string | null,
};

export const useModelsStore = create<ModelsState>((set, get) => ({
  // Initial state
  ...initialState,
  
  // Actions
  setConfig: (config) => set({
    config,
    isLoading: false,
    error: null,
  }),
  
  updateAgentModel: (agentId, model) => {
    const current = get().config;
    if (!current) return;
    
    set({
      config: {
        ...current,
        agents: {
          ...current.agents,
          [agentId]: { model },
        },
      },
    });
  },
  
  setLoading: (loading) => set({ isLoading: loading }),
  
  setError: (error) => set({ error, isLoading: false }),
  
  reset: () => set(initialState),
}));

// Selector helpers
export const selectAgentModel = (agentId: string) => {
  return (state: ModelsState) => {
    return state.config?.agents?.[agentId]?.model || '';
  };
};

export const selectAvailableModels = (state: ModelsState): AvailableModel[] => {
  return state.config?.available || [];
};

export const selectAvailableModelsByProvider = (state: ModelsState) => {
  const models = state.config?.available || [];
  const grouped: Record<string, AvailableModel[]> = {};
  
  for (const model of models) {
    const provider = model.provider || 'unknown';
    if (!grouped[provider]) {
      grouped[provider] = [];
    }
    grouped[provider].push(model);
  }
  
  return grouped;
};