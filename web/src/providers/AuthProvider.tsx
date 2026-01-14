'use client';

import { SessionProvider, useSession, signOut } from 'next-auth/react';
import { ReactNode, useEffect } from 'react';
import { WebSocketProvider } from './WebSocketProvider';

interface AuthProviderProps {
  children: ReactNode;
}

/**
 * SessionErrorHandler - Handles session errors like expired tokens
 */
function SessionErrorHandler({ children }: { children: ReactNode }) {
  const { data: session } = useSession();

  useEffect(() => {
    if (session?.error === 'RefreshAccessTokenError') {
      console.warn('[AuthProvider] Token refresh failed, signing out...');
      // Sign out and redirect to login when refresh fails
      signOut({ callbackUrl: '/login' });
    }
  }, [session?.error]);

  return <>{children}</>;
}

/**
 * AuthProvider - Authentication and WebSocket connection management
 *
 * Wraps the application with:
 * 1. SessionProvider - next-auth session management with token refresh
 * 2. SessionErrorHandler - automatic sign out on token refresh failure
 * 3. WebSocketProvider - centralized WebSocket connection management
 */
export function AuthProvider({ children }: AuthProviderProps) {
  return (
    <SessionProvider
      // Refetch session every 4 minutes to keep token fresh
      refetchInterval={4 * 60}
      // Refetch when window regains focus
      refetchOnWindowFocus={true}
    >
      <SessionErrorHandler>
        <WebSocketProvider>{children}</WebSocketProvider>
      </SessionErrorHandler>
    </SessionProvider>
  );
}
