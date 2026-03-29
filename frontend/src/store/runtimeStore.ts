import { create } from 'zustand';
import type { RuntimeProcess } from '@/types';

export interface Orchestrator {
  id: string;
  name: string;
  status: string;
  started_at: string;
  tasks: number;
  pid?: number;
}

interface RuntimeState {
  orchestrators: Orchestrator[];
  processes: RuntimeProcess[];
  isLoading: boolean;
  error: string | null;
  
  setOrchestrators: (orchestrators: Orchestrator[]) => void;
  setProcesses: (processes: RuntimeProcess[]) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clear: () => void;
}

export const useRuntimeStore = create<RuntimeState>((set) => ({
  orchestrators: [],
  processes: [],
  isLoading: false,
  error: null,
  
  setOrchestrators: (orchestrators) => set({ orchestrators, error: null }),
  setProcesses: (processes) => set({ processes }),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),
  clear: () => set({ orchestrators: [], processes: [], error: null }),
}));
