import { useEffect, useRef, useCallback } from 'react';
import { useGatewayStore } from '@/store';
import type { GatewayEvent, GatewayStatus } from '@/types';

interface GatewayWSMessage {
  type: 'snapshot' | 'event' | 'status';
  snapshot?: { status: GatewayStatus; events: GatewayEvent[] };
  event?: GatewayEvent;
  status?: Partial<GatewayStatus>;
}

interface UseGatewayWSOptions {
  enabled?: boolean;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
}

function getGatewayWsUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws/gateway-events`;
}

export function useGatewayWS(options: UseGatewayWSOptions = {}) {
  const { enabled = true, onOpen, onClose, onError } = options;
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  
  const setSnapshot = useGatewayStore((state) => state.setSnapshot);
  const addEvent = useGatewayStore((state) => state.addEvent);
  const setStatus = useGatewayStore((state) => state.setStatus);
  
  // Use refs to avoid recreating callbacks
  const callbacksRef = useRef({ onOpen, onClose, onError });
  useEffect(() => {
    callbacksRef.current = { onOpen, onClose, onError };
  }, [onOpen, onClose, onError]);
  
  // Single effect to handle connection lifecycle
  useEffect(() => {
    if (!enabled) {
      setStatus({ connected: false });
      return;
    }
    
    let isActive = true;
    
    const connect = () => {
      if (!isActive) return;
      
      try {
        const url = getGatewayWsUrl();
        const socket = new WebSocket(url);
        socketRef.current = socket;
        
        socket.onopen = () => {
          if (!isActive) return;
          setStatus({ connected: true, last_error: undefined });
          callbacksRef.current.onOpen?.();
        };
        
        socket.onmessage = (event) => {
          if (!isActive) return;
          try {
            const data: GatewayWSMessage = JSON.parse(event.data);
            
            switch (data.type) {
              case 'snapshot':
                if (data.snapshot) {
                  setSnapshot(data.snapshot);
                }
                break;
              case 'event':
                if (data.event) {
                  addEvent(data.event);
                }
                break;
              case 'status':
                if (data.status) {
                  setStatus(data.status);
                }
                break;
            }
          } catch (e) {
            console.error('Failed to parse Gateway WS message:', e);
          }
        };
        
        socket.onerror = () => {
          if (!isActive) return;
          setStatus({ connected: false });
          callbacksRef.current.onError?.(new Event('error'));
        };
        
        socket.onclose = () => {
          if (!isActive) return;
          setStatus({ connected: false });
          socketRef.current = null;
          callbacksRef.current.onClose?.();
          
          // Reconnect after 4 seconds
          if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
          }
          reconnectTimeoutRef.current = window.setTimeout(() => {
            reconnectTimeoutRef.current = null;
            if (isActive) {
              connect();
            }
          }, 4000);
        };
      } catch (e) {
        console.error('Failed to create WebSocket:', e);
        setStatus({ connected: false, last_error: String(e) });
      }
    };
    
    connect();
    
    // Cleanup function
    return () => {
      isActive = false;
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };
  // Only depend on enabled, not on callbacks or store actions
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);
  
  const disconnect = useCallback(() => {
    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    setStatus({ connected: false });
  }, [setStatus]);
  
  const reconnect = useCallback(() => {
    disconnect();
    // Force re-run of effect
    setStatus({ connected: false });
  }, [disconnect, setStatus]);
  
  return {
    isConnected: useGatewayStore((state) => state.status.connected),
    disconnect,
    reconnect,
  };
}