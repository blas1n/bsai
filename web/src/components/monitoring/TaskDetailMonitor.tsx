'use client';

import { useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  TaskDetailResponse,
  MilestoneResponse,
  AgentStepResponse,
  AgentCostBreakdown,
} from '@/lib/api';
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
} from 'lucide-react';

interface TaskDetailMonitorProps {
  task: TaskDetailResponse;
  className?: string;
}

const formatDuration = (ms: number | null): string => {
  if (!ms) return '-';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
};

const formatCost = (cost: string): string => {
  const value = parseFloat(cost);
  if (value < 0.01) return `$${value.toFixed(4)}`;
  return `$${value.toFixed(2)}`;
};

const getAgentIcon = (agentType: string) => {
  switch (agentType) {
    case 'architect':
      return <Brain className="h-4 w-4" />;
    case 'worker':
      return <Zap className="h-4 w-4" />;
    case 'qa':
      return <FileCheck className="h-4 w-4" />;
    case 'responder':
      return <MessageSquare className="h-4 w-4" />;
    default:
      return <Activity className="h-4 w-4" />;
  }
};

const getAgentColor = (agentType: string): string => {
  switch (agentType) {
    case 'architect':
      return 'bg-blue-500';
    case 'worker':
      return 'bg-green-500';
    case 'qa':
      return 'bg-orange-500';
    case 'responder':
      return 'bg-teal-500';
    default:
      return 'bg-gray-500';
  }
};

const getStatusBadge = (status: string) => {
  switch (status) {
    case 'completed':
    case 'passed':
      return (
        <Badge variant="default" className="bg-green-500">
          <CheckCircle2 className="h-3 w-3 mr-1" /> Completed
        </Badge>
      );
    case 'failed':
      return (
        <Badge variant="destructive">
          <XCircle className="h-3 w-3 mr-1" /> Failed
        </Badge>
      );
    case 'started':
    case 'in_progress':
      return (
        <Badge variant="secondary">
          <Loader2 className="h-3 w-3 mr-1 animate-spin" /> Running
        </Badge>
      );
    default:
      return <Badge variant="outline">{status}</Badge>;
  }
};

