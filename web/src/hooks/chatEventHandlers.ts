/**
 * Chat event handlers - Separated from useChat for maintainability
 *
 * These handlers process WebSocket events with explicit status from the backend,
 * eliminating the need for heuristic-based status detection.
 */

import {
  AgentActivity,
  AgentType,
  ChatMessage,
  MilestoneInfo,
  QADecision,
  SessionStats,
  StreamingState,
} from '@/types/chat';
import { MilestoneStatus, TaskComplexity } from '@/types/session';
import {
  AgentDetails,
  BreakpointHitPayload,
  ConductorDetails,
  LLMChunkPayload,
  LLMCompletePayload,
  MilestoneProgressPayload,
  TaskCompletedPayload,
  TaskFailedPayload,
  TaskProgressPayload,
  TaskStartedPayload,
  WorkerDetails,
} from '@/types/websocket';

/**
 * Context passed to event handlers - allows them to update state
 */
export interface ChatEventContext {
  // State setters
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  setStreaming: React.Dispatch<React.SetStateAction<StreamingState>>;
  setCurrentActivity: React.Dispatch<React.SetStateAction<AgentActivity | null>>;
  setCompletedAgents: React.Dispatch<React.SetStateAction<AgentType[]>>;
  setAgentHistory: React.Dispatch<React.SetStateAction<AgentActivity[]>>;
  setStats: React.Dispatch<React.SetStateAction<SessionStats>>;
  setIsLoading: React.Dispatch<React.SetStateAction<boolean>>;
  setError: React.Dispatch<React.SetStateAction<string | null>>;
  setBreakpoint: React.Dispatch<React.SetStateAction<BreakpointHitPayload | null>>;

  // Refs
  currentTaskIdRef: React.MutableRefObject<string | null>;
  streamingMessageIdRef: React.MutableRefObject<string | null>;

  // Callbacks
  updateSessionTitle: (sessionId: string, title: string) => void;
  onError?: (error: string) => void;
}

/**
 * Extract user-facing message from final result, removing code blocks and artifacts.
 * Keeps only the conversational text that should be displayed in chat.
 */
