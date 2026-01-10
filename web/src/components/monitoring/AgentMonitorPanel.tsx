'use client';

import { useState, useMemo } from 'react';
import { Brain, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  AgentActivity,
  MilestoneInfo,
  AGENT_DISPLAY,
} from '@/types/chat';
import {
  AGENT_ICONS,
  AGENT_BADGE_COLORS,
  AGENT_THINKING,
} from '@/lib/agentConstants';
import { MilestoneCard } from './MilestoneCard';
import { ActivityLogItem } from './ActivityLogItem';

interface AgentMonitorPanelProps {
  milestones: MilestoneInfo[];
  currentActivity: AgentActivity | null;
  isStreaming: boolean;
  agentHistory?: AgentActivity[];
}

export function AgentMonitorPanel({
  milestones,
  currentActivity,
  isStreaming,
  agentHistory = [],
}: AgentMonitorPanelProps) {
  const [expandedMilestones, setExpandedMilestones] = useState<Set<string>>(new Set());
  const [showAllHistory, setShowAllHistory] = useState(false);

  const toggleMilestone = (id: string) => {
    setExpandedMilestones((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  // Process activity history - merge running/completed for same activity instance
  // but keep separate instances (e.g., multiple QA retries)
  const mergedHistory = useMemo(() => {
    const activityMap = new Map<string, AgentActivity>();

    agentHistory.forEach((activity, idx) => {
      // Use timestamp + agent as key to identify same activity instance
      // Running and completed events for the same activity will share similar timestamps
      const timeKey = activity.startedAt?.slice(0, 19) || idx.toString(); // truncate to second
      const key = `${activity.agent}-${timeKey}`;
      const existing = activityMap.get(key);

      // Keep completed over running for same instance
      if (!existing || activity.status === 'completed') {
        activityMap.set(key, activity);
      }
    });

    return Array.from(activityMap.values());
  }, [agentHistory]);

  // Get recent activity for display (last 10 items, or all if showAllHistory)
  const displayedHistory = useMemo(() => {
    const sorted = [...mergedHistory].reverse();
    return showAllHistory ? sorted : sorted.slice(0, 10);
  }, [mergedHistory, showAllHistory]);

  return (
    <div className="h-full flex flex-col bg-background border-l">
      {/* Header */}
      <div className="p-4 border-b">
        <h2 className="font-semibold text-sm">Agent Pipeline</h2>
        <p className="text-xs text-muted-foreground mt-1">
          Multi-agent workflow monitoring
        </p>
      </div>

      {/* Current Activity - Enhanced */}
      {currentActivity && currentActivity.status === 'running' && (
        <div className="p-4 border-b bg-gradient-to-r from-primary/5 to-primary/10">
          <div className="flex items-center gap-2 mb-3">
            <div className="relative">
              <div className="absolute inset-0 bg-primary/20 rounded-full animate-ping" />
              <div className={cn(
                'relative w-10 h-10 rounded-full flex items-center justify-center',
                AGENT_BADGE_COLORS[currentActivity.agent]
              )}>
                {AGENT_ICONS[currentActivity.agent]}
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold">{AGENT_DISPLAY[currentActivity.agent].label}</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-primary/20 text-primary animate-pulse">
                  Working...
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                {currentActivity.model && `Using ${currentActivity.model}`}
              </p>
            </div>
          </div>

          {/* Thinking indicator */}
          <div className="bg-background/50 rounded-lg p-3 border">
            <div className="flex items-start gap-2">
              <Brain className="h-4 w-4 text-primary mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-xs font-medium text-foreground">
                  {currentActivity.message || AGENT_THINKING[currentActivity.agent].active}
                </p>
                <div className="flex items-center gap-1 mt-2">
                  <div className="flex gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Activity Log */}
      {mergedHistory.length > 0 && (
        <div className="flex-1 min-h-0 flex flex-col p-4 border-b">
          <div className="flex items-center justify-between mb-3 flex-shrink-0">
            <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Activity Log ({mergedHistory.length})
            </h3>
            {mergedHistory.length > 10 && (
              <button
                onClick={() => setShowAllHistory(!showAllHistory)}
                className="text-xs text-primary hover:underline"
              >
                {showAllHistory ? 'Show less' : 'Show all'}
              </button>
            )}
          </div>
          <div className="space-y-1 flex-1 overflow-y-auto">
            {displayedHistory.map((activity, idx) => (
              <ActivityLogItem
                key={`${activity.agent}-${activity.startedAt}-${idx}`}
                activity={activity}
                isLatest={idx === 0}
              />
            ))}
          </div>
        </div>
      )}

      {/* Milestones */}
      <div className="flex-1 min-h-0 flex flex-col p-4">
        <h3 className="text-xs font-medium text-muted-foreground mb-3 uppercase tracking-wider flex-shrink-0">
          Milestones ({milestones.length})
        </h3>
        {milestones.length === 0 && !isStreaming ? (
          <div className="text-center py-8 text-muted-foreground">
            <Brain className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No milestones yet</p>
            <p className="text-xs">Send a message to start</p>
          </div>
        ) : milestones.length === 0 && isStreaming ? (
          <div className="text-center py-8 text-muted-foreground">
            <Loader2 className="h-8 w-8 mx-auto mb-2 animate-spin text-primary" />
            <p className="text-sm">Planning milestones...</p>
            <p className="text-xs">Conductor is analyzing your request</p>
          </div>
        ) : (
          <div className="space-y-2 flex-1 overflow-y-auto">
            {milestones.map((milestone) => (
              <MilestoneCard
                key={milestone.id}
                milestone={milestone}
                isExpanded={expandedMilestones.has(milestone.id)}
                onToggle={() => toggleMilestone(milestone.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
