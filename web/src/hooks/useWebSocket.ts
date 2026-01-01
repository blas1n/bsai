'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { WSMessage, WSMessageType } from '@/types/websocket';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:18000';

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
  const previousTokenRef = useRef<string | undefined>(token);
  const isConnectingRef = useRef(false);
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);

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
    // Don't connect without a token (authentication required)
    if (!token) {
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
    if (sessionId) {
      url += `/${sessionId}`;
    }
    url += `?token=${encodeURIComponent(token)}`;

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
      if (autoReconnect && token && !reconnectTimeoutRef.current) {
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
  }, [sessionId, token, autoReconnect, reconnectInterval, maxReconnectAttempts]);

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

  // Handle token changes - reconnect with new token
  useEffect(() => {
    if (previousTokenRef.current !== token) {
      console.log('[useWebSocket] Token changed, reconnecting...');
      previousTokenRef.current = token;

      // Disconnect old connection
      disconnect();

      // Connect with new token (if available)
      if (token) {
        // Small delay to ensure clean disconnect
        setTimeout(() => connect(), 100);
      }
    }
  }, [token, disconnect, connect]);

  // Track if component is mounted
  const isMountedRef = useRef(false);

  // Initial connection (only when token is available)
  useEffect(() => {
    if (!isMountedRef.current) {
      isMountedRef.current = true;
      if (token) {
        connect();
      }
    }
    return () => {
      isMountedRef.current = false;
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Empty deps - only run on mount/unmount

  // Track previous sessionId to detect changes
  const previousSessionIdRef = useRef<string | undefined>(sessionId);

  // Reconnect when sessionId changes (if already connected)
  useEffect(() => {
    if (previousSessionIdRef.current !== sessionId) {
      previousSessionIdRef.current = sessionId;
      if (token && sessionId && isConnected) {
        // Session changed, need to reconnect to subscribe to new session
        console.log('[useWebSocket] Session changed, reconnecting...');
        reconnect();
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]); // Only react to sessionId changes

  return {
    isConnected,
    send,
    subscribe,
    unsubscribe,
    lastMessage,
    reconnect,
  };
}
