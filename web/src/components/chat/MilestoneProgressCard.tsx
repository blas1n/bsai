'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp, Check, Loader2, Circle, AlertCircle } from 'lucide-react';
import { MilestoneInfo, COMPLEXITY_DISPLAY, QA_DECISION_DISPLAY } from '@/types/chat';
import { MilestoneStatus, TaskComplexity } from '@/types/session';
import { cn, formatNumber, formatCurrency } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';

interface MilestoneProgressCardProps {
  milestones: MilestoneInfo[];
  defaultExpanded?: boolean;
}

export function MilestoneProgressCard({
  milestones,
  defaultExpanded = false,
}: MilestoneProgressCardProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  const completed = milestones.filter((m) => m.status === 'passed').length;
  const inProgress = milestones.filter((m) => m.status === 'in_progress').length;
  const failed = milestones.filter((m) => m.status === 'failed').length;
  const total = milestones.length;

  const progress = total > 0 ? (completed / total) * 100 : 0;

  return (
    <div className="w-full max-w-md rounded-lg border bg-card">
      {/* Header - always visible */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-3 hover:bg-accent/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Milestones</span>
          <Badge variant="outline" className="text-xs">
            {completed}/{total}
          </Badge>
          {inProgress > 0 && (
            <Badge variant="secondary" className="text-xs">
              <Loader2 className="h-3 w-3 animate-spin mr-1" />
              In Progress
            </Badge>
          )}
          {failed > 0 && (
            <Badge variant="destructive" className="text-xs">
              {failed} Failed
            </Badge>
          )}
        </div>
        {isExpanded ? (
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      {/* Progress Bar */}
      <div className="px-3 pb-2">
        <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-primary transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="border-t divide-y">
          {milestones.map((milestone) => (
            <MilestoneItem key={milestone.id} milestone={milestone} />
          ))}
        </div>
      )}
    </div>
  );
}

function MilestoneItem({ milestone }: { milestone: MilestoneInfo }) {
  const statusIconMap: Record<string, typeof Circle> = {
    pending: Circle,
    in_progress: Loader2,
    completed: Check,
    passed: Check,
    failed: AlertCircle,
  };

  const statusColorMap: Record<string, string> = {
    pending: 'text-muted-foreground',
    in_progress: 'text-blue-500',
    completed: 'text-green-500',
    passed: 'text-green-500',
    failed: 'text-red-500',
  };

  const StatusIcon = statusIconMap[milestone.status] || Circle;
  const statusColor = statusColorMap[milestone.status] || 'text-muted-foreground';

  const complexityInfo = COMPLEXITY_DISPLAY[milestone.complexity];

  return (
    <div className="p-3 text-sm">
      <div className="flex items-start gap-2">
        {/* Status Icon */}
        <StatusIcon
          className={cn(
            'h-4 w-4 mt-0.5 flex-shrink-0',
            statusColor,
            milestone.status === 'in_progress' && 'animate-spin'
          )}
        />

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Title */}
          <div className="flex items-center gap-2">
            <span className="font-medium truncate">{milestone.title}</span>
            <Badge
              variant="outline"
              className={cn(
                'text-xs',
                `text-${complexityInfo.color}-600 border-${complexityInfo.color}-200`
              )}
            >
              {complexityInfo.label}
            </Badge>
          </div>

          {/* Description */}
          {milestone.description && (
            <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
              {milestone.description}
            </p>
          )}

          {/* Model & Usage */}
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            {milestone.selectedModel && (
              <span className="text-xs text-muted-foreground">
                Model: {milestone.selectedModel}
              </span>
            )}
            {milestone.usage && (
              <>
                <span className="text-xs text-muted-foreground">
                  {formatNumber(milestone.usage.inputTokens + milestone.usage.outputTokens)} tokens
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatCurrency(milestone.usage.costUsd)}
                </span>
              </>
            )}
          </div>

          {/* QA Result */}
          {milestone.qaResult && (
            <div className="mt-1">
              <span
                className={cn(
                  'text-xs font-medium',
                  milestone.qaResult.decision === 'pass' && 'text-green-600',
                  milestone.qaResult.decision === 'retry' && 'text-yellow-600',
                  milestone.qaResult.decision === 'fail' && 'text-red-600'
                )}
              >
                QA: {QA_DECISION_DISPLAY[milestone.qaResult.decision].label}
                {milestone.qaResult.retryCount > 0 && (
                  <span className="opacity-75">
                    {' '}
                    ({milestone.qaResult.retryCount}/{milestone.qaResult.maxRetries} retries)
                  </span>
                )}
              </span>
              {milestone.qaResult.feedback && (
                <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                  {milestone.qaResult.feedback}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
