'use client';

import { ChevronDown, ChevronRight, CheckCircle, RefreshCw, XCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { MilestoneInfo, QADecision } from '@/types/chat';
import { STATUS_ICONS, COMPLEXITY_COLORS } from '@/lib/agentConstants';

interface QAResultBadgeProps {
  decision: QADecision;
  retryCount?: number;
}

export function QAResultBadge({ decision, retryCount }: QAResultBadgeProps) {
  const config = {
    pass: { icon: <CheckCircle className="h-3 w-3" />, color: 'text-green-500 bg-green-500/10' },
    retry: { icon: <RefreshCw className="h-3 w-3" />, color: 'text-yellow-500 bg-yellow-500/10' },
    fail: { icon: <XCircle className="h-3 w-3" />, color: 'text-red-500 bg-red-500/10' },
  };

  const { icon, color } = config[decision];

  return (
    <div className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs', color)}>
      {icon}
      <span className="capitalize">{decision}</span>
      {retryCount !== undefined && retryCount > 0 && (
        <span className="text-muted-foreground">({retryCount}x)</span>
      )}
    </div>
  );
}

interface MilestoneCardProps {
  milestone: MilestoneInfo;
  isExpanded: boolean;
  onToggle: () => void;
}

export function MilestoneCard({ milestone, isExpanded, onToggle }: MilestoneCardProps) {
  const statusIcon = STATUS_ICONS[milestone.status as keyof typeof STATUS_ICONS] || STATUS_ICONS.pending;

  return (
    <div className="border rounded-lg bg-card">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 p-3 text-left hover:bg-accent/50 transition-colors"
      >
        {isExpanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
        <span className="flex-shrink-0 w-6 h-6 rounded-full bg-muted flex items-center justify-center text-xs font-medium">
          {milestone.sequenceNumber}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{milestone.title}</p>
        </div>
        {statusIcon}
      </button>

      {isExpanded && (
        <div className="px-3 pb-3 pt-0 space-y-2 border-t">
          {milestone.description && (
            <p className="text-xs text-muted-foreground mt-2">{milestone.description}</p>
          )}

          <div className="flex flex-wrap gap-2 mt-2">
            {milestone.selectedModel && (
              <span className="text-xs px-2 py-0.5 rounded bg-muted">
                {milestone.selectedModel}
              </span>
            )}
            <span className={cn(
              'text-xs px-2 py-0.5 rounded capitalize',
              COMPLEXITY_COLORS[milestone.complexity],
            )}>
              {milestone.complexity}
            </span>
          </div>

          {milestone.qaResult && (
            <div className="mt-2">
              <QAResultBadge
                decision={milestone.qaResult.decision}
                retryCount={milestone.qaResult.retryCount}
              />
              {milestone.qaResult.feedback && (
                <p className="text-xs text-muted-foreground mt-1">
                  {milestone.qaResult.feedback}
                </p>
              )}
            </div>
          )}

          {milestone.usage && (
            <div className="text-xs text-muted-foreground mt-2 flex items-center gap-2">
              <span>{milestone.usage.inputTokens + milestone.usage.outputTokens} tokens</span>
              <span>${milestone.usage.costUsd.toFixed(4)}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
