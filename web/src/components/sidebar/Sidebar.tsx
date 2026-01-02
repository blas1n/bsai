'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Plus, MessageSquare, BarChart3, ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ConversationList } from './ConversationList';
import { SessionStats } from './SessionStats';
import { UserMenu } from '@/components/auth';
import { ThemeToggle } from '@/components/theme';
import { useAuth } from '@/hooks/useAuth';
import { api, SessionResponse } from '@/lib/api';
import { cn } from '@/lib/utils';

interface SidebarProps {
  currentSessionId?: string;
  onNewChat?: () => void;
  stats?: {
    totalTokens: number;
    totalCostUsd: number;
  };
}

export function Sidebar({ currentSessionId, onNewChat, stats }: SidebarProps) {
  const pathname = usePathname();
  const { accessToken, isAuthenticated } = useAuth();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [sessions, setSessions] = useState<SessionResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Set API token when auth changes
  useEffect(() => {
    if (accessToken) {
      api.setToken(accessToken);
    }
  }, [accessToken]);

  // Fetch sessions when authenticated
  useEffect(() => {
    const fetchSessions = async () => {
      if (!isAuthenticated || !accessToken) {
        setIsLoading(false);
        return;
      }

      try {
        const response = await api.getSessions(50, 0);
        setSessions(response.items);
      } catch (err) {
        console.error('Failed to fetch sessions:', err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchSessions();
  }, [currentSessionId, isAuthenticated, accessToken]);

  return (
    <div
      className={cn(
        'flex flex-col h-full bg-background border-r transition-all duration-300',
        isCollapsed ? 'w-16' : 'w-64'
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b">
        {!isCollapsed && (
          <Link href="/chat" className="font-semibold text-lg">
            BSAI
          </Link>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="ml-auto"
        >
          {isCollapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </Button>
      </div>

      {/* New Chat Button */}
      <div className="p-2">
        <Button
          onClick={onNewChat}
          className={cn('w-full justify-start gap-2', isCollapsed && 'justify-center px-2')}
          variant="outline"
        >
          <Plus className="h-4 w-4" />
          {!isCollapsed && <span>New Chat</span>}
        </Button>
      </div>

      {/* Conversations */}
      <div className="flex-1 overflow-y-auto">
        {!isCollapsed && (
          <ConversationList
            sessions={sessions}
            currentSessionId={currentSessionId}
            isLoading={isLoading}
          />
        )}
      </div>

      {/* Navigation Links */}
      <div className="border-t p-2 space-y-1">
        <Link href="/monitoring">
          <Button
            variant={pathname === '/monitoring' ? 'secondary' : 'ghost'}
            className={cn('w-full justify-start gap-2', isCollapsed && 'justify-center px-2')}
          >
            <BarChart3 className="h-4 w-4" />
            {!isCollapsed && <span>Monitoring</span>}
          </Button>
        </Link>
        <Link href="/sessions">
          <Button
            variant={pathname === '/sessions' ? 'secondary' : 'ghost'}
            className={cn('w-full justify-start gap-2', isCollapsed && 'justify-center px-2')}
          >
            <MessageSquare className="h-4 w-4" />
            {!isCollapsed && <span>All Sessions</span>}
          </Button>
        </Link>
      </div>

      {/* Session Stats */}
      {!isCollapsed && stats && (
        <div className="border-t p-4">
          <SessionStats
            totalTokens={stats.totalTokens}
            totalCostUsd={stats.totalCostUsd}
          />
        </div>
      )}

      {/* User Menu & Theme Toggle */}
      <div className={cn('border-t p-2 flex items-center', isCollapsed ? 'justify-center' : 'justify-between')}>
        <UserMenu />
        <ThemeToggle />
      </div>
    </div>
  );
}
