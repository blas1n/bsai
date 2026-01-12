'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { TaskDetailMonitor } from '@/components/monitoring/TaskDetailMonitor';
import { useAuth } from '@/hooks/useAuth';
import { api, TaskDetailResponse } from '@/lib/api';
import { useWebSocket } from '@/hooks/useWebSocket';
import { WSMessageType, LLMChunkPayload, MilestoneProgressPayload } from '@/types/websocket';
import { formatRelativeTime } from '@/lib/utils';

export default function TaskDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const taskId = params.id as string;
  const sessionId = searchParams.get('session') || '';
  const { accessToken } = useAuth();

  const [task, setTask] = useState<TaskDetailResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [streamingContent, setStreamingContent] = useState<string>('');
  const [currentAgent, setCurrentAgent] = useState<string>('');

  const handleWebSocketMessage = useCallback(
    (message: any) => {
      if (message.payload?.task_id !== taskId) return;

      switch (message.type) {
        case WSMessageType.LLM_CHUNK:
          const chunk = message.payload as LLMChunkPayload;
          setStreamingContent((prev) => prev + chunk.chunk);
          setCurrentAgent(chunk.agent);
          break;

        case WSMessageType.LLM_COMPLETE:
          setStreamingContent('');
          fetchTask();
          break;

        case WSMessageType.MILESTONE_PROGRESS:
          const progress = message.payload as MilestoneProgressPayload;
          setTask((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              milestones: prev.milestones.map((m) =>
                m.id === progress.milestone_id ? { ...m, status: progress.status } : m
              ),
            };
          });
          break;

        case WSMessageType.TASK_COMPLETED:
          fetchTask();
          break;

        case WSMessageType.TASK_FAILED:
          fetchTask();
          break;
      }
    },
    [taskId]
  );

  const { isConnected } = useWebSocket({
    sessionId,
    token: accessToken,
    onMessage: handleWebSocketMessage,
  });

  const fetchTask = async () => {
    if (!sessionId) return;
    setIsLoading(true);
    try {
      const data = await api.getTask(sessionId, taskId);
      setTask(data);
      setError(null);
    } catch (err) {
      setError('Failed to fetch task');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!confirm('Are you sure you want to cancel this task?')) return;
    try {
      await api.cancelTask(sessionId, taskId);
      fetchTask();
    } catch (err) {
      console.error('Failed to cancel task:', err);
    }
  };

  useEffect(() => {
    fetchTask();
  }, [taskId, sessionId]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-pulse text-muted-foreground">Loading task...</div>
      </div>
    );
  }

  if (error || !task) {
    return (
      <div className="text-center py-12">
        <p className="text-destructive mb-4">{error || 'Task not found'}</p>
        <Link href={sessionId ? `/sessions/${sessionId}` : '/sessions'}>
          <Button variant="outline">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
        </Link>
      </div>
    );
  }

  const completedMilestones = task.milestones.filter((m) => m.status === 'passed').length;
  const progress = task.progress || (task.milestones.length > 0 ? completedMilestones / task.milestones.length : 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href={sessionId ? `/sessions/${sessionId}` : '/sessions'}>
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div>
            <h1 className="text-2xl font-bold truncate max-w-[600px]">
              {task.original_request}
            </h1>
            <p className="text-sm text-muted-foreground">
              Created {formatRelativeTime(task.created_at)}
            </p>
          </div>
          <Badge
            variant={
              task.status === 'completed'
                ? 'success'
                : task.status === 'failed'
                ? 'destructive'
                : task.status === 'in_progress'
                ? 'info'
                : 'secondary'
            }
          >
            {task.status.replace('_', ' ')}
          </Badge>
          {isConnected && task.status === 'in_progress' && (
            <Badge variant="outline" className="bg-green-50">
              Live
            </Badge>
          )}
        </div>

        {task.status === 'in_progress' && (
          <Button variant="destructive" onClick={handleCancel}>
            <XCircle className="mr-2 h-4 w-4" />
            Cancel
          </Button>
        )}
      </div>

      {/* Progress */}
      {task.status === 'in_progress' && (
        <Card>
          <CardContent className="pt-6">
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Progress</span>
                <span>
                  {completedMilestones} / {task.milestones.length} milestones
                </span>
              </div>
              <Progress value={progress * 100} />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Streaming Output */}
      {streamingContent && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Live Output
              <Badge variant="info">{currentAgent}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="p-4 bg-muted rounded-lg overflow-auto max-h-[300px] text-sm whitespace-pre-wrap">
              {streamingContent}
              <span className="animate-pulse">|</span>
            </pre>
          </CardContent>
        </Card>
      )}

      {/* Final Result */}
      {task.final_result && (
        <Card>
          <CardHeader>
            <CardTitle>Result</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="p-4 bg-muted rounded-lg overflow-auto max-h-[400px] text-sm whitespace-pre-wrap">
              {task.final_result}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* Task Detail Monitor - shows agent steps, milestones, cost breakdown */}
      <TaskDetailMonitor task={task} />
    </div>
  );
}
