'use client';

import { useMemo, useRef, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Button } from '@/components/ui/button';
import {
  Clock,
  Coins,
  Activity,
  CheckCircle2,
  XCircle,
  Loader2,
  Zap,
  Brain,
  FileCheck,
  MessageSquare,
  Minimize2,
  PauseCircle,
  PlayCircle,
  Terminal,
  Eye,
} from 'lucide-react';
import { AgentActivity, AgentType, MilestoneInfo } from '@/types/chat';
import { BreakpointHitPayload } from '@/types/websocket';

interface LiveDetailPanelProps {
  milestones: MilestoneInfo[];
  agentHistory: AgentActivity[];
  currentActivity: AgentActivity | null;
  isStreaming: boolean;
  breakpoint: BreakpointHitPayload | null;
  onResume?: () => void;
  onReject?: () => void;
  isBreakpointLoading?: boolean;
  streamingChunks?: string[];
  streamingAgent?: AgentType;
  breakpointEnabled?: boolean;
  onBreakpointToggle?: (enabled: boolean) => void;
}

const formatDuration = (startedAt?: string, completedAt?: string): string => {
  if (!startedAt) return '-';
  const start = new Date(startedAt).getTime();
  const end = completedAt ? new Date(completedAt).getTime() : Date.now();
  const ms = end - start;
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
};

const getAgentIcon = (agentType: string) => {
  switch (agentType) {
    case 'conductor':
      return <Brain className="h-4 w-4" />;
    case 'meta_prompter':
      return <MessageSquare className="h-4 w-4" />;
    case 'worker':
      return <Zap className="h-4 w-4" />;
    case 'qa':
      return <FileCheck className="h-4 w-4" />;
    case 'summarizer':
      return <Minimize2 className="h-4 w-4" />;
    case 'responder':
      return <MessageSquare className="h-4 w-4" />;
    default:
      return <Activity className="h-4 w-4" />;
  }
};

const getAgentColor = (agentType: string): string => {
  switch (agentType) {
    case 'conductor':
      return 'bg-purple-500';
    case 'meta_prompter':
      return 'bg-blue-500';
    case 'worker':
      return 'bg-green-500';
    case 'qa':
      return 'bg-orange-500';
    case 'summarizer':
      return 'bg-cyan-500';
    case 'responder':
      return 'bg-pink-500';
    default:
      return 'bg-gray-500';
  }
};

const getStatusBadge = (status: string) => {
  switch (status) {
    case 'completed':
    case 'passed':
      return (
        <Badge variant="default" className="bg-green-500 text-xs">
          <CheckCircle2 className="h-3 w-3 mr-1" /> Done
        </Badge>
      );
    case 'failed':
      return (
        <Badge variant="destructive" className="text-xs">
          <XCircle className="h-3 w-3 mr-1" /> Failed
        </Badge>
      );
    case 'running':
    case 'in_progress':
      return (
        <Badge variant="secondary" className="text-xs">
          <Loader2 className="h-3 w-3 mr-1 animate-spin" /> Running
        </Badge>
      );
    case 'pending':
      return (
        <Badge variant="outline" className="text-xs">
          <Clock className="h-3 w-3 mr-1" /> Pending
        </Badge>
      );
    default:
      return <Badge variant="outline" className="text-xs">{status}</Badge>;
  }
};

