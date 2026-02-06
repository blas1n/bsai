'use client';

import { useCallback } from 'react';
import { cn } from '@/lib/utils';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import {
  Pause,
  Play,
  Edit,
  Square,
  Clock,
  CheckCircle2,
  ArrowRight,
} from 'lucide-react';

// Task preview for upcoming tasks
export interface TaskPreview {
  id: string;
  title: string;
  estimatedDuration?: number;
}

// Pause state information
export interface PauseState {
  reason: string;
  completedCount: number;
  totalCount: number;
  nextTasks: TaskPreview[];
  pausedAt?: string;
}

interface PauseDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pauseState: PauseState;
  onContinue?: () => void;
  onModifyPlan?: () => void;
  onStop?: () => void;
  className?: string;
}

export function PauseDialog({
  open,
  onOpenChange,
  pauseState,
  onContinue,
  onModifyPlan,
  onStop,
  className,
}: PauseDialogProps) {
  const { reason, completedCount, totalCount, nextTasks, pausedAt } = pauseState;

  // Calculate progress percentage
  const progressPercent = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;

  const handleContinue = useCallback(() => {
    onContinue?.();
    onOpenChange(false);
  }, [onContinue, onOpenChange]);

  const handleModifyPlan = useCallback(() => {
    onModifyPlan?.();
    onOpenChange(false);
  }, [onModifyPlan, onOpenChange]);

  const handleStop = useCallback(() => {
    onStop?.();
    onOpenChange(false);
  }, [onStop, onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn('sm:max-w-md', className)}>
        <DialogHeader>
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-full bg-yellow-500/10">
              <Pause className="h-5 w-5 text-yellow-500" />
            </div>
            <DialogTitle>Execution Paused</DialogTitle>
          </div>
          <DialogDescription className="pt-2">{reason}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Progress Section */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-1.5 text-muted-foreground">
                <CheckCircle2 className="h-4 w-4 text-green-500" />
                Progress
              </span>
              <span className="font-medium">
                {completedCount} / {totalCount} tasks ({Math.round(progressPercent)}%)
              </span>
            </div>
            <Progress value={progressPercent} className="h-2" />
          </div>

          {/* Paused Time */}
          {pausedAt && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Clock className="h-4 w-4" />
              <span>Paused at {new Date(pausedAt).toLocaleTimeString()}</span>
            </div>
          )}

          {/* Next Tasks Section */}
          {nextTasks.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium flex items-center gap-1.5">
                <ArrowRight className="h-4 w-4 text-muted-foreground" />
                Next Tasks
              </h4>
              <div className="space-y-1.5 pl-6">
                {nextTasks.map((task, index) => (
                  <div
                    key={task.id}
                    className="flex items-center gap-2 text-sm"
                  >
                    <Badge
                      variant="outline"
                      className="h-5 w-5 p-0 justify-center text-xs"
                    >
                      {index + 1}
                    </Badge>
                    <span className="truncate text-muted-foreground">
                      {task.title}
                    </span>
                    {task.estimatedDuration && (
                      <span className="text-xs text-muted-foreground/60 flex-shrink-0">
                        ~{task.estimatedDuration}s
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="flex-col sm:flex-row gap-2">
          <Button
            variant="destructive"
            onClick={handleStop}
            className="gap-2 sm:order-1"
          >
            <Square className="h-4 w-4" />
            Stop
          </Button>
          <Button
            variant="outline"
            onClick={handleModifyPlan}
            className="gap-2 sm:order-2"
          >
            <Edit className="h-4 w-4" />
            Modify Plan
          </Button>
          <Button
            variant="default"
            onClick={handleContinue}
            className="gap-2 sm:order-3"
          >
            <Play className="h-4 w-4" />
            Continue
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
