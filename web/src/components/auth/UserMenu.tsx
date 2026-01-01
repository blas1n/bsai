'use client';

import { User, LogOut, Settings } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/hooks/useAuth';

export function UserMenu() {
  const { user, isAuthenticated, isLoading, login, logout } = useAuth();

  if (isLoading) {
    return (
      <div className="h-8 w-8 animate-pulse rounded-full bg-muted" />
    );
  }

  if (!isAuthenticated) {
    return (
      <Button variant="outline" size="sm" onClick={() => login()}>
        Sign In
      </Button>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-2 text-sm">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground">
          {user?.image ? (
            <img
              src={user.image}
              alt={user.name || 'User'}
              className="h-8 w-8 rounded-full"
            />
          ) : (
            <User className="h-4 w-4" />
          )}
        </div>
        <span className="hidden md:inline-block">{user?.name || user?.email}</span>
      </div>
      <Button variant="ghost" size="icon" onClick={() => logout()} title="Sign out">
        <LogOut className="h-4 w-4" />
      </Button>
    </div>
  );
}
