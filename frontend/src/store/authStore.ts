import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { API_BASE } from '@/constants';

interface AuthState {
  // Auth state
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  sessionChecked: boolean;

  // Actions
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
  checkSession: () => Promise<boolean>;
  clearError: () => void;
}

const API = API_BASE;

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      // Initial state
      isAuthenticated: false,
      isLoading: false,
      error: null,
      sessionChecked: false,

      // Login action - now uses username/password
      login: async (username: string, password: string) => {
        set({ isLoading: true, error: null });
        try {
          const response = await fetch(`${API}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
            credentials: 'include',
          });

          const data = await response.json().catch(() => ({}));

          if (!response.ok) {
            throw new Error(data.error || data.message || 'Login failed');
          }

          if (data.ok) {
            set({
              isAuthenticated: true,
              isLoading: false,
              error: null,
              sessionChecked: true,
            });
            return true;
          } else {
            throw new Error(data.message || 'Login failed');
          }
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : 'Unknown error';
          set({
            isAuthenticated: false,
            isLoading: false,
            error: errorMessage,
            sessionChecked: true,
          });
          return false;
        }
      },

      // Logout action
      logout: async () => {
        try {
          await fetch(`${API}/auth/logout`, {
            method: 'POST',
            credentials: 'include',
          });
        } catch (e) {
          console.error('Logout error:', e);
        }
        set({
          isAuthenticated: false,
          error: null,
          sessionChecked: true,
        });
      },

      // Check session validity
      checkSession: async () => {
        try {
          const response = await fetch(`${API}/auth/session`, {
            credentials: 'include',
          });

          const data = await response.json().catch(() => ({ authenticated: false }));
          const isValid = data.authenticated === true;

          set({
            isAuthenticated: isValid,
            sessionChecked: true,
          });

          return isValid;
        } catch (e) {
          console.error('Session check error:', e);
          set({
            isAuthenticated: false,
            sessionChecked: true,
          });
          return false;
        }
      },

      // Clear error
      clearError: () => set({ error: null }),
    }),
    {
      name: 'devsquad-auth-state',
      // No persist anything - session is cookie-based
      partialize: () => ({}),
    }
  )
);
