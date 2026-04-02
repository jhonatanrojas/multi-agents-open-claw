import { useEffect } from 'react';
import { useAuthStore } from '@/store';

/**
 * Hook to manage authentication state
 * Handles session checking and provides auth status
 */
export function useAuth() {
  const { 
    isAuthenticated, 
    isLoading, 
    error, 
    sessionChecked,
    checkSession,
    logout,
    clearError,
  } = useAuthStore();

  // Check session on mount if not already checked
  useEffect(() => {
    if (!sessionChecked) {
      checkSession();
    }
  }, [checkSession, sessionChecked]);

  return {
    isAuthenticated,
    isLoading: isLoading || !sessionChecked,
    error,
    logout,
    clearError,
    checkSession,
  };
}
