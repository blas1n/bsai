'use client';

import { WSMessage, WSMessageType } from '@/types/websocket';
import { useCallback, useEffect, useRef, useState } from 'react';

// WebSocket URL - injected from docker-compose environment
const WS_URL = process.env.NEXT_PUBLIC_WS_URL;

interface UseWebSocketOptions {
  sessionId?: string;
  token?: string;
  onMessage?: (message: WSMessage) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
  autoReconnect?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
}

interface UseWebSocketReturn {
  isConnected: boolean;
  send: (message: WSMessage) => void;
  subscribe: (sessionId: string) => void;
  unsubscribe: (sessionId: string) => void;
  lastMessage: WSMessage | null;
  reconnect: () => void;
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const {
    sessionId,
    token,
    onMessage,
    onConnect,
    onDisconnect,
    onError,
    autoReconnect = true,
    reconnectInterval = 3000,
    maxReconnectAttempts = 5,
  } = options;

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const isConnectingRef = useRef(false);
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);

  // Store current values in refs to avoid dependency issues
  const tokenRef = useRef(token);
  const sessionIdRef = useRef(sessionId);

  // Update refs when values change
  useEffect(() => {
    tokenRef.current = token;
  }, [token]);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  // Use refs for callbacks to avoid reconnection on callback changes
  const onMessageRef = useRef(onMessage);
  const onConnectRef = useRef(onConnect);
  const onDisconnectRef = useRef(onDisconnect);
  const onErrorRef = useRef(onError);

  // Update refs when callbacks change
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    onConnectRef.current = onConnect;
  }, [onConnect]);

  useEffect(() => {
    onDisconnectRef.current = onDisconnect;
  }, [onDisconnect]);

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  const connect = useCallback(() => {
    const currentToken = tokenRef.current;
    const currentSessionId = sessionIdRef.current;

    // Don't connect without WebSocket URL configured
    if (!WS_URL) {
      console.error('[useWebSocket] NEXT_PUBLIC_WS_URL not configured');
      return;
    }

    // Don't connect without a token (authentication required)
    if (!currentToken) {
      console.log('[useWebSocket] No token, skipping connection');
      return;
    }

    // Prevent multiple simultaneous connection attempts
    if (isConnectingRef.current) {
      console.log('[useWebSocket] Already connecting, skipping');
      return;
    }

    // Don't reconnect if already connected
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[useWebSocket] Already connected');
      return;
    }

    // Close any existing connection that's in CONNECTING state
    if (wsRef.current?.readyState === WebSocket.CONNECTING) {
      console.log('[useWebSocket] Closing pending connection');
      wsRef.current.close();
      wsRef.current = null;
    }

    isConnectingRef.current = true;

    let url = `${WS_URL}/api/v1/ws`;
    if (currentSessionId) {
      url += `/${currentSessionId}`;
    }
    url += `?token=${encodeURIComponent(currentToken)}`;

    console.log('[useWebSocket] Connecting to:', url.replace(/token=[^&]+/, 'token=***'));
    const ws = new WebSocket(url);

    ws.onopen = () => {
      console.log('[useWebSocket] Connected');
      isConnectingRef.current = false;
      reconnectAttemptsRef.current = 0; // Reset on successful connection
      setIsConnected(true);
      onConnectRef.current?.();

      // Clear any pending reconnect
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };

    ws.onclose = (event) => {
      console.log('[useWebSocket] Disconnected, code:', event.code, 'reason:', event.reason);
      isConnectingRef.current = false;
      setIsConnected(false);
      wsRef.current = null;
      onDisconnectRef.current?.();

      // Auto reconnect with exponential backoff (only if we have a token)
      // Use ref to get current token value
      if (autoReconnect && tokenRef.current && !reconnectTimeoutRef.current) {
        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          const delay = reconnectInterval * Math.pow(2, reconnectAttemptsRef.current);
          reconnectAttemptsRef.current++;
          console.log(`[useWebSocket] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts})`);
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectTimeoutRef.current = null;
            connect();
          }, delay);
        } else {
          console.log('[useWebSocket] Max reconnect attempts reached');
        }
      }
    };

    ws.onerror = (error) => {
      console.error('[useWebSocket] Error:', error);
      isConnectingRef.current = false;
      onErrorRef.current?.(error);
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as WSMessage;
        console.log('[useWebSocket] Message received:', message.type);
        setLastMessage(message);
        onMessageRef.current?.(message);
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };

    wsRef.current = ws;
  }, [autoReconnect, reconnectInterval, maxReconnectAttempts]); // Removed token and sessionId from deps

  const disconnect = useCallback(() => {
    console.log('[useWebSocket] Disconnecting...');
    isConnectingRef.current = false;
    reconnectAttemptsRef.current = 0;

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect');
      wsRef.current = null;
    }
    setIsConnected(false);
  }, []);

  const send = useCallback((message: WSMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket not connected, cannot send message');
    }
  }, []);

  const subscribe = useCallback((targetSessionId: string) => {
    send({
      type: WSMessageType.SUBSCRIBE,
      payload: { session_id: targetSessionId },
      timestamp: new Date().toISOString(),
    });
  }, [send]);

  const unsubscribe = useCallback((targetSessionId: string) => {
    send({
      type: WSMessageType.UNSUBSCRIBE,
      payload: { session_id: targetSessionId },
      timestamp: new Date().toISOString(),
    });
  }, [send]);

  // Manual reconnect function (resets attempt counter)
  const reconnect = useCallback(() => {
    console.log('[useWebSocket] Manual reconnect requested');
    reconnectAttemptsRef.current = 0;
    disconnect();
    // Small delay to ensure clean disconnect
    setTimeout(() => connect(), 100);
  }, [disconnect, connect]);

  // Track previous values for change detection
  const prevTokenRef = useRef<string | undefined>(undefined);
  const prevSessionIdRef = useRef<string | undefined>(undefined);
  const isMountedRef = useRef(false);

  // Single effect to handle connection lifecycle
  useEffect(() => {
    const tokenChanged = prevTokenRef.current !== token;
    const sessionIdChanged = prevSessionIdRef.current !== sessionId;
    const isFirstMount = !isMountedRef.current;

    // Update previous values
    prevTokenRef.current = token;
    prevSessionIdRef.current = sessionId;
    isMountedRef.current = true;

    // Handle initial connection or reconnection due to changes
    if (token) {
      if (isFirstMount) {
        // Initial connection with small delay to allow port forwarding to stabilize
        console.log('[useWebSocket] Initial connection');
        setTimeout(() => connect(), 500);
      } else if (tokenChanged) {
        // Token changed - need full reconnect
        console.log('[useWebSocket] Token changed, reconnecting...');
        disconnect();
        setTimeout(() => connect(), 100);
      } else if (sessionIdChanged && isConnected) {
        // Session changed while connected - need to reconnect
        console.log('[useWebSocket] Session changed, reconnecting...');
        disconnect();
        setTimeout(() => connect(), 100);
      }
    } else if (!token && !isFirstMount) {
      // Token removed - disconnect
      console.log('[useWebSocket] Token removed, disconnecting...');
      disconnect();
    }

    // Cleanup on unmount
    return () => {
      if (!token) return; // Don't run cleanup logic if no token
    };
  }, [token, sessionId, isConnected, connect, disconnect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    isConnected,
    send,
    subscribe,
    unsubscribe,
    lastMessage,
    reconnect,
  };
}
