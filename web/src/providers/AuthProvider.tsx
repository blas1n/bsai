'use client';

import { SessionProvider, useSession, signOut } from 'next-auth/react';
import { ReactNode, useEffect } from 'react';

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
 * AuthProvider - Authentication context provider
 *
 * Wraps the application with:
 * 1. SessionProvider - next-auth session management with token refresh
 * 2. SessionErrorHandler - automatic sign out on token refresh failure
 *
 * Note: WebSocket connections are managed per-session via useWebSocket hook
 * in useChat, not via a global provider.
 */
export function AuthProvider({ children }: AuthProviderProps) {
  return (
    <SessionProvider
      // Refetch session every 2 minutes to keep token fresh
      // (Keycloak access token default is 5 minutes, so 2 minutes gives buffer)
      refetchInterval={2 * 60}
      // Refetch when window regains focus
      refetchOnWindowFocus={true}
    >
      <SessionErrorHandler>{children}</SessionErrorHandler>
    </SessionProvider>
  );
}
