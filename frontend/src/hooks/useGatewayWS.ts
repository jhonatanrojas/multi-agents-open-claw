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
  
  const connect = useCallback(() => {
    // Close existing socket
    if (socketRef.current) {
      socketRef.current.close();
    }
    
    try {
      const url = getGatewayWsUrl();
      const socket = new WebSocket(url);
      socketRef.current = socket;
      
      socket.onopen = () => {
        setStatus({ connected: true, last_error: undefined });
        onOpen?.();
      };
      
      socket.onmessage = (event) => {
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
        setStatus({ connected: false });
        onError?.(new Event('error'));
      };
      
      socket.onclose = () => {
        setStatus({ connected: false });
        socketRef.current = null;
        onClose?.();
        
        // Reconnect after 4 seconds
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
        }
        reconnectTimeoutRef.current = window.setTimeout(() => {
          reconnectTimeoutRef.current = null;
          if (enabled) {
            connect();
          }
        }, 4000);
      };
    } catch (e) {
      console.error('Failed to create WebSocket:', e);
      setStatus({ connected: false, last_error: String(e) });
    }
  }, [enabled, setSnapshot, addEvent, setStatus, onOpen, onClose, onError]);
  
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
  
  useEffect(() => {
    if (enabled) {
      connect();
    }
    
    return () => {
      disconnect();
    };
  }, [enabled, connect, disconnect]);
  
  return {
    isConnected: useGatewayStore((state) => state.status.connected),
    disconnect,
    reconnect: connect,
  };
}