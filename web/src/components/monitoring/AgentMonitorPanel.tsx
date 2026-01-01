'use client';

import { useState, useMemo } from 'react';
import {
  Brain,
  Sparkles,
  Cog,
  CheckCircle,
  FileText,
  ChevronDown,
  ChevronRight,
  Clock,
  RefreshCw,
  XCircle,
  Loader2,
  MessageCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  AgentType,
  AgentActivity,
  MilestoneInfo,
  AGENT_DISPLAY,
  QADecision,
} from '@/types/chat';
import {
  ConductorDetails,
  MetaPrompterDetails,
  WorkerDetails,
  QADetails,
  SummarizerDetails,
} from '@/types/websocket';

interface AgentMonitorPanelProps {
  milestones: MilestoneInfo[];
  currentActivity: AgentActivity | null;
  isStreaming: boolean;
  agentHistory?: AgentActivity[];
}

// Agent thinking descriptions for each phase
const AGENT_THINKING: Record<AgentType, { active: string; phases: string[] }> = {
  conductor: {
    active: 'Analyzing task complexity and planning execution strategy...',
    phases: [
      'Parsing user request',
      'Identifying subtasks',
      'Assessing complexity levels',
      'Creating milestone breakdown',
      'Selecting optimal LLM for each task',
    ],
  },
  meta_prompter: {
    active: 'Optimizing prompt for better results...',
    phases: [
      'Analyzing task requirements',
      'Applying prompt engineering techniques',
      'Adding context and constraints',
      'Structuring output format',
      'Finalizing optimized prompt',
    ],
  },
  worker: {
    active: 'Executing task with selected LLM...',
    phases: [
      'Loading context',
      'Processing with LLM',
      'Generating response',
      'Formatting output',
    ],
  },
  qa: {
    active: 'Validating output quality...',
    phases: [
      'Checking against acceptance criteria',
      'Validating completeness',
      'Assessing accuracy',
      'Making pass/retry/fail decision',
    ],
  },
  summarizer: {
    active: 'Compressing context to preserve memory...',
    phases: [
      'Analyzing conversation history',
      'Identifying key information',
      'Creating compressed summary',
      'Updating context window',
    ],
  },
  responder: {
    active: 'Generating user-friendly response...',
    phases: [
      'Detecting user language',
      'Summarizing results',
      'Formatting response',
      'Finalizing message',
    ],
  },
};

const AGENT_ICONS: Record<AgentType, React.ReactNode> = {
  conductor: <Brain className="h-4 w-4" />,
  meta_prompter: <Sparkles className="h-4 w-4" />,
  worker: <Cog className="h-4 w-4" />,
  qa: <CheckCircle className="h-4 w-4" />,
  summarizer: <FileText className="h-4 w-4" />,
  responder: <MessageCircle className="h-4 w-4" />,
};

const AGENT_COLORS: Record<AgentType, string> = {
  conductor: 'text-blue-500 bg-blue-500/10 border-blue-500/20',
  meta_prompter: 'text-purple-500 bg-purple-500/10 border-purple-500/20',
  worker: 'text-green-500 bg-green-500/10 border-green-500/20',
  qa: 'text-orange-500 bg-orange-500/10 border-orange-500/20',
  summarizer: 'text-gray-500 bg-gray-500/10 border-gray-500/20',
  responder: 'text-teal-500 bg-teal-500/10 border-teal-500/20',
};

const STATUS_ICONS = {
  pending: <Clock className="h-3 w-3 text-muted-foreground" />,
  in_progress: <Loader2 className="h-3 w-3 text-blue-500 animate-spin" />,
  running: <Loader2 className="h-3 w-3 text-blue-500 animate-spin" />,
  completed: <CheckCircle className="h-3 w-3 text-green-500" />,
  passed: <CheckCircle className="h-3 w-3 text-green-500" />,
  failed: <XCircle className="h-3 w-3 text-red-500" />,
};

