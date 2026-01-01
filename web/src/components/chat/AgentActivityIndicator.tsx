'use client';

import { Loader2, Check, X } from 'lucide-react';
import { AgentActivity, AGENT_DISPLAY, AgentType } from '@/types/chat';
import { cn } from '@/lib/utils';

interface AgentActivityIndicatorProps {
  activities: AgentActivity[];
  showAll?: boolean;
}

export function AgentActivityIndicator({
  activities,
  showAll = false,
}: AgentActivityIndicatorProps) {
  // Show only the most recent activity unless showAll is true
  const displayActivities = showAll ? activities : activities.slice(-1);

  if (displayActivities.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-col gap-1">
      {displayActivities.map((activity, index) => (
        <ActivityItem key={index} activity={activity} />
      ))}
    </div>
  );
}

function ActivityItem({ activity }: { activity: AgentActivity }) {
  const agentInfo = AGENT_DISPLAY[activity.agent];
  const isRunning = activity.status === 'running';
  const isCompleted = activity.status === 'completed';
  const isFailed = activity.status === 'failed';

  return (
    <div
      className={cn(
        'flex items-center gap-2 px-3 py-1.5 rounded-md text-xs',
        'bg-muted/50 border border-muted'
      )}
    >
      {/* Status Icon */}
      {isRunning && <Loader2 className="h-3 w-3 animate-spin text-blue-500" />}
      {isCompleted && <Check className="h-3 w-3 text-green-500" />}
      {isFailed && <X className="h-3 w-3 text-red-500" />}

      {/* Agent Icon */}
      <span>{agentInfo.icon}</span>

      {/* Agent Name */}
      <span
        className={cn(
          'font-medium',
          isRunning && 'text-blue-600',
          isCompleted && 'text-green-600',
          isFailed && 'text-red-600'
        )}
      >
        {agentInfo.label}
      </span>

      {/* Model (if available) */}
      {activity.model && (
        <span className="text-muted-foreground">({activity.model})</span>
      )}

      {/* Message (if available) */}
      {activity.message && (
        <span className="text-muted-foreground truncate max-w-[200px]">
          - {activity.message}
        </span>
      )}
    </div>
  );
}

// Compact version for inline display
export function AgentActivityBadge({ agent, status }: { agent: AgentType; status: string }) {
  const agentInfo = AGENT_DISPLAY[agent];
  const isRunning = status === 'running';

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs',
        isRunning ? 'bg-blue-100 text-blue-700' : 'bg-muted text-muted-foreground'
      )}
    >
      {isRunning && <Loader2 className="h-2 w-2 animate-spin" />}
      <span>{agentInfo.icon}</span>
      <span>{agentInfo.label}</span>
    </span>
  );
}
