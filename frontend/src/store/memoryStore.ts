import { create } from 'zustand';
import type { 
  Memory, 
  Agent, 
  Task, 
  Project, 
  LogEntry, 
  Blocker, 
  Phase 
} from '@/types';

interface MemoryState {
  // Data
  agents: Record<string, Agent>;
  tasks: Task[];
  project: Project | null;
  projects: Project[];
  log: LogEntry[];
  blockers: Blocker[];
  plan: { phases: Phase[] };
  
  // Connection status
  isConnected: boolean;
  lastUpdated: string | null;
  
  // Actions
  setMemory: (memory: Memory) => void;
  updateAgent: (agentId: string, agent: Agent) => void;
  updateTask: (taskId: string, task: Partial<Task>) => void;
  addLogEntry: (entry: LogEntry) => void;
  setConnected: (connected: boolean) => void;
  reset: () => void;
}

const initialMemory: Memory = {
  agents: {},
  tasks: [],
  project: null,
  projects: [],
  log: [],
  blockers: [],
  plan: { phases: [] },
};

export const useMemoryStore = create<MemoryState>((set) => ({
  // Initial state
  ...initialMemory,
  isConnected: false,
  lastUpdated: null,
  
  // Actions
  setMemory: (memory) => set({
    ...memory,
    lastUpdated: new Date().toISOString(),
  }),
  
  updateAgent: (agentId, agent) => set((state) => ({
    agents: {
      ...state.agents,
      [agentId]: agent,
    },
    lastUpdated: new Date().toISOString(),
  })),
  
  updateTask: (taskId, taskUpdate) => set((state) => ({
    tasks: state.tasks.map((task) =>
      task.id === taskId ? { ...task, ...taskUpdate } : task
    ),
    lastUpdated: new Date().toISOString(),
  })),
  
  addLogEntry: (entry) => set((state) => ({
    log: [...state.log.slice(-199), entry], // Keep max 200 entries
    lastUpdated: new Date().toISOString(),
  })),
  
  setConnected: (connected) => set({ isConnected: connected }),
  
  reset: () => set({
    ...initialMemory,
    isConnected: false,
    lastUpdated: null,
  }),
}));