// Type guards for agent details
function isConductorDetails(d: unknown): d is ConductorDetails {
  if (!d || typeof d !== 'object') return false;
  const obj = d as Record<string, unknown>;
  if (!Array.isArray(obj.milestones) || obj.milestones.length === 0) return false;
  const first = obj.milestones[0] as Record<string, unknown>;
  return typeof first?.index === 'number' && typeof first?.description === 'string';
}

function isMetaPrompterDetails(d: unknown): d is MetaPrompterDetails {
  if (!d || typeof d !== 'object') return false;
  const obj = d as Record<string, unknown>;
  return typeof obj.generated_prompt === 'string' && obj.generated_prompt.length > 0;
}

function isWorkerDetails(d: unknown): d is WorkerDetails {
  if (!d || typeof d !== 'object') return false;
  const obj = d as Record<string, unknown>;
  return typeof obj.output_preview === 'string' && typeof obj.tokens_used === 'number';
}

function isQADetails(d: unknown): d is QADetails {
  if (!d || typeof d !== 'object') return false;
  const obj = d as Record<string, unknown>;
  return typeof obj.decision === 'string' && typeof obj.attempt_number === 'number';
}

function isSummarizerDetails(d: unknown): d is SummarizerDetails {
  if (!d || typeof d !== 'object') return false;
  const obj = d as Record<string, unknown>;
  return typeof obj.summary_preview === 'string' && typeof obj.old_message_count === 'number';
}

// Component to render agent-specific details
function AgentDetailsPanel({ agent, details }: { agent: AgentType; details: unknown }) {
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
                  m.complexity === 'trivial' && 'bg-gray-500/10 text-gray-500',
                  m.complexity === 'simple' && 'bg-green-500/10 text-green-500',
                  m.complexity === 'moderate' && 'bg-blue-500/10 text-blue-500',
                  m.complexity === 'complex' && 'bg-orange-500/10 text-orange-500',
                  m.complexity === 'context_heavy' && 'bg-red-500/10 text-red-500',
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
            <span>•</span>
            <span>${d.cost_usd.toFixed(4)}</span>
            <span>•</span>
            <span>{d.model}</span>
            {d.is_retry && <span className="text-yellow-500">• Retry</span>}
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

function AgentBadge({ agent, isActive }: { agent: AgentType; isActive?: boolean }) {
  const display = AGENT_DISPLAY[agent];
  const colorClasses = AGENT_COLORS[agent];

  return (
    <div
      className={cn(
        'inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium border',
        colorClasses,
        isActive && 'ring-2 ring-offset-2 ring-offset-background'
      )}
    >
      {AGENT_ICONS[agent]}
      <span>{display.label}</span>
      {isActive && <Loader2 className="h-3 w-3 animate-spin" />}
    </div>
  );
}

function QAResultBadge({ decision, retryCount }: { decision: QADecision; retryCount?: number }) {
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

function MilestoneCard({ milestone, isExpanded, onToggle }: {
  milestone: MilestoneInfo;
  isExpanded: boolean;
  onToggle: () => void;
}) {
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
              milestone.complexity === 'trivial' && 'bg-gray-500/10 text-gray-500',
              milestone.complexity === 'simple' && 'bg-green-500/10 text-green-500',
              milestone.complexity === 'moderate' && 'bg-blue-500/10 text-blue-500',
              milestone.complexity === 'complex' && 'bg-orange-500/10 text-orange-500',
              milestone.complexity === 'context_heavy' && 'bg-red-500/10 text-red-500',
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

// Activity log item component
function ActivityLogItem({ activity, isLatest }: { activity: AgentActivity; isLatest: boolean }) {
  const [isExpanded, setIsExpanded] = useState(isLatest && activity.status === 'completed' && !!activity.details);
  const colorClasses = AGENT_COLORS[activity.agent];
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
                AGENT_COLORS[currentActivity.agent]
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
