'use client';

import React, { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  AlertCircle,
  CheckCircle,
  Clock,
  MessageSquare,
  Play,
  XCircle,
  Loader2,
} from 'lucide-react';
import { BreakpointHitPayload } from '@/types/websocket';

interface BreakpointModalProps {
  open: boolean;
  breakpoint: BreakpointHitPayload | null;
  onResume: (userInput?: string) => void;
  onReject: (reason?: string) => void;
  isLoading?: boolean;
}

export function BreakpointModal({
  open,
  breakpoint,
  onResume,
  onReject,
  isLoading = false,
}: BreakpointModalProps) {
  const [userInput, setUserInput] = useState('');

  if (!breakpoint) return null;

  const { current_state, node_name, agent_type } = breakpoint;
  const currentMilestone = current_state.milestones[current_state.current_milestone_index];

  const handleResume = () => {
    onResume(userInput || undefined);
    setUserInput('');
  };

  const handleReject = () => {
    // With feedback: re-run worker with the feedback
    // Without feedback: cancel the task
    onReject(userInput || undefined);
    setUserInput('');
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'passed':
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'failed':
        return <XCircle className="h-4 w-4 text-red-500" />;
      case 'in_progress':
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
      default:
        return <Clock className="h-4 w-4 text-gray-400" />;
    }
  };

  return (
    <Dialog open={open} onOpenChange={() => {}}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-amber-500" />
            Breakpoint Reached
          </DialogTitle>
          <DialogDescription asChild>
            <div className="text-sm text-muted-foreground">
              The workflow has paused at <Badge variant="outline">{node_name}</Badge>
              {' '}awaiting your review before proceeding.
            </div>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Current State Summary */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <MessageSquare className="h-4 w-4" />
                Agent: <span className="capitalize">{agent_type.replace('_', ' ')}</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Progress</span>
                <span className="font-medium">
                  Milestone {current_state.current_milestone_index + 1} of {current_state.total_milestones}
                </span>
              </div>

              {currentMilestone && (
                <div className="p-3 bg-muted rounded-lg">
                  <div className="flex items-center gap-2 mb-1">
                    {getStatusIcon(currentMilestone.status)}
                    <span className="font-medium">Current Milestone</span>
                    <Badge variant="secondary" className="text-xs">
                      {currentMilestone.status}
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {currentMilestone.description}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Last Worker Output */}
          {current_state.last_worker_output && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Last Worker Output</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-32 overflow-y-auto">
                  <pre className="text-xs whitespace-pre-wrap font-mono bg-muted p-3 rounded">
                    {current_state.last_worker_output}
                  </pre>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Last QA Result */}
          {current_state.last_qa_result && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  QA Result
                  <Badge
                    variant={current_state.last_qa_result.decision === 'pass' ? 'default' : 'destructive'}
                    className="text-xs"
                  >
                    {current_state.last_qa_result.decision}
                  </Badge>
                </CardTitle>
              </CardHeader>
              {current_state.last_qa_result.feedback && (
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    {current_state.last_qa_result.feedback}
                  </p>
                </CardContent>
              )}
            </Card>
          )}

          <hr className="border-t border-border" />

          {/* User Input */}
          <div className="space-y-2">
            <label className="text-sm font-medium">
              Feedback for the agent (optional)
            </label>
            <Textarea
              placeholder="Enter feedback to modify the output, or leave empty to continue as-is..."
              value={userInput}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setUserInput(e.target.value)}
              className="min-h-20"
              disabled={isLoading}
            />
            {userInput && (
              <p className="text-xs text-muted-foreground">
                With feedback: &quot;Continue&quot; applies changes to QA, &quot;Reject&quot; re-runs worker with your feedback.
              </p>
            )}
          </div>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={handleReject}
            disabled={isLoading}
            className={userInput ? 'text-amber-600 hover:text-amber-600' : 'text-destructive hover:text-destructive'}
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : userInput ? (
              <Play className="h-4 w-4 mr-2" />
            ) : (
              <XCircle className="h-4 w-4 mr-2" />
            )}
            {userInput ? 'Retry with Feedback' : 'Cancel Task'}
          </Button>
          <Button onClick={handleResume} disabled={isLoading}>
            {isLoading ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Play className="h-4 w-4 mr-2" />
            )}
            {userInput ? 'Continue to QA' : 'Continue'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
