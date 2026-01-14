'use client';

import { SessionProvider } from 'next-auth/react';
import { ReactNode } from 'react';
import { WebSocketProvider } from './WebSocketProvider';

interface AuthProviderProps {
  children: ReactNode;
}

/**
 * AuthProvider - Authentication and WebSocket connection management
 *
 * Wraps the application with:
 * 1. SessionProvider - next-auth session management with token refresh
 * 2. WebSocketProvider - centralized WebSocket connection management
 */
export function AuthProvider({ children }: AuthProviderProps) {
  return (
    <SessionProvider
      // Refetch session every 4 minutes to keep token fresh
      refetchInterval={4 * 60}
      // Refetch when window regains focus
      refetchOnWindowFocus={true}
    >
      <WebSocketProvider>{children}</WebSocketProvider>
    </SessionProvider>
  );
}
