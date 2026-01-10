'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, CheckCircle, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { AgentActivity, AGENT_DISPLAY } from '@/types/chat';
import { AGENT_ICONS, AGENT_BADGE_COLORS, AGENT_THINKING } from '@/lib/agentConstants';
import { AgentDetailsPanel } from './AgentDetailsPanel';

interface ActivityLogItemProps {
  activity: AgentActivity;
  isLatest: boolean;
}

export function ActivityLogItem({ activity, isLatest }: ActivityLogItemProps) {
  const [isExpanded, setIsExpanded] = useState(isLatest && activity.status === 'completed' && !!activity.details);
  const colorClasses = AGENT_BADGE_COLORS[activity.agent];
  const isRunning = activity.status === 'running';
  const isCompleted = activity.status === 'completed';
  const hasDetails = !!activity.details;

  return (
    <div className={cn(
      'rounded-md text-xs',
      isLatest && isRunning && 'bg-primary/5 border border-primary/20',
      isCompleted && !isExpanded && 'opacity-70',
      isExpanded && 'bg-muted/30 border border-border'
    )}>
      <button
        onClick={() => hasDetails && setIsExpanded(!isExpanded)}
        className={cn(
          'flex gap-3 py-2 px-3 w-full text-left',
          hasDetails && 'cursor-pointer hover:bg-muted/50 transition-colors',
          !hasDetails && 'cursor-default'
        )}
        disabled={!hasDetails}
      >
        <div className={cn(
          'w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0',
          colorClasses
        )}>
          {AGENT_ICONS[activity.agent]}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium">{AGENT_DISPLAY[activity.agent].label}</span>
            {isRunning && <Loader2 className="h-3 w-3 animate-spin text-primary" />}
            {isCompleted && <CheckCircle className="h-3 w-3 text-green-500" />}
            {hasDetails && (
              isExpanded
                ? <ChevronDown className="h-3 w-3 text-muted-foreground" />
                : <ChevronRight className="h-3 w-3 text-muted-foreground" />
            )}
          </div>
          <p className="text-muted-foreground mt-0.5 leading-relaxed">
            {activity.message || AGENT_THINKING[activity.agent].active}
          </p>
        </div>
      </button>
      {isExpanded && hasDetails && (
        <div className="px-3 pb-3">
          <AgentDetailsPanel agent={activity.agent} details={activity.details} />
        </div>
      )}
    </div>
  );
}
