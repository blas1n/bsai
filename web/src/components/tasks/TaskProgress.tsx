'use client';

import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { CheckCircle2, Clock, XCircle, Loader2, PauseCircle } from 'lucide-react';

interface TaskLike {
  id: string;
  original_request: string;
  status: string;
  final_result: string | null;
}

interface TaskProgressProps {
  task: TaskLike;
  progress?: number;
  currentMilestone?: string;
}

function getStatusIcon(status: string) {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="h-5 w-5 text-green-500" />;
    case 'failed':
      return <XCircle className="h-5 w-5 text-red-500" />;
    case 'in_progress':
      return <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />;
    case 'paused':
      return <PauseCircle className="h-5 w-5 text-yellow-500" />;
    default:
      return <Clock className="h-5 w-5 text-muted-foreground" />;
  }
}

function getStatusVariant(status: string) {
  switch (status) {
    case 'completed':
      return 'success';
    case 'failed':
      return 'destructive';
    case 'in_progress':
      return 'info';
    case 'paused':
      return 'warning';
    default:
      return 'secondary';
  }
}

export function TaskProgress({ task, progress = 0, currentMilestone }: TaskProgressProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          {getStatusIcon(task.status)}
          <span className="font-medium truncate max-w-[300px]">
            {task.original_request}
          </span>
        </div>
        <Badge variant={getStatusVariant(task.status)}>
          {task.status.replace('_', ' ')}
        </Badge>
      </div>

      {task.status === 'in_progress' && (
        <>
          <Progress value={progress * 100} className="h-2" />
          <div className="flex justify-between text-sm text-muted-foreground">
            <span>{currentMilestone || 'Processing...'}</span>
            <span>{Math.round(progress * 100)}%</span>
          </div>
        </>
      )}

      {task.final_result && (
        <div className="mt-2 p-3 bg-muted rounded-md">
          <p className="text-sm whitespace-pre-wrap">{task.final_result}</p>
        </div>
      )}
    </div>
  );
}
