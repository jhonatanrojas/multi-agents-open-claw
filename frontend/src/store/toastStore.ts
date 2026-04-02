import { create } from 'zustand';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: string;
  type: ToastType;
  message: string;
  duration?: number;
  action?: {
    label: string;
    onClick: () => void;
  };
}

interface ToastStore {
  toasts: Toast[];
  addToast: (toast: Omit<Toast, 'id'>) => void;
  removeToast: (id: string) => void;
  clearAll: () => void;
}

let toastIdCounter = 0;

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  addToast: (toast) => set((state) => ({
    toasts: [...state.toasts, { 
      ...toast, 
      id: `toast-${++toastIdCounter}-${Date.now()}`
    }]
  })),
  removeToast: (id) => set((state) => ({
    toasts: state.toasts.filter((t) => t.id !== id)
  })),
  clearAll: () => set({ toasts: [] }),
}));

// Convenience hooks
export function useToast() {
  const { addToast, removeToast, clearAll } = useToastStore();
  
  return {
    success: (message: string, duration = 3000) => 
      addToast({ type: 'success', message, duration }),
    error: (message: string, duration = 5000) => 
      addToast({ type: 'error', message, duration }),
    warning: (message: string, duration = 4000) => 
      addToast({ type: 'warning', message, duration }),
    info: (message: string, duration = 3000) => 
      addToast({ type: 'info', message, duration }),
    custom: addToast,
    remove: removeToast,
    clearAll,
  };
}
