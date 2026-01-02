'use client';

import { useState } from 'react';
import { Loader2, CheckCircle, ChevronDown, ChevronRight, Brain, Sparkles, Cog, FileText, MessageCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { AgentActivity, AgentType, AGENT_DISPLAY } from '@/types/chat';

interface AgentThinkingProps {
  currentActivity: AgentActivity | null;
  agentHistory: AgentActivity[];
  isStreaming: boolean;
}

const AGENT_ICONS: Record<AgentType, React.ReactNode> = {
  conductor: <Brain className="h-4 w-4" />,
  meta_prompter: <Sparkles className="h-4 w-4" />,
  worker: <Cog className="h-4 w-4" />,
  qa: <CheckCircle className="h-4 w-4" />,
  summarizer: <FileText className="h-4 w-4" />,
  responder: <MessageCircle className="h-4 w-4" />,
};

const AGENT_COLORS: Record<AgentType, string> = {
  conductor: 'text-blue-500',
  meta_prompter: 'text-purple-500',
  worker: 'text-green-500',
  qa: 'text-orange-500',
  summarizer: 'text-gray-500',
  responder: 'text-teal-500',
};

// Merge running and completed activities - show completed state when available
function mergeActivities(history: AgentActivity[]): AgentActivity[] {
  const activityMap = new Map<string, AgentActivity>();

  // Process in order, completed states will override running states for same agent
  // We use agent name as key since each agent processes sequentially
  history.forEach(activity => {
    const key = activity.agent;
    const existing = activityMap.get(key);

    // Keep completed over running, or update if newer completed
    if (!existing || activity.status === 'completed') {
      activityMap.set(key, activity);
    }
  });

  return Array.from(activityMap.values());
}

export function AgentThinking({ currentActivity, agentHistory, isStreaming }: AgentThinkingProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  if (!isStreaming && agentHistory.length === 0) {
    return null;
  }

  // Merge activities to remove running/completed duplicates
  const mergedHistory = mergeActivities(agentHistory);

  // Get completed agents from merged history
  const completedSteps = mergedHistory.filter(a => a.status === 'completed');

  return (
    <div className="flex gap-3 py-4">
      {/* Avatar placeholder for alignment with messages */}
      <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
        <Brain className="h-4 w-4 text-primary" />
      </div>

      <div className="flex-1 min-w-0">
        {/* Header */}
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          {isExpanded ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
          <span>Agent Pipeline</span>
          {isStreaming && (
            <Loader2 className="h-3 w-3 animate-spin text-primary" />
          )}
          {!isStreaming && completedSteps.length > 0 && (
            <span className="text-xs text-green-500">
              ({completedSteps.length} steps completed)
            </span>
          )}
        </button>

        {/* Expanded content */}
        {isExpanded && (
          <div className="mt-3 space-y-2">
            {/* Current activity - prominent display */}
            {currentActivity && currentActivity.status === 'running' && (
              <div className="flex items-start gap-3 p-3 rounded-lg bg-primary/5 border border-primary/20">
                <div className={cn(
                  'w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 bg-background',
                  AGENT_COLORS[currentActivity.agent]
                )}>
                  {AGENT_ICONS[currentActivity.agent]}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">
                      {AGENT_DISPLAY[currentActivity.agent].label}
                    </span>
                    <Loader2 className="h-3 w-3 animate-spin text-primary" />
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {currentActivity.message || 'Processing...'}
                  </p>
                  {/* Thinking dots */}
                  <div className="flex gap-1 mt-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}

            {/* Completed steps - compact list */}
            {completedSteps.length > 0 && (
              <div className="space-y-1">
                {completedSteps.map((activity, idx) => (
                  <div
                    key={`${activity.agent}-${idx}`}
                    className="flex items-center gap-2 px-2 py-1 text-xs text-muted-foreground"
                  >
                    <CheckCircle className="h-3 w-3 text-green-500 flex-shrink-0" />
                    <span className={cn('font-medium', AGENT_COLORS[activity.agent])}>
                      {AGENT_DISPLAY[activity.agent].label}
                    </span>
                    {activity.message && (
                      <span className="truncate">
                        - {activity.message}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
