'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { CheckSquare, Pause, Plus, RefreshCw, Trash2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SessionCard } from './SessionCard';
import { api } from '@/lib/api';
import { useSessionStore } from '@/stores/sessionStore';
import { useAuth } from '@/hooks/useAuth';

export function SessionList() {
  const { sessions, setSessions, addSession, isLoading, setLoading, error, setError } = useSessionStore();
  const { accessToken, isLoading: isAuthLoading } = useAuth();
  const [isCreating, setIsCreating] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isBulkActing, setIsBulkActing] = useState(false);
  const hasFetchedRef = useRef(false);

  const fetchSessions = useCallback(async () => {
    if (!accessToken) {
      console.log('[SessionList] No token, skipping fetch');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await api.getSessions();
      setSessions(response.items);
    } catch (err) {
      setError('Failed to fetch sessions');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [accessToken, setLoading, setError, setSessions]);

  const handleCreateSession = async () => {
    setIsCreating(true);
    try {
      const session = await api.createSession();
      addSession(session);
    } catch (err) {
      setError('Failed to create session');
      console.error(err);
    } finally {
      setIsCreating(false);
    }
  };

  const toggleSelection = (id: string, selected: boolean) => {
    const newSet = new Set(selectedIds);
    if (selected) {
      newSet.add(id);
    } else {
      newSet.delete(id);
    }
    setSelectedIds(newSet);
  };

  const handleBulkAction = async (action: 'pause' | 'complete' | 'delete') => {
    if (selectedIds.size === 0) return;

    setIsBulkActing(true);
    try {
      const result = await api.bulkSessionAction(Array.from(selectedIds), action);
      if (result.failed.length > 0) {
        setError(`Some sessions failed: ${result.failed.map(f => f.error).join(', ')}`);
      }
      // Refresh sessions list
      await fetchSessions();
      setSelectedIds(new Set());
      setSelectionMode(false);
    } catch (err) {
      setError(`Failed to ${action} sessions`);
      console.error(err);
    } finally {
      setIsBulkActing(false);
    }
  };

  const cancelSelection = () => {
    setSelectionMode(false);
    setSelectedIds(new Set());
  };

  const selectAll = () => {
    setSelectedIds(new Set(sessions.map(s => s.id)));
  };

  // Fetch sessions when auth is ready and token is available
  useEffect(() => {
    // Wait for auth to finish loading
    if (isAuthLoading) {
      return;
    }

    // Only fetch if we have a token and haven't fetched yet
    if (accessToken && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      fetchSessions();
    }
  }, [accessToken, isAuthLoading, fetchSessions]);

  // Reset fetch flag when token changes (e.g., re-login)
  useEffect(() => {
    if (!accessToken) {
      hasFetchedRef.current = false;
    }
  }, [accessToken]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold tracking-tight">Sessions</h2>
        <div className="flex items-center space-x-2">
          {selectionMode ? (
            <>
              <span className="text-sm text-muted-foreground">
                {selectedIds.size} selected
              </span>
              <Button variant="outline" size="sm" onClick={selectAll} disabled={isBulkActing}>
                Select All
              </Button>
              <Button
                variant="outline"
                size="icon"
                onClick={() => handleBulkAction('pause')}
                disabled={selectedIds.size === 0 || isBulkActing}
                title="Pause selected"
              >
                <Pause className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                onClick={() => handleBulkAction('complete')}
                disabled={selectedIds.size === 0 || isBulkActing}
                title="Complete selected"
              >
                <CheckSquare className="h-4 w-4" />
              </Button>
              <Button
                variant="destructive"
                size="icon"
                onClick={() => handleBulkAction('delete')}
                disabled={selectedIds.size === 0 || isBulkActing}
                title="Delete selected"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" onClick={cancelSelection} disabled={isBulkActing}>
                <X className="h-4 w-4" />
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSelectionMode(true)}
                disabled={sessions.length === 0}
              >
                Select
              </Button>
              <Button variant="outline" size="icon" onClick={fetchSessions} disabled={isLoading}>
                <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                <span className="sr-only">Refresh</span>
              </Button>
              <Button onClick={handleCreateSession} disabled={isCreating}>
                <Plus className="mr-2 h-4 w-4" />
                New Session
              </Button>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-md bg-destructive/15 p-4 text-destructive">
          {error}
        </div>
      )}

      {(isLoading || isAuthLoading) && sessions.length === 0 ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : sessions.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <p className="text-muted-foreground mb-4">No sessions yet</p>
          <Button onClick={handleCreateSession} disabled={isCreating}>
            <Plus className="mr-2 h-4 w-4" />
            Create your first session
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {sessions.map((session) => (
            <SessionCard
              key={session.id}
              session={session}
              selectable={selectionMode}
              selected={selectedIds.has(session.id)}
              onSelectChange={(selected) => toggleSelection(session.id, selected)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
