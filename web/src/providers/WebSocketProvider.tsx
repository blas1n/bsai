'use client';

import { WSMessage, WSMessageType } from '@/types/websocket';
import { useSession } from 'next-auth/react';
import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:18001';

type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting';

interface WebSocketContextValue {
  /** Whether the WebSocket is currently connected */
  isConnected: boolean;
  /** Detailed connection state */
  connectionState: ConnectionState;
  /** Subscribe to a session's events */
  subscribe: (sessionId: string) => void;
  /** Unsubscribe from a session's events */
  unsubscribe: (sessionId: string) => void;
  /** Send a message through the WebSocket */
  send: (message: WSMessage) => void;
  /** Add a listener for incoming messages */
  addMessageListener: (callback: (msg: WSMessage) => void) => () => void;
  /** Force a reconnection */
  reconnect: () => void;
  /** The last message received */
  lastMessage: WSMessage | null;
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

interface WebSocketProviderProps {
  children: ReactNode;
  /** Maximum number of reconnection attempts */
  maxReconnectAttempts?: number;
  /** Base interval for reconnection (exponential backoff) */
  reconnectInterval?: number;
}

/**
 * WebSocketProvider - Centralized WebSocket management
 *
 * Handles:
 * - Automatic connection when authenticated
 * - Token synchronization with auth state
 * - Reconnection with exponential backoff
 * - Message distribution to listeners
 */
export function WebSocketProvider({
  children,
  maxReconnectAttempts = 5,
  reconnectInterval = 3000,
}: WebSocketProviderProps) {
  const { data: session, status, update: updateSession } = useSession();
  const accessToken = session?.accessToken;

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const listenersRef = useRef<Set<(msg: WSMessage) => void>>(new Set());

  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);

  const isConnected = connectionState === 'connected';

  // Clean up reconnection timer
  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  // Disconnect WebSocket
  const disconnect = useCallback(() => {
    clearReconnectTimer();
    reconnectAttemptsRef.current = 0;

    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect');
      wsRef.current = null;
    }
    setConnectionState('disconnected');
  }, [clearReconnectTimer]);

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (!accessToken) {
      console.log('[WebSocketProvider] No access token, skipping connection');
      return;
    }

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[WebSocketProvider] Already connected');
      return;
    }

    if (wsRef.current?.readyState === WebSocket.CONNECTING) {
      console.log('[WebSocketProvider] Already connecting');
      return;
    }

    setConnectionState('connecting');

    const url = `${WS_URL}/api/v1/ws?token=${encodeURIComponent(accessToken)}`;
    console.log('[WebSocketProvider] Connecting...');

    const ws = new WebSocket(url);

    ws.onopen = () => {
      console.log('[WebSocketProvider] Connected');
      reconnectAttemptsRef.current = 0;
      clearReconnectTimer();
      setConnectionState('connected');
    };

    ws.onclose = (event) => {
      console.log('[WebSocketProvider] Disconnected, code:', event.code);
      wsRef.current = null;

      // Don't reconnect if we deliberately closed or if no token
      if (event.code === 1000 || !accessToken) {
        setConnectionState('disconnected');
        return;
      }

      // Token rejected (expired or invalid) - trigger session refresh
      if (event.code === 4003 || event.code === 403) {
        console.log('[WebSocketProvider] Token rejected, triggering session refresh...');
        updateSession().then(() => {
          // Session updated, reconnect will happen via accessToken change detection
          console.log('[WebSocketProvider] Session refresh triggered');
        }).catch((err) => {
          console.error('[WebSocketProvider] Session refresh failed:', err);
        });
        setConnectionState('disconnected');
        return;
      }

      // Attempt reconnection with exponential backoff
      if (reconnectAttemptsRef.current < maxReconnectAttempts) {
        setConnectionState('reconnecting');
        const delay = reconnectInterval * Math.pow(2, reconnectAttemptsRef.current);
        reconnectAttemptsRef.current++;
        console.log(
          `[WebSocketProvider] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts})`
        );
        reconnectTimeoutRef.current = setTimeout(() => {
          reconnectTimeoutRef.current = null;
          connect();
        }, delay);
      } else {
        console.log('[WebSocketProvider] Max reconnect attempts reached');
        setConnectionState('disconnected');
      }
    };

    ws.onerror = (error) => {
      console.error('[WebSocketProvider] Error:', error);
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as WSMessage;
        console.log('[WebSocketProvider] Message:', message.type);
        setLastMessage(message);

        // Notify all listeners
        listenersRef.current.forEach((listener) => {
          try {
            listener(message);
          } catch (err) {
            console.error('[WebSocketProvider] Listener error:', err);
          }
        });
      } catch (err) {
        console.error('[WebSocketProvider] Parse error:', err);
      }
    };

    wsRef.current = ws;
  }, [accessToken, clearReconnectTimer, maxReconnectAttempts, reconnectInterval, updateSession]);

  // Send a message
  const send = useCallback((message: WSMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    } else {
      console.warn('[WebSocketProvider] Not connected, cannot send message');
    }
  }, []);

  // Subscribe to a session
  const subscribe = useCallback(
    (sessionId: string) => {
      send({
        type: WSMessageType.SUBSCRIBE,
        payload: { session_id: sessionId },
        timestamp: new Date().toISOString(),
      });
    },
    [send]
  );

  // Unsubscribe from a session
  const unsubscribe = useCallback(
    (sessionId: string) => {
      send({
        type: WSMessageType.UNSUBSCRIBE,
        payload: { session_id: sessionId },
        timestamp: new Date().toISOString(),
      });
    },
    [send]
  );

  // Add a message listener
  const addMessageListener = useCallback((callback: (msg: WSMessage) => void) => {
    listenersRef.current.add(callback);
    return () => {
      listenersRef.current.delete(callback);
    };
  }, []);

  // Manual reconnect
  const reconnect = useCallback(() => {
    console.log('[WebSocketProvider] Manual reconnect');
    reconnectAttemptsRef.current = 0;
    disconnect();
    setTimeout(() => connect(), 100);
  }, [disconnect, connect]);

  // Connect when authenticated, disconnect when not
  const hasConnectedRef = useRef(false);
  useEffect(() => {
    if (status === 'authenticated' && accessToken) {
      if (!hasConnectedRef.current) {
        // Initial connection with delay to allow port forwarding to stabilize
        hasConnectedRef.current = true;
        setTimeout(() => connect(), 500);
      } else {
        connect();
      }
    } else if (status === 'unauthenticated') {
      hasConnectedRef.current = false;
      disconnect();
    }

    return () => {
      // Don't disconnect on every render, only on unmount
    };
  }, [status, accessToken, connect, disconnect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reconnect when token changes
  const prevTokenRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (prevTokenRef.current !== undefined && prevTokenRef.current !== accessToken && accessToken) {
      console.log('[WebSocketProvider] Token changed, reconnecting...');
      reconnect();
    }
    prevTokenRef.current = accessToken;
  }, [accessToken, reconnect]);

  const value: WebSocketContextValue = {
    isConnected,
    connectionState,
    subscribe,
    unsubscribe,
    send,
    addMessageListener,
    reconnect,
    lastMessage,
  };

  return <WebSocketContext.Provider value={value}>{children}</WebSocketContext.Provider>;
}

/**
 * Hook to use the WebSocket context
 */
export function useWebSocketContext() {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocketContext must be used within a WebSocketProvider');
  }
  return context;
}
