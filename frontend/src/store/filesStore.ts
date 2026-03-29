import { create } from 'zustand';
import type { FilesSnapshot } from '@/types';

export type { FilesSnapshot };

interface FilesState {
  snapshot: FilesSnapshot | null;
  isLoading: boolean;
  error: string | null;
  selectedPath: string | null;
  previewContent: string | null;
  previewLoading: boolean;
  previewError: string | null;
  scope: 'running' | 'finished' | 'all';
  
  setSnapshot: (snapshot: FilesSnapshot) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setSelectedPath: (path: string | null) => void;
  setPreviewContent: (content: string | null) => void;
  setPreviewLoading: (loading: boolean) => void;
  setPreviewError: (error: string | null) => void;
  setScope: (scope: 'running' | 'finished' | 'all') => void;
  clear: () => void;
}

export const useFilesStore = create<FilesState>((set) => ({
  snapshot: null,
  isLoading: false,
  error: null,
  selectedPath: null,
  previewContent: null,
  previewLoading: false,
  previewError: null,
  scope: 'running',
  
  setSnapshot: (snapshot) => set({ snapshot, error: null }),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),
  setSelectedPath: (selectedPath) => set({ selectedPath }),
  setPreviewContent: (previewContent) => set({ previewContent, previewError: null }),
  setPreviewLoading: (previewLoading) => set({ previewLoading }),
  setPreviewError: (previewError) => set({ previewError }),
  setScope: (scope) => set({ scope }),
  clear: () => set({
    snapshot: null,
    error: null,
    selectedPath: null,
    previewContent: null,
    previewError: null,
  }),
}));