export function extractUserMessage(content: string): string {
  if (!content) return '';

  // Remove code blocks (```...```)
  let result = content.replace(/```[\s\S]*?```/g, '');

  // Remove inline code that looks like file paths or technical artifacts
  result = result.replace(/`[^`]+`/g, (match) => {
    // Keep short inline code that looks like emphasis, remove file paths
    if (match.includes('/') || match.includes('\\') || match.length > 50) {
      return '';
    }
    return match;
  });

  // Remove multiple consecutive newlines (cleanup after removing blocks)
  result = result.replace(/\n{3,}/g, '\n\n');

  // Trim whitespace
  result = result.trim();

  // If nothing left, provide a default message
  if (!result) {
    return 'Task completed. Check the Artifacts panel for generated code and files.';
  }

  return result;
}

/**
 * Handle TASK_STARTED event
 */
export function handleTaskStarted(
  payload: TaskStartedPayload,
  ctx: ChatEventContext
): void {
  const {
    setMessages,
    setStreaming,
    currentTaskIdRef,
    streamingMessageIdRef,
    updateSessionTitle,
  } = ctx;

  const taskIdStr = String(payload.task_id);

  // If we already created the message (e.g., from MILESTONE event), just update milestone count
  if (streamingMessageIdRef.current && currentTaskIdRef.current === taskIdStr) {
    setStreaming((prev) => ({
      ...prev,
      totalMilestones: payload.milestone_count,
    }));
    return;
  }

  // Convert previous milestones from backend to MilestoneInfo format
  const previousMilestones: MilestoneInfo[] = (payload.previous_milestones || []).map((m) => ({
    id: m.id,
    sequenceNumber: m.sequence_number,
    title: m.description,
    description: m.description,
    complexity: m.complexity as TaskComplexity,
    status: (m.status === 'pass' ? 'passed' : m.status) as MilestoneStatus,
  }));

  // Create assistant message for this task, preserving previous milestones
  currentTaskIdRef.current = taskIdStr;
  const newMessageId = `msg-${Date.now()}`;
  streamingMessageIdRef.current = newMessageId;

  const assistantMessage: ChatMessage = {
    id: newMessageId,
    role: 'assistant',
    content: '',
    timestamp: new Date().toISOString(),
    taskId: taskIdStr,
    milestones: previousMilestones,
    agentActivity: [],
    isStreaming: true,
    traceUrl: payload.trace_url,
  };

  setMessages((prev) => [...prev, assistantMessage]);
  setStreaming({
    isStreaming: true,
    totalMilestones: payload.milestone_count + previousMilestones.length,
    currentMilestone: previousMilestones.length,
    chunks: [],
  });

  // Update session title with first task's request
  if (payload.session_id && payload.original_request) {
    const title =
      payload.original_request.length > 50
        ? payload.original_request.slice(0, 50) + '...'
        : payload.original_request;
    updateSessionTitle(String(payload.session_id), title);
  }
}

/**
 * Handle TASK_PROGRESS event
 */
export function handleTaskProgress(
  payload: TaskProgressPayload,
  ctx: ChatEventContext
): void {
  const { setStreaming, setMessages, streamingMessageIdRef } = ctx;

  setStreaming((prev) => ({
    ...prev,
    currentMilestone: payload.current_milestone,
    totalMilestones: payload.total_milestones,
  }));

  // Update current milestone status to in_progress
  if (streamingMessageIdRef.current) {
    setMessages((prev) =>
      prev.map((msg) => {
        if (msg.id !== streamingMessageIdRef.current) return msg;

        const milestones = msg.milestones || [];
        // Milestone index is 0-based, sequence_number is 1-based
        const currentIndex = payload.current_milestone;
        if (currentIndex < milestones.length) {
          const updatedMilestones = milestones.map((m, idx) => {
            if (idx === currentIndex && m.status === 'pending') {
              return { ...m, status: 'in_progress' as MilestoneStatus };
            }
            return m;
          });
          return { ...msg, milestones: updatedMilestones };
        }
        return msg;
      })
    );
  }
}

/**
 * Handle MILESTONE_PROGRESS event
 *
 * Uses EXPLICIT status from payload instead of heuristics.
 * The backend now sends AgentStatus (started/completed/failed) explicitly.
 */
export function handleMilestoneProgress(
  payload: MilestoneProgressPayload,
  ctx: ChatEventContext
): void {
  const {
    setMessages,
    setStreaming,
    setCurrentActivity,
    setCompletedAgents,
    setAgentHistory,
    currentTaskIdRef,
    streamingMessageIdRef,
  } = ctx;

  const agentType = payload.agent as AgentType;
  const taskIdStr = String(payload.task_id);

  // Ensure we have a streaming message for this task
  if (!streamingMessageIdRef.current || currentTaskIdRef.current !== taskIdStr) {
    const newMessageId = `msg-${Date.now()}`;
    currentTaskIdRef.current = taskIdStr;
    streamingMessageIdRef.current = newMessageId;

    const assistantMessage: ChatMessage = {
      id: newMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      taskId: taskIdStr,
      milestones: [],
      agentActivity: [],
      isStreaming: true,
    };

    setMessages((prev) => {
      const existing = prev.find((m) => m.isStreaming || m.taskId === taskIdStr);
      if (existing) {
        streamingMessageIdRef.current = existing.id;
        return prev;
      }
      return [...prev, assistantMessage];
    });
    setStreaming({
      isStreaming: true,
      totalMilestones: 0,
      currentMilestone: 0,
      chunks: [],
    });
  }

  // Use EXPLICIT status from payload
  // Backend sends: 'started', 'completed', 'failed' via AgentStatus enum
  // Also check payload.status for milestone status ('in_progress', 'passed', 'failed')
  const isCompletion =
    payload.status === 'completed' ||
    payload.status === 'passed' ||
    payload.status === 'failed';

  // Also check if details are present (completed events typically have details)
  const hasDetails = !!payload.details && Object.keys(payload.details).length > 0;

  if (isCompletion || hasDetails) {
    // Add agent to completed list
    setCompletedAgents((prev) => (prev.includes(agentType) ? prev : [...prev, agentType]));
  }

  const activity: AgentActivity = {
    agent: agentType,
    status: isCompletion || hasDetails ? 'completed' : 'running',
    message: payload.message,
    startedAt: new Date().toISOString(),
    completedAt: isCompletion || hasDetails ? new Date().toISOString() : undefined,
    details: payload.details as AgentDetails | undefined,
  };
  setCurrentActivity(activity);

  // Add to activity history
  setAgentHistory((prev) => {
    if (isCompletion || hasDetails) {
      const lastRunningIndex = [...prev]
        .reverse()
        .findIndex((a) => a.agent === agentType && a.status === 'running');
      if (lastRunningIndex !== -1) {
        const actualIndex = prev.length - 1 - lastRunningIndex;
        const updated = [...prev];
        updated[actualIndex] = activity;
        return updated;
      }
    }
    return [...prev, activity];
  });

  // Handle conductor completion with milestones
  if (agentType === 'conductor' && (isCompletion || hasDetails) && payload.details) {
    const conductorDetails = payload.details as ConductorDetails;
    if (conductorDetails.milestones && conductorDetails.milestones.length > 0) {
      const plannedMilestones: MilestoneInfo[] = conductorDetails.milestones.map((m) => ({
        id: `planned-${m.index}`,
        sequenceNumber: m.index,
        title: m.description,
        description: m.acceptance_criteria,
        complexity: m.complexity as TaskComplexity,
        status: 'pending' as MilestoneStatus,
      }));

      setMessages((prev) => {
        const targetId = streamingMessageIdRef.current;
        const streamingMsg = prev.find(
          (msg) => (targetId && msg.id === targetId) || msg.isStreaming
        );

        if (streamingMsg) {
          return prev.map((msg) => {
            if (msg.id === streamingMsg.id) {
              return {
                ...msg,
                milestones: plannedMilestones,
                agentActivity: [...(msg.agentActivity || []), activity],
              };
            }
            return msg;
          });
        } else {
          const newTaskIdStr = String(payload.task_id);
          const newMessageId = `msg-${Date.now()}`;
          currentTaskIdRef.current = newTaskIdStr;
          streamingMessageIdRef.current = newMessageId;

          const newMessage: ChatMessage = {
            id: newMessageId,
            role: 'assistant',
            content: '',
            timestamp: new Date().toISOString(),
            taskId: newTaskIdStr,
            milestones: plannedMilestones,
            agentActivity: [activity],
            isStreaming: true,
          };
          return [...prev, newMessage];
        }
      });

      setStreaming((prev) => ({
        ...prev,
        isStreaming: true,
        totalMilestones: conductorDetails.milestones.length,
      }));
      return; // Skip default message update
    }
  }

  // Handle worker completion with token/cost info and artifacts
  // Uses task-level snapshot: artifacts array = COMPLETE state (no merge/delete needed)
  if (agentType === 'worker' && (isCompletion || hasDetails) && payload.details) {
    const workerDetails = payload.details as WorkerDetails;

    setMessages((prev) =>
      prev.map((msg) => {
        if (msg.id !== streamingMessageIdRef.current) return msg;

        const milestones = msg.milestones || [];
        const milestoneIndex = payload.sequence_number - 1;

        const updatedMilestones = milestones.map((m, idx) => {
          if (idx === milestoneIndex) {
            return {
              ...m,
              status: 'in_progress' as MilestoneStatus,
              selectedModel: workerDetails.model,
              usage: {
                inputTokens: workerDetails.input_tokens || 0,
                outputTokens: workerDetails.output_tokens || 0,
                costUsd: workerDetails.cost_usd || 0,
                model: workerDetails.model || 'unknown',
              },
            };
          }
          return m;
        });

        // Task-level snapshot: Replace entire artifacts array (no merge logic needed)
        // Worker output represents COMPLETE artifact state
        const newArtifacts = workerDetails.artifacts || [];

        return {
          ...msg,
          milestones: updatedMilestones,
          artifacts: newArtifacts,
          rawContent: workerDetails.output || msg.rawContent,
          agentActivity: [...(msg.agentActivity || []), activity],
        };
      })
    );
    return; // Skip default activity update
  }

  // Default: Update message with activity
  if (streamingMessageIdRef.current) {
    setMessages((prev) =>
      prev.map((msg) =>
        msg.id === streamingMessageIdRef.current
          ? {
              ...msg,
              agentActivity: [...(msg.agentActivity || []), activity],
            }
          : msg
      )
    );
  }
}

/**
 * Handle MILESTONE_COMPLETED event
 */
export function handleMilestoneCompleted(
  payload: MilestoneProgressPayload,
  ctx: ChatEventContext
): void {
  const { setMessages, setCurrentActivity, setCompletedAgents, streamingMessageIdRef } = ctx;

  const agent = payload.agent as AgentType;

  // Add agent to completed list
  setCompletedAgents((prev) => (prev.includes(agent) ? prev : [...prev, agent]));

  setCurrentActivity((prev) =>
    prev
      ? {
          ...prev,
          status: 'completed',
          completedAt: new Date().toISOString(),
        }
      : null
  );

  // Update milestone status in message
  if (streamingMessageIdRef.current) {
    setMessages((prev) =>
      prev.map((msg) => {
        if (msg.id !== streamingMessageIdRef.current) return msg;

        const existingMilestones = msg.milestones || [];
        const milestoneIndex = existingMilestones.findIndex(
          (m) => m.sequenceNumber === payload.sequence_number
        );

        if (milestoneIndex >= 0) {
          const updatedMilestones = [...existingMilestones];
          updatedMilestones[milestoneIndex] = {
            ...updatedMilestones[milestoneIndex],
            id: payload.milestone_id,
            status: 'passed' as MilestoneStatus,
          };
          return { ...msg, milestones: updatedMilestones };
        } else {
          const milestoneInfo: MilestoneInfo = {
            id: payload.milestone_id,
            sequenceNumber: payload.sequence_number,
            title: payload.message,
            description: '',
            complexity: 'moderate' as TaskComplexity,
            status: 'passed' as MilestoneStatus,
          };
          return { ...msg, milestones: [...existingMilestones, milestoneInfo] };
        }
      })
    );
  }
}

/**
 * Handle MILESTONE_RETRY event
 */
export function handleMilestoneRetry(
  payload: MilestoneProgressPayload,
  ctx: ChatEventContext
): void {
  const { setMessages, streamingMessageIdRef } = ctx;

  if (streamingMessageIdRef.current) {
    setMessages((prev) =>
      prev.map((msg) => {
        if (msg.id !== streamingMessageIdRef.current) return msg;
        const milestones = msg.milestones || [];
        const lastMilestone = milestones[milestones.length - 1];
        if (lastMilestone) {
          lastMilestone.qaResult = {
            decision: 'retry' as QADecision,
            feedback: payload.message,
            retryCount: (lastMilestone.qaResult?.retryCount || 0) + 1,
            maxRetries: 3,
          };
        }
        return { ...msg, milestones: [...milestones] };
      })
    );
  }
}

/**
 * Handle LLM_CHUNK event
 */
export function handleLLMChunk(payload: LLMChunkPayload, ctx: ChatEventContext): void {
  const { setStreaming, setMessages, streamingMessageIdRef } = ctx;

  setStreaming((prev) => ({
    ...prev,
    currentAgent: payload.agent as AgentType,
    chunks: [...prev.chunks, payload.chunk],
  }));

  if (streamingMessageIdRef.current) {
    setMessages((prev) =>
      prev.map((msg) =>
        msg.id === streamingMessageIdRef.current
          ? { ...msg, content: msg.content + payload.chunk }
          : msg
      )
    );
  }
}

/**
 * Handle LLM_COMPLETE event
 */
export function handleLLMComplete(payload: LLMCompletePayload, ctx: ChatEventContext): void {
  const { setCurrentActivity, setMessages, streamingMessageIdRef } = ctx;

  setCurrentActivity(null);

  if (streamingMessageIdRef.current) {
    setMessages((prev) =>
      prev.map((msg) => {
        if (msg.id !== streamingMessageIdRef.current) return msg;
        const milestones = msg.milestones || [];
        const lastMilestone = milestones[milestones.length - 1];
        if (lastMilestone) {
          lastMilestone.usage = {
            inputTokens: 0,
            outputTokens: payload.tokens_used,
            costUsd: 0,
            model: payload.agent,
          };
        }
        return { ...msg, milestones: [...milestones] };
      })
    );
  }
}

/**
 * Handle TASK_COMPLETED event
 */
export function handleTaskCompleted(
  payload: TaskCompletedPayload,
  ctx: ChatEventContext
): void {
  const {
    setMessages,
    setStats,
    setStreaming,
    setIsLoading,
    setCurrentActivity,
    currentTaskIdRef,
    streamingMessageIdRef,
  } = ctx;

  const userMessage = extractUserMessage(payload.final_result);
  const targetId = streamingMessageIdRef.current;

  if (targetId) {
    setMessages((prev) =>
      prev.map((msg) =>
        msg.id === targetId
          ? {
              ...msg,
              content: userMessage,
              isStreaming: false,
              usage: {
                inputTokens: 0,
                outputTokens: payload.total_tokens,
                totalTokens: payload.total_tokens,
                costUsd: parseFloat(payload.total_cost_usd),
                model: 'multiple',
              },
              traceUrl: payload.trace_url || msg.traceUrl,
            }
          : msg
      )
    );
  }

  setStats((prev) => ({
    ...prev,
    totalTokens: prev.totalTokens + payload.total_tokens,
    totalCostUsd: prev.totalCostUsd + parseFloat(payload.total_cost_usd),
  }));

  setStreaming({ isStreaming: false, chunks: [] });
  setIsLoading(false);
  setCurrentActivity(null);
  currentTaskIdRef.current = null;
  streamingMessageIdRef.current = null;
}

/**
 * Handle TASK_FAILED event
 */
export function handleTaskFailed(
  payload: TaskFailedPayload,
  ctx: ChatEventContext
): void {
  const {
    setMessages,
    setError,
    setStreaming,
    setIsLoading,
    setCurrentActivity,
    currentTaskIdRef,
    streamingMessageIdRef,
    onError,
  } = ctx;

  if (streamingMessageIdRef.current) {
    setMessages((prev) =>
      prev.map((msg) =>
        msg.id === streamingMessageIdRef.current
          ? {
              ...msg,
              content: `Error: ${payload.error}`,
              isStreaming: false,
            }
          : msg
      )
    );
  }

  setError(payload.error);
  onError?.(payload.error);
  setStreaming({ isStreaming: false, chunks: [] });
  setIsLoading(false);
  setCurrentActivity(null);
  currentTaskIdRef.current = null;
  streamingMessageIdRef.current = null;
}

/**
 * Handle CONTEXT_COMPRESSED event
 */
export function handleContextCompressed(ctx: ChatEventContext): void {
  const { setMessages } = ctx;

  const systemMessage: ChatMessage = {
    id: `sys-${Date.now()}`,
    role: 'system',
    content: 'Context was compressed to free up memory.',
    timestamp: new Date().toISOString(),
  };
  setMessages((prev) => [...prev, systemMessage]);
}

/**
 * Handle BREAKPOINT_HIT event
 */
export function handleBreakpointHit(
  payload: BreakpointHitPayload,
  ctx: ChatEventContext
): void {
  const { setBreakpoint, setCurrentActivity } = ctx;

  setBreakpoint(payload);
  setCurrentActivity({
    agent: payload.agent_type as AgentType,
    status: 'running',
    message: `Paused at ${payload.node_name} - awaiting review`,
    startedAt: payload.timestamp,
  });
}
