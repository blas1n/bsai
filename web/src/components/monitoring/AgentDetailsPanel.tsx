'use client';

import { cn } from '@/lib/utils';
import { AgentType } from '@/types/chat';
import {
  ArchitectDetails,
  WorkerDetails,
  QADetails,
} from '@/types/websocket';
import { COMPLEXITY_COLORS } from '@/lib/agentConstants';

// Type guards for agent details
export function isArchitectDetails(d: unknown): d is ArchitectDetails {
  if (!d || typeof d !== 'object') return false;
  const obj = d as Record<string, unknown>;
  if (!Array.isArray(obj.tasks) || obj.tasks.length === 0) return false;
  const first = obj.tasks[0] as Record<string, unknown>;
  return typeof first?.id === 'string' && typeof first?.description === 'string';
}

export function isWorkerDetails(d: unknown): d is WorkerDetails {
  if (!d || typeof d !== 'object') return false;
  const obj = d as Record<string, unknown>;
  return typeof obj.output_preview === 'string' && typeof obj.tokens_used === 'number';
}

export function isQADetails(d: unknown): d is QADetails {
  if (!d || typeof d !== 'object') return false;
  const obj = d as Record<string, unknown>;
  return typeof obj.decision === 'string' && typeof obj.attempt_number === 'number';
}

interface AgentDetailsPanelProps {
  agent: AgentType;
  details: unknown;
}

export function AgentDetailsPanel({ agent, details }: AgentDetailsPanelProps) {
  if (!details || typeof details !== 'object') return null;

  switch (agent) {
    case 'architect': {
      if (!isArchitectDetails(details)) return null;
      const d = details;
      return (
        <div className="mt-2 pl-2 border-l-2 border-blue-500/30">
          <p className="text-xs font-medium text-muted-foreground mb-1">Created Tasks:</p>
          <ul className="space-y-1">
            {d.tasks.map((t) => (
              <li key={t.id} className="text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{t.id}.</span> {t.description}
                <span className={cn(
                  'ml-1 px-1 py-0.5 rounded text-[10px]',
                  COMPLEXITY_COLORS[t.complexity],
                )}>
                  {t.complexity}
                </span>
              </li>
            ))}
          </ul>
        </div>
      );
    }
    case 'worker': {
      if (!isWorkerDetails(details)) return null;
      const d = details;
      return (
        <div className="mt-2 pl-2 border-l-2 border-green-500/30">
          <p className="text-xs font-medium text-muted-foreground mb-1">Output Preview:</p>
          <div className="bg-muted/50 rounded p-2 max-h-32 overflow-y-auto">
            <pre className="text-xs text-muted-foreground whitespace-pre-wrap break-words">
              {d.output_preview}
            </pre>
          </div>
          <div className="flex gap-2 mt-1 text-[10px] text-muted-foreground">
            <span>{d.tokens_used} tokens</span>
            <span>-</span>
            <span>${d.cost_usd.toFixed(4)}</span>
            <span>-</span>
            <span>{d.model}</span>
            {d.is_retry && <span className="text-yellow-500">- Retry</span>}
          </div>
        </div>
      );
    }
    case 'qa': {
      if (!isQADetails(details)) return null;
      const d = details;
      return (
        <div className="mt-2 pl-2 border-l-2 border-orange-500/30">
          <div className="flex items-center gap-2 mb-1">
            <span className={cn(
              'text-xs px-1.5 py-0.5 rounded font-medium',
              d.decision === 'pass' && 'bg-green-500/10 text-green-500',
              d.decision === 'retry' && 'bg-yellow-500/10 text-yellow-500',
              d.decision === 'fail' && 'bg-red-500/10 text-red-500',
            )}>
              {d.decision.toUpperCase()}
            </span>
            <span className="text-[10px] text-muted-foreground">
              Attempt {d.attempt_number}/{d.max_retries}
            </span>
          </div>
          {d.feedback && (
            <p className="text-xs text-muted-foreground bg-muted/50 rounded p-2">
              {d.feedback}
            </p>
          )}
        </div>
      );
    }
    default:
      return null;
  }
}