export function LiveDetailPanel({
  milestones,
  agentHistory,
  currentActivity,
  isStreaming,
  breakpoint,
  onResume,
  onReject,
  isBreakpointLoading = false,
  streamingChunks = [],
  streamingAgent,
  breakpointEnabled = false,
  onBreakpointToggle,
}: LiveDetailPanelProps) {
  const streamingRef = useRef<HTMLDivElement>(null);

  // Auto-scroll streaming content
  useEffect(() => {
    if (streamingRef.current) {
      streamingRef.current.scrollTop = streamingRef.current.scrollHeight;
    }
  }, [streamingChunks]);

  // Calculate stats
  const stats = useMemo(() => {
    const completed = milestones.filter((m) => m.status === 'passed').length;
    const total = milestones.length;
    const progress = total > 0 ? (completed / total) * 100 : 0;

    let totalTokens = 0;
    let totalCost = 0;
    milestones.forEach((m) => {
      if (m.usage) {
        totalTokens += (m.usage.inputTokens || 0) + (m.usage.outputTokens || 0);
        totalCost += m.usage.costUsd || 0;
      }
    });

    // Estimate streaming tokens (rough: ~4 chars per token)
    const streamingText = streamingChunks.join('');
    const estimatedStreamingTokens = Math.ceil(streamingText.length / 4);

    return { completed, total, progress, totalTokens, totalCost, estimatedStreamingTokens };
  }, [milestones, streamingChunks]);

  // Get streaming text
  const streamingText = useMemo(() => streamingChunks.join(''), [streamingChunks]);

  return (
    <div className="h-full flex flex-col bg-background border-l">
      {/* Header */}
      <div className="p-4 border-b">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Live Monitor
            {isStreaming && (
              <span className="flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-2 w-2 rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
            )}
          </h2>
          {onBreakpointToggle && (
            <Button
              variant={breakpointEnabled ? 'default' : 'outline'}
              size="sm"
              onClick={() => onBreakpointToggle(!breakpointEnabled)}
              className={breakpointEnabled ? 'bg-amber-500 hover:bg-amber-600' : ''}
              title={breakpointEnabled ? 'Breakpoints enabled - will pause before QA' : 'Enable breakpoints to pause before QA'}
            >
              <PauseCircle className="h-4 w-4 mr-1" />
              {breakpointEnabled ? 'BP On' : 'BP Off'}
            </Button>
          )}
        </div>
        {breakpointEnabled && !breakpoint && (
          <p className="text-xs text-amber-600 dark:text-amber-400 mt-2">
            Workflow will pause before QA verification
          </p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Breakpoint Alert */}
        {breakpoint && (
          <Card className="border-amber-500 bg-amber-50 dark:bg-amber-950">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium flex items-center gap-2 text-amber-700 dark:text-amber-300">
                <PauseCircle className="h-4 w-4" />
                Breakpoint Reached
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-sm text-amber-600 dark:text-amber-400 flex items-center gap-2">
                <span>Paused at</span>
                <Badge variant="outline">{breakpoint.node_name}</Badge>
              </div>
              <div className="text-xs text-muted-foreground">
                Milestone {breakpoint.current_state.current_milestone_index + 1} of {breakpoint.current_state.total_milestones}
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={onResume}
                  disabled={isBreakpointLoading}
                  className="flex-1"
                >
                  {isBreakpointLoading ? (
                    <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                  ) : (
                    <PlayCircle className="h-3 w-3 mr-1" />
                  )}
                  Continue
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={onReject}
                  disabled={isBreakpointLoading}
                >
                  <XCircle className="h-3 w-3 mr-1" />
                  Stop
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Progress Summary */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Progress</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Milestones</span>
              <span className="font-medium">{stats.completed} / {stats.total}</span>
            </div>
            <Progress value={stats.progress} className="h-2" />
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">Tokens:</span>
                <span className="font-medium">
                  {stats.totalTokens.toLocaleString()}
                  {stats.estimatedStreamingTokens > 0 && (
                    <span className="text-blue-500 animate-pulse">
                      {' +'}~{stats.estimatedStreamingTokens}
                    </span>
                  )}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Coins className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">Cost:</span>
                <span className="font-medium">${stats.totalCost.toFixed(4)}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Live LLM Output */}
        {streamingText && streamingAgent && (
          <Card className="border-green-500">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Eye className="h-4 w-4 text-green-500" />
                <span>Live Output</span>
                <Badge variant="secondary" className="text-xs capitalize">
                  {streamingAgent.replace('_', ' ')}
                </Badge>
                <span className="text-xs text-muted-foreground ml-auto">
                  ~{stats.estimatedStreamingTokens} tokens
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div
                ref={streamingRef}
                className="max-h-48 overflow-y-auto bg-muted/50 rounded-md p-3 font-mono text-xs whitespace-pre-wrap break-words"
              >
                {streamingText}
                <span className="animate-pulse text-green-500">▌</span>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Current Activity */}
        {currentActivity && (
          <Card className="border-blue-500">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                Current Activity
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-full ${getAgentColor(currentActivity.agent)} text-white`}>
                  {getAgentIcon(currentActivity.agent)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-medium capitalize">
                    {currentActivity.agent.replace('_', ' ')}
                  </div>
                  <p className="text-sm text-muted-foreground truncate">
                    {currentActivity.message}
                  </p>
                </div>
                <div className="text-xs text-muted-foreground">
                  {formatDuration(currentActivity.startedAt)}
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Agent Timeline */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Agent Timeline</CardTitle>
          </CardHeader>
          <CardContent>
            {agentHistory.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                No activity yet
              </p>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {agentHistory.slice().reverse().map((activity, index) => (
                  <div
                    key={`${activity.agent}-${index}`}
                    className="flex items-center gap-2 p-2 rounded-lg bg-muted/50 text-sm"
                  >
                    <div className={`p-1.5 rounded-full ${getAgentColor(activity.agent)} text-white`}>
                      {getAgentIcon(activity.agent)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium capitalize text-xs">
                          {activity.agent.replace('_', ' ')}
                        </span>
                        {getStatusBadge(activity.status)}
                      </div>
                      <p className="text-xs text-muted-foreground truncate">
                        {activity.message}
                      </p>
                    </div>
                    <div className="text-xs text-muted-foreground whitespace-nowrap">
                      {formatDuration(activity.startedAt, activity.completedAt)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Milestones */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Milestones</CardTitle>
          </CardHeader>
          <CardContent>
            {milestones.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                No milestones yet
              </p>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {milestones.map((milestone) => (
                  <div
                    key={milestone.id}
                    className="flex items-start gap-2 p-2 rounded-lg bg-muted/50"
                  >
                    <div className="flex items-center justify-center w-6 h-6 rounded-full bg-primary text-primary-foreground text-xs font-medium flex-shrink-0">
                      {milestone.sequenceNumber}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-xs truncate">
                          {milestone.title || `Milestone ${milestone.sequenceNumber}`}
                        </span>
                        {getStatusBadge(milestone.status)}
                      </div>
                      {milestone.description && (
                        <p className="text-xs text-muted-foreground line-clamp-1">
                          {milestone.description}
                        </p>
                      )}
                      {milestone.usage && (
                        <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                          <span>{(milestone.usage.inputTokens || 0) + (milestone.usage.outputTokens || 0)} tokens</span>
                          <span>${milestone.usage.costUsd?.toFixed(4) || '0'}</span>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
