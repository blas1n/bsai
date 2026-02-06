'use client';

import { useCallback } from 'react';
import { cn } from '@/lib/utils';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Pause,
  Play,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { TaskStatus, MilestoneStatus } from '@/types/session';

// Task item in the execution plan
export interface ExecutionTask {
  id: string;
  title: string;
  status: TaskStatus | MilestoneStatus;
  featureId?: string;
  estimatedDuration?: number;
}

// Feature grouping for tasks
export interface ExecutionFeature {
  id: string;
  title: string;
  tasks: ExecutionTask[];
  isExpanded?: boolean;
}

// Overall execution state
export interface ExecutionState {
  isPaused: boolean;
  pauseReason?: string;
  currentTaskId?: string;
  completedCount: number;
  failedCount: number;
  pendingCount: number;
  totalCount: number;
}

interface ExecutionProgressProps {
  state: ExecutionState;
  tasks: ExecutionTask[];
  features?: ExecutionFeature[];
  onPause?: () => void;
  onResume?: () => void;
  onFeatureToggle?: (featureId: string) => void;
  className?: string;
}

// Status icon mapping
function getStatusIcon(status: TaskStatus | MilestoneStatus) {
  switch (status) {
    case 'completed':
    case 'passed':
      return <CheckCircle2 className="h-4 w-4 text-green-500" />;
    case 'failed':
      return <XCircle className="h-4 w-4 text-red-500" />;
    case 'in_progress':
      return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
    case 'paused':
      return <Pause className="h-4 w-4 text-yellow-500" />;
    case 'cancelled':
      return <XCircle className="h-4 w-4 text-gray-500" />;
    case 'pending':
    default:
      return <Clock className="h-4 w-4 text-muted-foreground" />;
  }
}

// Status badge variant mapping
function getStatusVariant(status: TaskStatus | MilestoneStatus) {
  switch (status) {
    case 'completed':
    case 'passed':
      return 'success' as const;
    case 'failed':
      return 'destructive' as const;
    case 'in_progress':
      return 'info' as const;
    case 'paused':
      return 'warning' as const;
    default:
      return 'secondary' as const;
  }
}

// Task list item component
function TaskListItem({
  task,
  isCurrent,
}: {
  task: ExecutionTask;
  isCurrent: boolean;
}) {
  return (
    <div
      className={cn(
        'flex items-center gap-3 px-3 py-2 rounded-md transition-colors',
        isCurrent && 'bg-primary/5 border border-primary/20',
        !isCurrent && 'hover:bg-muted/50'
      )}
    >
      {getStatusIcon(task.status)}
      <span
        className={cn(
          'flex-1 text-sm truncate',
          isCurrent && 'font-medium',
          task.status === 'completed' || task.status === 'passed'
            ? 'text-muted-foreground line-through'
            : ''
        )}
      >
        {task.title}
      </span>
      {isCurrent && (
        <Badge variant="info" className="text-xs">
          Current
        </Badge>
      )}
    </div>
  );
}

// Feature group component with collapsible tasks
function FeatureGroup({
  feature,
  currentTaskId,
  onToggle,
}: {
  feature: ExecutionFeature;
  currentTaskId?: string;
  onToggle?: () => void;
}) {
  const completedCount = feature.tasks.filter(
    (t) => t.status === 'completed' || t.status === 'passed'
  ).length;
  const progress = (completedCount / feature.tasks.length) * 100;

  return (
    <div className="border rounded-lg">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 p-3 text-left hover:bg-muted/50 transition-colors"
      >
        {feature.isExpanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
        <span className="flex-1 text-sm font-medium">{feature.title}</span>
        <span className="text-xs text-muted-foreground">
          {completedCount}/{feature.tasks.length}
        </span>
        <Progress value={progress} className="w-20 h-2" />
      </button>
      {feature.isExpanded && (
        <div className="px-2 pb-2 space-y-1">
          {feature.tasks.map((task) => (
            <TaskListItem
              key={task.id}
              task={task}
              isCurrent={task.id === currentTaskId}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function ExecutionProgress({
  state,
  tasks,
  features,
  onPause,
  onResume,
  onFeatureToggle,
  className,
}: ExecutionProgressProps) {
  const { isPaused, pauseReason, currentTaskId, completedCount, failedCount, pendingCount, totalCount } =
    state;

  // Calculate overall progress percentage
  const progressPercent = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;

  // Find current task
  const currentTask = tasks.find((t) => t.id === currentTaskId);

  const handlePauseResume = useCallback(() => {
    if (isPaused) {
      onResume?.();
    } else {
      onPause?.();
    }
  }, [isPaused, onPause, onResume]);

  return (
    <Card className={cn('w-full', className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Execution Progress</CardTitle>
          <Button
            variant={isPaused ? 'default' : 'outline'}
            size="sm"
            onClick={handlePauseResume}
            className="gap-2"
          >
            {isPaused ? (
              <>
                <Play className="h-4 w-4" />
                Resume
              </>
            ) : (
              <>
                <Pause className="h-4 w-4" />
                Pause
              </>
            )}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Pause Banner */}
        {isPaused && (
          <div className="flex items-center gap-2 p-3 rounded-md bg-yellow-500/10 border border-yellow-500/20">
            <AlertTriangle className="h-4 w-4 text-yellow-500 flex-shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-medium text-yellow-600 dark:text-yellow-400">
                Execution Paused
              </p>
              {pauseReason && (
                <p className="text-xs text-muted-foreground mt-0.5">
                  {pauseReason}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Overall Progress Bar */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Overall Progress</span>
            <span className="font-medium">{Math.round(progressPercent)}%</span>
          </div>
          <Progress value={progressPercent} className="h-2" />
        </div>

        {/* Stats Row */}
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="h-4 w-4 text-green-500" />
            <span className="text-muted-foreground">Completed:</span>
            <span className="font-medium">{completedCount}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <XCircle className="h-4 w-4 text-red-500" />
            <span className="text-muted-foreground">Failed:</span>
            <span className="font-medium">{failedCount}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <span className="text-muted-foreground">Pending:</span>
            <span className="font-medium">{pendingCount}</span>
          </div>
        </div>

        {/* Current Task Indicator */}
        {currentTask && (
          <div className="p-3 rounded-md bg-primary/5 border border-primary/20">
            <div className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 text-primary animate-spin" />
              <span className="text-sm font-medium">Currently executing:</span>
            </div>
            <p className="text-sm text-muted-foreground mt-1 truncate">
              {currentTask.title}
            </p>
          </div>
        )}

        {/* Feature-level Progress (if features provided) */}
        {features && features.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-muted-foreground">
              Features
            </h4>
            <div className="space-y-2">
              {features.map((feature) => (
                <FeatureGroup
                  key={feature.id}
                  feature={feature}
                  currentTaskId={currentTaskId}
                  onToggle={() => onFeatureToggle?.(feature.id)}
                />
              ))}
            </div>
          </div>
        )}

        {/* Task List (if no features or flat view) */}
        {(!features || features.length === 0) && tasks.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-muted-foreground">Tasks</h4>
            <div className="space-y-1 max-h-64 overflow-y-auto">
              {tasks.map((task) => (
                <TaskListItem
                  key={task.id}
                  task={task}
                  isCurrent={task.id === currentTaskId}
                />
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
