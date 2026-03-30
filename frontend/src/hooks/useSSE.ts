import { useEffect, useRef, useCallback } from 'react';
import { useMemoryStore } from '@/store';
import { API_BASE } from '@/constants';
import type { Memory } from '@/types';

// SSE stream endpoint follows the same API base used by the rest of the app.
const SSE_URL = API_BASE.replace(/\/$/, '') + '/stream';

interface UseSSEOptions {
  enabled?: boolean;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
}

export function useSSE(options: UseSSEOptions = {}) {
  const { enabled = true, onOpen, onClose, onError } = options;
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  
  const setMemory = useMemoryStore((state) => state.setMemory);
  const setConnected = useMemoryStore((state) => state.setConnected);
  
  const connect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }
    
    try {
      const eventSource = new EventSource(SSE_URL);
      eventSourceRef.current = eventSource;
      
      eventSource.onopen = () => {
        setConnected(true);
        onOpen?.();
      };
      
      eventSource.onmessage = (event) => {
        try {
          const data: Memory = JSON.parse(event.data);
          setMemory(data);
          setConnected(true);
        } catch (e) {
          console.error('Failed to parse SSE message:', e);
        }
      };
      
      eventSource.onerror = () => {
        setConnected(false);
        onError?.(new Event('error'));
        
        // Reconnect after 3 seconds
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
        }
        reconnectTimeoutRef.current = window.setTimeout(() => {
          reconnectTimeoutRef.current = null;
          if (enabled) {
            connect();
          }
        }, 3000);
      };
    } catch (e) {
      console.error('Failed to create EventSource:', e);
      setConnected(false);
    }
  }, [enabled, setMemory, setConnected, onOpen, onError]);
  
  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    setConnected(false);
    onClose?.();
  }, [setConnected, onClose]);
  
  useEffect(() => {
    if (enabled) {
      connect();
    }
    
    return () => {
      disconnect();
    };
  }, [enabled, connect, disconnect]);
  
  return {
    isConnected: useMemoryStore((state) => state.isConnected),
    disconnect,
    reconnect: connect,
  };
}