function AgentStepTimeline({ steps }: { steps: AgentStepResponse[] }) {
  if (steps.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-4">
        No agent steps recorded yet
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {steps.map((step, index) => (
        <div
          key={step.id}
          className="flex items-center gap-3 p-3 rounded-lg border bg-card"
        >
          <div className={`p-2 rounded-full ${getAgentColor(step.agent_type)} text-white`}>
            {getAgentIcon(step.agent_type)}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium capitalize">
                {step.agent_type.replace('_', ' ')}
              </span>
              {getStatusBadge(step.status)}
            </div>
            {step.output_summary && (
              <p className="text-sm text-muted-foreground truncate mt-1">
                {step.output_summary}
              </p>
            )}
            {step.error_message && (
              <p className="text-sm text-destructive mt-1">
                {step.error_message}
              </p>
            )}
          </div>
          <div className="text-right text-sm text-muted-foreground">
            <div className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {formatDuration(step.duration_ms)}
            </div>
            <div className="flex items-center gap-1">
              <Coins className="h-3 w-3" />
              {formatCost(step.cost_usd)}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function MilestoneList({ milestones }: { milestones: MilestoneResponse[] }) {
  if (milestones.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-4">
        No milestones yet
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {milestones.map((milestone) => (
        <div
          key={milestone.id}
          className="flex items-start gap-3 p-3 rounded-lg border bg-card"
        >
          <div className="flex items-center justify-center w-8 h-8 rounded-full bg-primary text-primary-foreground text-sm font-medium">
            {milestone.sequence_number}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium">{milestone.title || `Milestone ${milestone.sequence_number}`}</span>
              {getStatusBadge(milestone.status)}
              <Badge variant="outline" className="text-xs">
                {milestone.complexity}
              </Badge>
            </div>
            {milestone.description && (
              <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                {milestone.description}
              </p>
            )}
            <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
              {milestone.selected_llm && (
                <span>Model: {milestone.selected_llm}</span>
              )}
              <span>{milestone.input_tokens + milestone.output_tokens} tokens</span>
              <span>{formatCost(milestone.cost_usd)}</span>
              {milestone.duration_ms && (
                <span>{formatDuration(milestone.duration_ms)}</span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function CostBreakdownChart({ breakdown }: { breakdown: Record<string, AgentCostBreakdown> }) {
  const agents = Object.entries(breakdown);

  if (agents.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-4">
        No cost data yet
      </p>
    );
  }

  const totalCost = agents.reduce(
    (sum, [, data]) => sum + parseFloat(data.total_cost_usd),
    0
  );

  return (
    <div className="space-y-3">
      {agents.map(([agentType, data]) => {
        const percentage = totalCost > 0
          ? (parseFloat(data.total_cost_usd) / totalCost) * 100
          : 0;

        return (
          <div key={agentType} className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <div className={`p-1 rounded ${getAgentColor(agentType)} text-white`}>
                  {getAgentIcon(agentType)}
                </div>
                <span className="capitalize">{agentType.replace('_', ' ')}</span>
              </div>
              <span className="font-medium">{formatCost(data.total_cost_usd)}</span>
            </div>
            <Progress value={percentage} className="h-2" />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{data.step_count} calls</span>
              <span>
                {data.total_input_tokens + data.total_output_tokens} tokens
              </span>
              <span>{formatDuration(data.total_duration_ms)}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function TaskDetailMonitor({ task, className = '' }: TaskDetailMonitorProps) {
  const totalTokens = useMemo(() => {
    return task.agent_steps.reduce(
      (sum, step) => sum + step.input_tokens + step.output_tokens,
      0
    );
  }, [task.agent_steps]);

  const totalCost = useMemo(() => {
    return Object.values(task.cost_breakdown).reduce(
      (sum, data) => sum + parseFloat(data.total_cost_usd),
      0
    );
  }, [task.cost_breakdown]);

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Progress</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {Math.round(task.progress * 100)}%
            </div>
            <Progress value={task.progress * 100} className="mt-2" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Duration</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold flex items-center gap-2">
              <Clock className="h-5 w-5 text-muted-foreground" />
              {formatDuration(task.total_duration_ms)}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {task.agent_steps.length} agent steps
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Tokens Used</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold flex items-center gap-2">
              <Activity className="h-5 w-5 text-muted-foreground" />
              {totalTokens.toLocaleString()}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {task.milestones.length} milestones
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Total Cost</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold flex items-center gap-2">
              <Coins className="h-5 w-5 text-muted-foreground" />
              {formatCost(totalCost.toFixed(6))}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {Object.keys(task.cost_breakdown).length} agents used
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Agent Timeline & Cost Breakdown */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Agent Execution Timeline</CardTitle>
            <CardDescription>
              Step-by-step execution history
            </CardDescription>
          </CardHeader>
          <CardContent className="max-h-96 overflow-y-auto">
            <AgentStepTimeline steps={task.agent_steps} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Cost Breakdown by Agent</CardTitle>
            <CardDescription>
              Resource usage per agent type
            </CardDescription>
          </CardHeader>
          <CardContent>
            <CostBreakdownChart breakdown={task.cost_breakdown} />
          </CardContent>
        </Card>
      </div>

      {/* Milestones */}
      <Card>
        <CardHeader>
          <CardTitle>Milestones</CardTitle>
          <CardDescription>
            Task breakdown and completion status
          </CardDescription>
        </CardHeader>
        <CardContent className="max-h-96 overflow-y-auto">
          <MilestoneList milestones={task.milestones} />
        </CardContent>
      </Card>
    </div>
  );
}
