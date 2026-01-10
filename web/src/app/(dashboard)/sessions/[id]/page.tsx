'use client';

import { TaskProgress } from '@/components/tasks/TaskProgress';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuth } from '@/hooks/useAuth';
import { useWebSocket } from '@/hooks/useWebSocket';
import { api, SessionDetailResponse } from '@/lib/api';
import { formatCurrency, formatNumber, formatRelativeTime } from '@/lib/utils';
import { TaskCompletedPayload, TaskProgressPayload, WSMessageType } from '@/types/websocket';
import { ArrowLeft, CheckCircle, Pause, Play, Plus, Trash2 } from 'lucide-react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

export default function SessionDetailPage() {
  const params = useParams();
  const sessionId = params.id as string;
  const { accessToken } = useAuth();

  const [session, setSession] = useState<SessionDetailResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [taskProgress, setTaskProgress] = useState<Record<string, TaskProgressPayload>>({});
  const [newTaskRequest, setNewTaskRequest] = useState('');
  const [isCreatingTask, setIsCreatingTask] = useState(false);

  const handleWebSocketMessage = useCallback((message: any) => {
    switch (message.type) {
      case WSMessageType.TASK_PROGRESS:
        const progress = message.payload as TaskProgressPayload;
        setTaskProgress((prev) => ({
          ...prev,
          [progress.task_id]: progress,
        }));
        break;

      case WSMessageType.TASK_COMPLETED:
        const completed = message.payload as TaskCompletedPayload;
        setSession((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            tasks: prev.tasks.map((t) =>
              t.id === completed.task_id
                ? { ...t, status: 'completed', final_result: completed.final_result }
                : t
            ),
          };
        });
        break;

      case WSMessageType.TASK_FAILED:
        const failed = message.payload as any;
        setSession((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            tasks: prev.tasks.map((t) =>
              t.id === failed.task_id ? { ...t, status: 'failed' } : t
            ),
          };
        });
        break;
    }
  }, []);

  const { isConnected } = useWebSocket({
    sessionId,
    token: accessToken,
    onMessage: handleWebSocketMessage,
  });

  const fetchSession = async () => {
    setIsLoading(true);
    try {
      const data = await api.getSession(sessionId);
      setSession(data);
      setError(null);
    } catch (err) {
      setError('Failed to fetch session');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const handlePause = async () => {
    try {
      await api.pauseSession(sessionId);
      setSession((prev) => (prev ? { ...prev, status: 'paused' } : prev));
    } catch (err) {
      console.error('Failed to pause session:', err);
    }
  };

  const handleResume = async () => {
    try {
      await api.resumeSession(sessionId);
      setSession((prev) => (prev ? { ...prev, status: 'active' } : prev));
    } catch (err) {
      console.error('Failed to resume session:', err);
    }
  };

  const handleComplete = async () => {
    try {
      await api.completeSession(sessionId);
      setSession((prev) => (prev ? { ...prev, status: 'completed' } : prev));
    } catch (err) {
      console.error('Failed to complete session:', err);
    }
  };

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete this session?')) return;
    try {
      await api.deleteSession(sessionId);
      window.location.href = '/sessions';
    } catch (err) {
      console.error('Failed to delete session:', err);
    }
  };

  const handleCreateTask = async () => {
    if (!newTaskRequest.trim()) return;
    setIsCreatingTask(true);
    try {
      const task = await api.createTask(sessionId, newTaskRequest);
      setSession((prev) => {
        if (!prev) return prev;
        return { ...prev, tasks: [...prev.tasks, task] };
      });
      setNewTaskRequest('');
    } catch (err) {
      console.error('Failed to create task:', err);
    } finally {
      setIsCreatingTask(false);
    }
  };

  useEffect(() => {
    fetchSession();
  }, [sessionId]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-pulse text-muted-foreground">Loading session...</div>
      </div>
    );
  }

  if (error || !session) {
    return (
      <div className="text-center py-12">
        <p className="text-destructive mb-4">{error || 'Session not found'}</p>
        <Link href="/sessions">
          <Button variant="outline">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Sessions
          </Button>
        </Link>
      </div>
    );
  }

  const totalTokens = session.total_input_tokens + session.total_output_tokens;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/sessions">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div>
            <h1 className="text-2xl font-bold">Session {session.id.slice(0, 8)}...</h1>
            <p className="text-sm text-muted-foreground">
              Created {formatRelativeTime(session.created_at)}
            </p>
          </div>
          <Badge
            variant={
              session.status === 'active'
                ? 'success'
                : session.status === 'paused'
                  ? 'warning'
                  : session.status === 'completed'
                    ? 'info'
                    : 'destructive'
            }
          >
            {session.status}
          </Badge>
          {isConnected && (
            <Badge variant="outline" className="bg-green-50">
              Live
            </Badge>
          )}
        </div>

        <div className="flex items-center gap-2">
          {session.status === 'active' && (
            <Button variant="outline" onClick={handlePause}>
              <Pause className="mr-2 h-4 w-4" />
              Pause
            </Button>
          )}
          {session.status === 'paused' && (
            <Button variant="outline" onClick={handleResume}>
              <Play className="mr-2 h-4 w-4" />
              Resume
            </Button>
          )}
          {(session.status === 'active' || session.status === 'paused') && (
            <Button variant="outline" onClick={handleComplete}>
              <CheckCircle className="mr-2 h-4 w-4" />
              Complete
            </Button>
          )}
          <Button variant="destructive" onClick={handleDelete}>
            <Trash2 className="mr-2 h-4 w-4" />
            Delete
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Tokens
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{formatNumber(totalTokens)}</p>
            <p className="text-xs text-muted-foreground">
              {formatNumber(session.total_input_tokens)} in / {formatNumber(session.total_output_tokens)} out
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Cost
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{formatCurrency(session.total_cost_usd)}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Tasks
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{session.tasks.length}</p>
          </CardContent>
        </Card>
      </div>

      {/* New Task Input */}
      {session.status === 'active' && (
        <Card>
          <CardHeader>
            <CardTitle>Create New Task</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              <input
                type="text"
                value={newTaskRequest}
                onChange={(e) => setNewTaskRequest(e.target.value)}
                placeholder="Enter your task request..."
                className="flex-1 px-3 py-2 border rounded-md bg-background"
                onKeyPress={(e) => e.key === 'Enter' && handleCreateTask()}
              />
              <Button onClick={handleCreateTask} disabled={isCreatingTask || !newTaskRequest.trim()}>
                <Plus className="mr-2 h-4 w-4" />
                Create Task
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tasks */}
      <Card>
        <CardHeader>
          <CardTitle>Tasks</CardTitle>
        </CardHeader>
        <CardContent>
          {session.tasks.length === 0 ? (
            <p className="text-center py-8 text-muted-foreground">No tasks yet</p>
          ) : (
            <div className="space-y-6">
              {session.tasks.map((task) => (
                <Link key={task.id} href={`/tasks/${task.id}?session=${sessionId}`}>
                  <div className="p-4 border rounded-lg hover:bg-accent/50 transition-colors cursor-pointer">
                    <TaskProgress
                      task={task}
                      progress={taskProgress[task.id]?.progress}
                      currentMilestone={taskProgress[task.id]?.current_milestone_title}
                    />
                  </div>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
