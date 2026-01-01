'use client';

import { useSession, signIn, signOut } from 'next-auth/react';
import { useCallback } from 'react';

export function useAuth() {
  const { data: session, status } = useSession();

  const isAuthenticated = status === 'authenticated';
  const isLoading = status === 'loading';
  const user = session?.user;
  const accessToken = session?.accessToken;
  const error = session?.error;

  const login = useCallback((callbackUrl?: string) => {
    signIn('keycloak', { callbackUrl: callbackUrl || '/chat' });
  }, []);

  const logout = useCallback((callbackUrl?: string) => {
    signOut({ callbackUrl: callbackUrl || '/' });
  }, []);

  return {
    user,
    accessToken,
    isAuthenticated,
    isLoading,
    error,
    login,
    logout,
  };
}
