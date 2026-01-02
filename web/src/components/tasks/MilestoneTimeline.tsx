'use client';

import { CheckCircle2, Circle, XCircle, Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { formatCurrency, formatNumber } from '@/lib/utils';

interface MilestoneLike {
  id: string;
  title: string;
  description: string;
  complexity: string;
  status: string;
  llm_model?: string | null;
  input_tokens?: number;
  output_tokens?: number;
  cost_usd?: string;
  completed_at?: string | null;
}

interface MilestoneTimelineProps {
  milestones: MilestoneLike[];
}

function getStatusIcon(status: string) {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="h-5 w-5 text-green-500" />;
    case 'failed':
      return <XCircle className="h-5 w-5 text-red-500" />;
    case 'in_progress':
      return <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />;
    default:
      return <Circle className="h-5 w-5 text-muted-foreground" />;
  }
}

function getComplexityColor(complexity: string) {
  switch (complexity) {
    case 'trivial':
      return 'bg-gray-100 text-gray-800';
    case 'simple':
      return 'bg-green-100 text-green-800';
    case 'moderate':
      return 'bg-yellow-100 text-yellow-800';
    case 'complex':
      return 'bg-orange-100 text-orange-800';
    case 'context_heavy':
      return 'bg-red-100 text-red-800';
    default:
      return 'bg-gray-100 text-gray-800';
  }
}

export function MilestoneTimeline({ milestones }: MilestoneTimelineProps) {
  if (milestones.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        No milestones yet
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {milestones.map((milestone, index) => (
        <div key={milestone.id} className="flex gap-4">
          {/* Timeline connector */}
          <div className="flex flex-col items-center">
            {getStatusIcon(milestone.status)}
            {index < milestones.length - 1 && (
              <div className="w-0.5 h-full bg-border mt-2" />
            )}
          </div>

          {/* Milestone content */}
          <div className="flex-1 pb-4">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-medium">{milestone.title}</span>
              <Badge className={getComplexityColor(milestone.complexity)} variant="outline">
                {milestone.complexity}
              </Badge>
            </div>

            <p className="text-sm text-muted-foreground mb-2">
              {milestone.description}
            </p>

            <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
              {milestone.llm_model && (
                <span>Model: {milestone.llm_model}</span>
              )}
              {(milestone.input_tokens ?? 0) > 0 && (
                <span>
                  Tokens: {formatNumber((milestone.input_tokens ?? 0) + (milestone.output_tokens ?? 0))}
                </span>
              )}
              {milestone.cost_usd && parseFloat(milestone.cost_usd) > 0 && (
                <span>Cost: {formatCurrency(milestone.cost_usd)}</span>
              )}
              {milestone.completed_at && (
                <span>
                  Completed: {new Date(milestone.completed_at).toLocaleTimeString()}
                </span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
