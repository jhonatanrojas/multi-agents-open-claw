import { useEffect, useRef, useCallback, useState } from 'react';
import { useMemoryStore } from '@/store';
import { useAuthStore } from '@/store/authStore';
import { API_BASE } from '@/constants';
import type { Memory } from '@/types';

// SSE stream endpoint follows the same API base used by the rest of the app.
// API_BASE is '/api', so we append '/stream' to get '/api/stream'
const SSE_URL = API_BASE.replace(/\/$/, '') + '/stream';

export type SSEConnectionState = 'connecting' | 'connected' | 'reconnecting' | 'disconnected';

interface UseSSEOptions {
  enabled?: boolean;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
  onReconnect?: (attempt: number, maxAttempts: number) => void;
}

// EventSource with credentials support and smart reconnection
class EventSourceWithCredentials {
  private eventSource: EventSource | null = null;
  private url: string;
  private withCredentials: boolean;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private baseReconnectDelay = 1000;
  private maxReconnectDelay = 30000;
  private onMessageCallback: ((event: MessageEvent) => void) | null = null;
  private onOpenCallback: (() => void) | null = null;
  private onErrorCallback: ((error: Event) => void) | null = null;
  private onReconnectCallback: ((attempt: number, maxAttempts: number) => void) | null = null;
  private reconnectTimer: number | null = null;
  private isIntentionallyClosed = false;
  private lastEventId: string | null = null;
  private nextReconnectDelay = 0;

  constructor(url: string, options: { withCredentials?: boolean } = {}) {
    this.url = url;
    this.withCredentials = options.withCredentials ?? false;
    this.connect();
  }

  getReconnectAttempts() {
    return this.reconnectAttempts;
  }

  getMaxReconnectAttempts() {
    return this.maxReconnectAttempts;
  }

  getNextReconnectDelay() {
    return this.nextReconnectDelay;
  }

  private connect() {
    if (this.isIntentionallyClosed) return;

    try {
      let url = this.url;
      if (this.lastEventId) {
        url += (url.includes('?') ? '&' : '?') + `lastEventId=${encodeURIComponent(this.lastEventId)}`;
      }
      
      this.eventSource = new EventSource(url, { 
        withCredentials: this.withCredentials 
      });

      this.eventSource.onopen = () => {
        this.reconnectAttempts = 0;
        this.nextReconnectDelay = 0;
        this.onOpenCallback?.();
      };

      this.eventSource.onmessage = (event) => {
        if (event.lastEventId) {
          this.lastEventId = event.lastEventId;
        }
        this.onMessageCallback?.(event);
      };

      this.eventSource.onerror = (error) => {
        this.onErrorCallback?.(error);
        
        this.eventSource?.close();
        this.eventSource = null;
        
        // Don't reconnect if intentionally closed or max attempts reached
        if (!this.isIntentionallyClosed && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.attemptReconnect();
        }
      };
    } catch (e) {
      console.error('[SSE] Failed to create EventSource:', e);
      this.onErrorCallback?.(new Event('error'));
      if (!this.isIntentionallyClosed) {
        this.attemptReconnect();
      }
    }
  }

  private attemptReconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }

    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      
      const delay = Math.min(
        this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
        this.maxReconnectDelay
      );
      const jitter = Math.random() * 1000;
      this.nextReconnectDelay = delay + jitter;
      
      this.onReconnectCallback?.(this.reconnectAttempts, this.maxReconnectAttempts);
      
      this.reconnectTimer = window.setTimeout(() => {
        this.connect();
      }, this.nextReconnectDelay);
    } else {
      console.error('[SSE] Max reconnection attempts reached');
    }
  }

  set onmessage(callback: (event: MessageEvent) => void) {
    this.onMessageCallback = callback;
  }

  set onopen(callback: () => void) {
    this.onOpenCallback = callback;
  }

  set onerror(callback: (error: Event) => void) {
    this.onErrorCallback = callback;
  }

  set onreconnect(callback: (attempt: number, maxAttempts: number) => void) {
    this.onReconnectCallback = callback;
  }

  close() {
    this.isIntentionallyClosed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.eventSource?.close();
    this.eventSource = null;
  }

  reset() {
    this.isIntentionallyClosed = false;
    this.reconnectAttempts = 0;
    this.nextReconnectDelay = 0;
    this.close();
    this.connect();
  }
}

export function useSSE(options: UseSSEOptions = {}) {
  const { enabled = true, onOpen, onClose, onError, onReconnect } = options;
  const eventSourceRef = useRef<EventSourceWithCredentials | null>(null);
  const [connectionState, setConnectionState] = useState<SSEConnectionState>('connecting');
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [reconnectDelay, setReconnectDelay] = useState(0);
  
  const setMemory = useMemoryStore((state) => state.setMemory);
  const setConnected = useMemoryStore((state) => state.setConnected);
  const { isAuthenticated } = useAuthStore();
  
  // Use refs to avoid recreating callbacks
  const callbacksRef = useRef({ onOpen, onClose, onError, onReconnect });
  useEffect(() => {
    callbacksRef.current = { onOpen, onClose, onError, onReconnect };
  }, [onOpen, onClose, onError, onReconnect]);

  // Single effect to handle connection lifecycle
  useEffect(() => {
    if (!enabled) {
      setConnectionState('disconnected');
      setConnected(false);
      return;
    }

    // Only connect if authenticated
    if (!isAuthenticated) {
      setConnectionState('disconnected');
      setConnected(false);
      return;
    }

    setConnectionState('connecting');
    setReconnectAttempt(0);
    
    const eventSource = new EventSourceWithCredentials(SSE_URL, { 
      withCredentials: true 
    });
    eventSourceRef.current = eventSource;
    
    eventSource.onopen = () => {
      setConnected(true);
      setConnectionState('connected');
      setReconnectAttempt(0);
      callbacksRef.current.onOpen?.();
    };
    
    eventSource.onmessage = (event: MessageEvent) => {
      try {
        if (event.data === ': keepalive') {
          return;
        }
        
        const data: Memory = JSON.parse(event.data);
        setMemory(data);
        setConnected(true);
        setConnectionState('connected');
      } catch (e) {
        console.error('[SSE] Failed to parse message:', e);
      }
    };
    
    eventSource.onerror = () => {
      setConnected(false);
      callbacksRef.current.onError?.(new Event('error'));
    };

    eventSource.onreconnect = (attempt, maxAttempts) => {
      setConnectionState('reconnecting');
      setReconnectAttempt(attempt);
      setReconnectDelay(eventSource.getNextReconnectDelay());
      callbacksRef.current.onReconnect?.(attempt, maxAttempts);
    };

    // Cleanup function
    return () => {
      eventSource.close();
      eventSourceRef.current = null;
      callbacksRef.current.onClose?.();
    };
  // Only depend on enabled and isAuthenticated, not on callbacks or store actions
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, isAuthenticated]);
  
  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setConnected(false);
    setConnectionState('disconnected');
    onClose?.();
  }, [setConnected, onClose]);

  const reconnect = useCallback(() => {
    disconnect();
    // Force re-run of effect by toggling a dummy state
    setConnectionState('connecting');
  }, [disconnect]);
  
  return {
    isConnected: useMemoryStore((state) => state.isConnected),
    connectionState,
    reconnectAttempt,
    reconnectDelay,
    maxReconnectAttempts: 10,
    disconnect,
    reconnect,
  };
}
