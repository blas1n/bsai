'use client';

import Link from 'next/link';
import { MessageSquare, Circle } from 'lucide-react';
import { SessionResponse } from '@/lib/api';
import { cn, formatRelativeTime } from '@/lib/utils';

interface ConversationListProps {
  sessions: SessionResponse[];
  currentSessionId?: string;
  isLoading: boolean;
}

// Group sessions by date
function groupSessionsByDate(sessions: SessionResponse[]) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
  const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);

  const groups: { label: string; sessions: SessionResponse[] }[] = [
    { label: 'Today', sessions: [] },
    { label: 'Yesterday', sessions: [] },
    { label: 'Previous 7 Days', sessions: [] },
    { label: 'Older', sessions: [] },
  ];

  sessions.forEach((session) => {
    const sessionDate = new Date(session.created_at);
    if (sessionDate >= today) {
      groups[0].sessions.push(session);
    } else if (sessionDate >= yesterday) {
      groups[1].sessions.push(session);
    } else if (sessionDate >= weekAgo) {
      groups[2].sessions.push(session);
    } else {
      groups[3].sessions.push(session);
    }
  });

  return groups.filter((g) => g.sessions.length > 0);
}

// Generate title from session (title from API or fallback to ID)
function getSessionTitle(session: SessionResponse): string {
  return session.title || 'New session';
}

// Get status indicator color
function getStatusColor(status: string): string {
  switch (status) {
    case 'active':
      return 'text-green-500';
    case 'paused':
      return 'text-yellow-500';
    case 'completed':
      return 'text-blue-500';
    case 'failed':
      return 'text-red-500';
    default:
      return 'text-gray-500';
  }
}

export function ConversationList({
  sessions,
  currentSessionId,
  isLoading,
}: ConversationListProps) {
  if (isLoading) {
    return (
      <div className="p-4 text-sm text-muted-foreground text-center">
        Loading conversations...
      </div>
    );
  }

  if (sessions.length === 0) {
    return (
      <div className="p-4 text-sm text-muted-foreground text-center">
        No conversations yet
      </div>
    );
  }

  const groupedSessions = groupSessionsByDate(sessions);

  return (
    <div className="space-y-4 p-2">
      {groupedSessions.map((group) => (
        <div key={group.label}>
          <h3 className="px-2 py-1 text-xs font-medium text-muted-foreground uppercase tracking-wider">
            {group.label}
          </h3>
          <div className="space-y-1">
            {group.sessions.map((session) => (
              <Link key={session.id} href={`/chat/${session.id}`}>
                <div
                  className={cn(
                    'flex items-center gap-2 px-2 py-2 rounded-md text-sm cursor-pointer transition-colors',
                    'hover:bg-accent',
                    currentSessionId === session.id && 'bg-accent'
                  )}
                >
                  <MessageSquare className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                  <div className="flex-1 min-w-0">
                    <p className="truncate">{getSessionTitle(session)}</p>
                    <p className="text-xs text-muted-foreground truncate">
                      {formatRelativeTime(session.created_at)}
                    </p>
                  </div>
                  <Circle
                    className={cn('h-2 w-2 flex-shrink-0', getStatusColor(session.status))}
                    fill="currentColor"
                  />
                </div>
              </Link>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
