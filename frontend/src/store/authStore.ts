import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { API_BASE } from '@/constants';

interface AuthState {
  // Auth state
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  apiKey: string | null;
  sessionChecked: boolean;
  
  // Actions
  login: (apiKey: string) => Promise<boolean>;
  logout: () => Promise<void>;
  checkSession: () => Promise<boolean>;
  clearError: () => void;
}

const API = API_BASE;

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      // Initial state
      isAuthenticated: false,
      isLoading: false,
      error: null,
      apiKey: null,
      sessionChecked: false,
      
      // Login action
      login: async (apiKey: string) => {
        set({ isLoading: true, error: null });
        
        try {
          const response = await fetch(`${API}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey }),
            credentials: 'include', // Important: include cookies
          });
          
          const data = await response.json().catch(() => ({}));
          
          if (!response.ok) {
            throw new Error(data.error || data.message || 'Login failed');
          }
          
          if (data.ok) {
            set({ 
              isAuthenticated: true, 
              isLoading: false, 
              apiKey,
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
          apiKey: null, 
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
            // If session is invalid, clear the API key
            apiKey: isValid ? get().apiKey : null,
          });
          
          return isValid;
        } catch (e) {
          console.error('Session check error:', e);
          set({ 
            isAuthenticated: false, 
            sessionChecked: true,
            apiKey: null,
          });
          return false;
        }
      },
      
      // Clear error
      clearError: () => set({ error: null }),
    }),
    {
      name: 'devsquad-auth-state',
      partialize: (state) => ({
        // Only persist API key, not auth state (checked on load)
        apiKey: state.apiKey,
      }),
    }
  )
);
