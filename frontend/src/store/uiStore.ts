import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { TabId } from '@/components/shared/Tabs';

interface UIState {
  // Project view mode
  projectViewMode: 'new' | 'view';
  setProjectViewMode: (mode: 'new' | 'view') => void;
  
  // Tabs
  activeTab: TabId;
  setActiveTab: (tab: TabId) => void;
  
  // File browser
  selectedFilePath: string | null;
  setSelectedFilePath: (path: string | null) => void;
  filesScope: 'running' | 'finished' | 'all';
  setFilesScope: (scope: 'running' | 'finished' | 'all') => void;
  
  // Projects
  projectsScope: 'active' | 'finished' | 'all';
  setProjectsScope: (scope: 'active' | 'finished' | 'all') => void;
  
  // Model selection (persisted)
  selectedModels: Record<string, string>;
  setSelectedModel: (agentId: string, model: string) => void;
  
  // Loading states
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
  
  // Reset
  reset: () => void;
}

const initialState = {
  projectViewMode: 'new' as 'new' | 'view',
  activeTab: 'tasks' as TabId,
  selectedFilePath: null,
  filesScope: 'running' as 'running' | 'finished' | 'all',
  projectsScope: 'active' as 'active' | 'finished' | 'all',
  selectedModels: {} as Record<string, string>,
  isLoading: false,
};

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      // Initial state
      ...initialState,
      
      // Project mode actions
      setProjectViewMode: (mode) => set({ projectViewMode: mode }),
      
      // Tab actions
      setActiveTab: (tab) => set({ activeTab: tab }),
      
      // File browser actions
      setSelectedFilePath: (path) => set({ selectedFilePath: path }),
      setFilesScope: (scope) => set({ filesScope: scope }),
      
      // Projects actions
      setProjectsScope: (scope) => set({ projectsScope: scope }),
      
      // Model selection
      setSelectedModel: (agentId, model) =>
        set((state) => ({
          selectedModels: { ...state.selectedModels, [agentId]: model },
        })),
      
      // Loading
      setIsLoading: (loading) => set({ isLoading: loading }),
      
      // Reset
      reset: () => set(initialState),
    }),
    {
      name: 'devsquad-ui-state',
      partialize: (state) => ({
        // Only persist these
        selectedModels: state.selectedModels,
        filesScope: state.filesScope,
        projectsScope: state.projectsScope,
      }),
    }
  )
);
