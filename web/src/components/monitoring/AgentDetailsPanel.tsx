'use client';

import { cn } from '@/lib/utils';
import { AgentType } from '@/types/chat';
import {
  ConductorDetails,
  MetaPrompterDetails,
  WorkerDetails,
  QADetails,
  SummarizerDetails,
} from '@/types/websocket';
import { COMPLEXITY_COLORS } from '@/lib/agentConstants';

// Type guards for agent details
export function isConductorDetails(d: unknown): d is ConductorDetails {
  if (!d || typeof d !== 'object') return false;
  const obj = d as Record<string, unknown>;
  if (!Array.isArray(obj.milestones) || obj.milestones.length === 0) return false;
  const first = obj.milestones[0] as Record<string, unknown>;
  return typeof first?.index === 'number' && typeof first?.description === 'string';
}

export function isMetaPrompterDetails(d: unknown): d is MetaPrompterDetails {
  if (!d || typeof d !== 'object') return false;
  const obj = d as Record<string, unknown>;
  return typeof obj.generated_prompt === 'string' && obj.generated_prompt.length > 0;
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

export function isSummarizerDetails(d: unknown): d is SummarizerDetails {
  if (!d || typeof d !== 'object') return false;
  const obj = d as Record<string, unknown>;
  return typeof obj.summary_preview === 'string' && typeof obj.old_message_count === 'number';
}

interface AgentDetailsPanelProps {
  agent: AgentType;
  details: unknown;
}

export function AgentDetailsPanel({ agent, details }: AgentDetailsPanelProps) {
  if (!details || typeof details !== 'object') return null;

  switch (agent) {
    case 'conductor': {
      if (!isConductorDetails(details)) return null;
      const d = details;
      return (
        <div className="mt-2 pl-2 border-l-2 border-blue-500/30">
          <p className="text-xs font-medium text-muted-foreground mb-1">Created Milestones:</p>
          <ul className="space-y-1">
            {d.milestones.map((m) => (
              <li key={m.index} className="text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{m.index}.</span> {m.description}
                <span className={cn(
                  'ml-1 px-1 py-0.5 rounded text-[10px]',
                  COMPLEXITY_COLORS[m.complexity],
                )}>
                  {m.complexity}
                </span>
              </li>
            ))}
          </ul>
        </div>
      );
    }
    case 'meta_prompter': {
      if (!isMetaPrompterDetails(details)) return null;
      const d = details;
      return (
        <div className="mt-2 pl-2 border-l-2 border-purple-500/30">
          <p className="text-xs font-medium text-muted-foreground mb-1">Generated Prompt:</p>
          <div className="bg-muted/50 rounded p-2 max-h-32 overflow-y-auto">
            <pre className="text-xs text-muted-foreground whitespace-pre-wrap break-words font-mono">
              {d.generated_prompt.length > 500
                ? d.generated_prompt.substring(0, 500) + '...'
                : d.generated_prompt}
            </pre>
          </div>
          <p className="text-[10px] text-muted-foreground mt-1">{d.prompt_length} characters</p>
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
    case 'summarizer': {
      if (!isSummarizerDetails(details)) return null;
      const d = details;
      return (
        <div className="mt-2 pl-2 border-l-2 border-gray-500/30">
          <p className="text-xs font-medium text-muted-foreground mb-1">Context Summary:</p>
          <div className="bg-muted/50 rounded p-2 max-h-24 overflow-y-auto">
            <p className="text-xs text-muted-foreground">{d.summary_preview}</p>
          </div>
          <p className="text-[10px] text-muted-foreground mt-1">
            Compressed {d.old_message_count} → {d.new_message_count} messages
          </p>
        </div>
      );
    }
    default:
      return null;
  }
}
