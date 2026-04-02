import { create } from 'zustand';

interface ContextSection {
  id: string;
  title: string;
  content: string;
}

interface ContextState {
  content: string;
  sections: ContextSection[];
  isLoading: boolean;
  error: string | null;
  isEditing: boolean;
  editMessage: string;
  
  setContent: (content: string) => void;
  setSections: (sections: ContextSection[]) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setEditing: (editing: boolean) => void;
  setEditMessage: (message: string) => void;
  clear: () => void;
}

export const useContextStore = create<ContextState>((set) => ({
  content: '',
  sections: [],
  isLoading: false,
  error: null,
  isEditing: false,
  editMessage: '',
  
  setContent: (content) => set({ content }),
  setSections: (sections) => set({ sections }),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),
  setEditing: (isEditing) => set({ isEditing }),
  setEditMessage: (editMessage) => set({ editMessage }),
  clear: () => set({
    content: '',
    sections: [],
    error: null,
    isEditing: false,
    editMessage: '',
  }),
}));
