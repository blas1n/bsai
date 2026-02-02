'use client';

import { api } from '@/lib/api';
import {
  AgentActivity,
  AgentType,
  ChatMessage,
  MilestoneInfo,
  SessionStats,
  StreamingState,
} from '@/types/chat';
import { MilestoneStatus, TaskComplexity } from '@/types/session';
import {
  ArtifactData,
  BreakpointHitPayload,
  LLMChunkPayload,
  LLMCompletePayload,
  McpApprovalRequestPayload,
  McpToolCallRequestPayload,
  MilestoneProgressPayload,
  TaskCompletedPayload,
  TaskFailedPayload,
  TaskProgressPayload,
  TaskStartedPayload,
  WSMessage,
  WSMessageType,
} from '@/types/websocket';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from './useAuth';
import { useWebSocket } from './useWebSocket';
import { useSessionStore } from '@/stores/sessionStore';
import {
  ChatEventContext,
  handleTaskStarted,
  handleTaskProgress,
  handleMilestoneProgress,
  handleMilestoneCompleted,
  handleMilestoneRetry,
  handleLLMChunk,
  handleLLMComplete,
  handleTaskCompleted,
  handleTaskFailed,
  handleContextCompressed,
  handleBreakpointHit,
  handleMcpToolCallRequest,
  handleMcpApprovalRequest,
} from './chatEventHandlers';

interface UseChatOptions {
  sessionId?: string;
  onError?: (error: string) => void;
  breakpointEnabled?: boolean;
  breakpointNodes?: string[];
}

interface UseChatReturn {
  sessionId: string | null;
  messages: ChatMessage[];
  isLoading: boolean;
  isStreaming: boolean;
  error: string | null;
  stats: SessionStats;
  currentActivity: AgentActivity | null;
  completedAgents: AgentType[];
  agentHistory: AgentActivity[];
  /** Current task's Langfuse trace URL for debugging */
  currentTraceUrl: string | null;
  /** Current breakpoint state if workflow is paused */
  breakpoint: BreakpointHitPayload | null;
  /** Whether a breakpoint resume/reject is in progress */
  isBreakpointLoading: boolean;
  /** Current streaming text chunks from LLM */
  streamingChunks: string[];
  /** Current agent doing the streaming */
  streamingAgent: AgentType | undefined;
  sendMessage: (content: string) => Promise<void>;
  cancelTask: () => void;
  createNewChat: () => Promise<string>;
  loadSession: (sessionId: string) => Promise<void>;
  clearError: () => void;
  /** Resume workflow from breakpoint with optional user input */
  resumeFromBreakpoint: (userInput?: string) => Promise<void>;
  /** Reject and cancel task at breakpoint */
  rejectAtBreakpoint: (reason?: string) => Promise<void>;
}

export function useChat(options: UseChatOptions = {}): UseChatReturn {
  const {
    sessionId: initialSessionId,
    onError,
    breakpointEnabled = false,
    breakpointNodes = ['qa_breakpoint'],
  } = options;
  const { accessToken } = useAuth();
  const updateSessionTitle = useSessionStore((state) => state.updateSessionTitle);

  // Use refs to always have the latest values in callbacks
  const breakpointEnabledRef = useRef(breakpointEnabled);
  const breakpointNodesRef = useRef(breakpointNodes);
  useEffect(() => {
    console.log('[useChat] Breakpoint settings changed:', {
      breakpointEnabled,
      breakpointNodes,
    });
    breakpointEnabledRef.current = breakpointEnabled;
    breakpointNodesRef.current = breakpointNodes;
  }, [breakpointEnabled, breakpointNodes]);

  const [sessionId, setSessionId] = useState<string | null>(initialSessionId || null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<SessionStats>({
    totalTokens: 0,
    totalCostUsd: 0,
    inputTokens: 0,
    outputTokens: 0,
  });
  const [streaming, setStreaming] = useState<StreamingState>({
    isStreaming: false,
    chunks: [],
  });
  const [currentActivity, setCurrentActivity] = useState<AgentActivity | null>(null);
  const [completedAgents, setCompletedAgents] = useState<AgentType[]>([]);
  const [agentHistory, setAgentHistory] = useState<AgentActivity[]>([]);
  const [breakpoint, setBreakpoint] = useState<BreakpointHitPayload | null>(null);
  const [isBreakpointLoading, setIsBreakpointLoading] = useState(false);

  const currentTaskIdRef = useRef<string | null>(null);
  const streamingMessageIdRef = useRef<string | null>(null);

  // Event context for handlers - memoized to avoid recreation
  const eventContext = useMemo<ChatEventContext>(
    () => ({
      setMessages,
      setStreaming,
      setCurrentActivity,
      setCompletedAgents,
      setAgentHistory,
      setStats,
      setIsLoading,
      setError,
      setBreakpoint,
      currentTaskIdRef,
      streamingMessageIdRef,
      updateSessionTitle,
      onError,
    }),
    [updateSessionTitle, onError]
  );

  // WebSocket message handler - uses separated event handlers
  const handleWebSocketMessage = useCallback(
    (message: WSMessage) => {
      const handlers: Record<string, (payload: unknown, ctx: ChatEventContext) => void> = {
        [WSMessageType.TASK_STARTED]: (p, c) =>
          handleTaskStarted(p as TaskStartedPayload, c),
        [WSMessageType.TASK_PROGRESS]: (p, c) =>
          handleTaskProgress(p as TaskProgressPayload, c),
        [WSMessageType.MILESTONE_STARTED]: (p, c) =>
          handleMilestoneProgress(p as MilestoneProgressPayload, c),
        [WSMessageType.MILESTONE_PROGRESS]: (p, c) =>
          handleMilestoneProgress(p as MilestoneProgressPayload, c),
        [WSMessageType.MILESTONE_COMPLETED]: (p, c) =>
          handleMilestoneCompleted(p as MilestoneProgressPayload, c),
        [WSMessageType.MILESTONE_RETRY]: (p, c) =>
          handleMilestoneRetry(p as MilestoneProgressPayload, c),
        [WSMessageType.LLM_CHUNK]: (p, c) => handleLLMChunk(p as LLMChunkPayload, c),
        [WSMessageType.LLM_COMPLETE]: (p, c) =>
          handleLLMComplete(p as LLMCompletePayload, c),
        [WSMessageType.TASK_COMPLETED]: (p, c) =>
          handleTaskCompleted(p as TaskCompletedPayload, c),
        [WSMessageType.TASK_FAILED]: (p, c) =>
          handleTaskFailed(p as TaskFailedPayload, c),
        [WSMessageType.CONTEXT_COMPRESSED]: (_p, c) => handleContextCompressed(c),
        [WSMessageType.BREAKPOINT_HIT]: (p, c) =>
          handleBreakpointHit(p as BreakpointHitPayload, c),
        [WSMessageType.MCP_TOOL_CALL_REQUEST]: (p, c) =>
          handleMcpToolCallRequest(p as McpToolCallRequestPayload, c),
        [WSMessageType.MCP_APPROVAL_REQUEST]: (p, c) =>
          handleMcpApprovalRequest(p as McpApprovalRequestPayload, c),
      };

      const handler = handlers[message.type];
      if (handler) {
        handler(message.payload, eventContext);
      }
    },
    [eventContext]
  );

  // WebSocket connection with auth token
  const { isConnected, reconnect: wsReconnect, send: wsSend } = useWebSocket({
    sessionId: sessionId || undefined,
    token: accessToken || undefined,
    onMessage: handleWebSocketMessage,
  });

  // Store wsSend in ref to avoid unnecessary effect triggers
  const wsSendRef = useRef(wsSend);
  useEffect(() => {
    wsSendRef.current = wsSend;
  }, [wsSend]);

  // Track previous breakpoint values to only send when actually changed
  const prevBreakpointRef = useRef({ enabled: breakpointEnabled, nodes: breakpointNodes });

  // Send breakpoint config update via WebSocket when settings change during active task
  useEffect(() => {
    const taskId = currentTaskIdRef.current;
    const prev = prevBreakpointRef.current;

    // Only send if there's an active task and the values actually changed
    if (
      taskId &&
      isConnected &&
      (prev.enabled !== breakpointEnabled ||
        JSON.stringify(prev.nodes) !== JSON.stringify(breakpointNodes))
    ) {
      console.log('[useChat] Sending breakpoint config update via WebSocket:', {
        taskId,
        breakpointEnabled,
        breakpointNodes,
      });
      wsSendRef.current({
        type: WSMessageType.BREAKPOINT_CONFIG,
        payload: {
          task_id: taskId,
          breakpoint_enabled: breakpointEnabled,
          breakpoint_nodes: breakpointNodes,
        },
        timestamp: new Date().toISOString(),
      });

      // Update previous values
      prevBreakpointRef.current = { enabled: breakpointEnabled, nodes: breakpointNodes };
    }
  }, [breakpointEnabled, breakpointNodes, isConnected]);

  // Create new chat session
  const createNewChat = useCallback(async (): Promise<string> => {
    setIsLoading(true);
    setError(null);

    try {
      const session = await api.createSession();
      setSessionId(session.id);
      // Reset all state for new session
      setMessages([]);
      setStats({
        totalTokens: 0,
        totalCostUsd: 0,
        inputTokens: 0,
        outputTokens: 0,
      });
      setStreaming({ isStreaming: false, chunks: [] });
      setCurrentActivity(null);
      setCompletedAgents([]);
      setAgentHistory([]);
      setBreakpoint(null);
      setIsBreakpointLoading(false);
      currentTaskIdRef.current = null;
      streamingMessageIdRef.current = null;
      return session.id;
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to create session';
      setError(errorMsg);
      onError?.(errorMsg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [onError]);

  // Load existing session
  const loadSession = useCallback(async (targetSessionId: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const session = await api.getSession(targetSessionId);
      setSessionId(targetSessionId);

      // Fetch all session artifacts once (session-level management)
      let sessionArtifacts: ArtifactData[] = [];
      try {
        const artifactResult = await api.getArtifacts(targetSessionId);
        if (artifactResult.items) {
          sessionArtifacts = artifactResult.items.map((a) => ({
            id: a.id,
            type: a.artifact_type,
            filename: a.filename,
            language: a.language,
            content: a.content,
            path: a.path,
          }));
        }
      } catch {
        // Ignore error fetching artifacts
      }

      // Convert tasks to messages
      const loadedMessages: ChatMessage[] = [];
      const completedTasks = session.tasks.filter((t) => t.final_result);
      const lastCompletedTaskId = completedTasks.length > 0 ? completedTasks[completedTasks.length - 1].id : null;

      for (const task of session.tasks) {
        // User message
        loadedMessages.push({
          id: `user-${task.id}`,
          role: 'user',
          content: task.original_request,
          timestamp: task.created_at,
        });

        // Assistant message (if completed)
        if (task.final_result) {
          // Get task details to include milestones
          let milestones: MilestoneInfo[] = [];
          let agentActivity: AgentActivity[] = [];

          try {
            const taskDetail = await api.getTask(targetSessionId, task.id);
            if (taskDetail.milestones) {
              milestones = taskDetail.milestones.map((m) => ({
                id: m.id,
                sequenceNumber: m.sequence_number,
                title: m.title || m.description.slice(0, 50),
                description: m.description,
                complexity: m.complexity.toLowerCase() as TaskComplexity,
                status: m.status.toLowerCase() as MilestoneStatus,
                selectedModel: m.selected_llm || undefined,
                usage: {
                  inputTokens: m.input_tokens,
                  outputTokens: m.output_tokens,
                  costUsd: parseFloat(m.cost_usd),
                  model: m.selected_llm || 'unknown',
                },
              }));

              // Reconstruct agent activity from milestones
              // For completed tasks, we show what agents completed each milestone
              agentActivity = [
                // Conductor completed (always first)
                {
                  agent: 'conductor' as AgentType,
                  status: 'completed' as const,
                  message: `Created ${milestones.length} milestones`,
                  completedAt: task.created_at,
                },
              ];

              // Add activities for each milestone
              for (const m of taskDetail.milestones) {
                // Worker activity
                agentActivity.push({
                  agent: 'worker' as AgentType,
                  status: 'completed' as const,
                  message: `Executed milestone ${m.sequence_number}`,
                  model: m.selected_llm || undefined,
                  completedAt: m.created_at,
                });
                // QA activity
                agentActivity.push({
                  agent: 'qa' as AgentType,
                  status: 'completed' as const,
                  message: m.status === 'passed' ? 'Quality check passed' : 'Check completed',
                  completedAt: m.created_at,
                });
              }

              // Responder activity (for completed tasks)
              agentActivity.push({
                agent: 'responder' as AgentType,
                status: 'completed' as const,
                message: 'Response ready',
                completedAt: task.updated_at,
              });
            }
          } catch {
            // Ignore error fetching task details, milestones will be empty
          }

          // Attach all session artifacts to the last completed task's message
          // (artifacts are managed at session level, not task level)
          const isLastTask = task.id === lastCompletedTaskId;

          loadedMessages.push({
            id: `assistant-${task.id}`,
            role: 'assistant',
            content: task.final_result,
            timestamp: task.updated_at,
            taskId: task.id,
            milestones,
            agentActivity,
            artifacts: isLastTask && sessionArtifacts.length > 0 ? sessionArtifacts : undefined,
            rawContent: task.final_result, // For artifact extraction
          });
        }
      }

      setMessages(loadedMessages);
      setStats({
        totalTokens: session.total_input_tokens + session.total_output_tokens,
        totalCostUsd: parseFloat(session.total_cost_usd),
        inputTokens: session.total_input_tokens,
        outputTokens: session.total_output_tokens,
      });
      // Reset live monitoring state when loading a different session
      setStreaming({ isStreaming: false, chunks: [] });
      setCurrentActivity(null);
      setCompletedAgents([]);
      setAgentHistory([]);
      setBreakpoint(null);
      setIsBreakpointLoading(false);
      currentTaskIdRef.current = null;
      streamingMessageIdRef.current = null;
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to load session';
      setError(errorMsg);
      onError?.(errorMsg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [onError]);

  // Send message
  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim()) return;

    // Create session if needed
    let currentSessionId = sessionId;
    if (!currentSessionId) {
      currentSessionId = await createNewChat();
    }

    // Add user message
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);
    setError(null);

    try {
      // Create task - assistant message will be created when TASK_STARTED arrives
      // Use refs to get the latest values at call time
      console.log('[useChat] Creating task with breakpoint settings:', {
        breakpointEnabled: breakpointEnabledRef.current,
        breakpointNodes: breakpointNodesRef.current,
      });
      await api.createTask(currentSessionId, content, {
        stream: true,
        breakpointEnabled: breakpointEnabledRef.current,
        breakpointNodes: breakpointNodesRef.current,
      });
      // Note: streamingMessageIdRef and currentTaskIdRef will be set by TASK_STARTED handler
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to send message';
      setError(errorMsg);
      onError?.(errorMsg);
      setIsLoading(false);
    }
  }, [sessionId, createNewChat, onError]);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Cancel current task
  const cancelTask = useCallback(() => {
    const taskId = currentTaskIdRef.current;
    if (!taskId || !sessionId) return;

    // Call cancel API
    api.cancelTask(sessionId, taskId).catch((err) => {
      console.error('Failed to cancel task:', err);
    });

    // Update UI immediately
    if (streamingMessageIdRef.current) {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === streamingMessageIdRef.current
            ? {
              ...msg,
              content: msg.content || 'Task cancelled by user.',
              isStreaming: false,
            }
            : msg
        )
      );
    }

    setStreaming({ isStreaming: false, chunks: [] });
    setIsLoading(false);
    setCurrentActivity(null);
    currentTaskIdRef.current = null;
    streamingMessageIdRef.current = null;
  }, [sessionId]);

  // Resume workflow from breakpoint
  const resumeFromBreakpoint = useCallback(async (userInput?: string) => {
    if (!breakpoint || !sessionId) return;

    setIsBreakpointLoading(true);
    try {
      await api.resumeTask(sessionId, breakpoint.task_id, userInput);
      setBreakpoint(null);
      // Update activity to show resuming
      setCurrentActivity({
        agent: breakpoint.agent_type as AgentType,
        status: 'running',
        message: 'Resuming workflow...',
        startedAt: new Date().toISOString(),
      });
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to resume task';
      setError(errorMsg);
      onError?.(errorMsg);
    } finally {
      setIsBreakpointLoading(false);
    }
  }, [breakpoint, sessionId, onError]);

  // Reject at breakpoint - with reason: re-run worker, without reason: cancel task
  const rejectAtBreakpoint = useCallback(async (reason?: string) => {
    if (!breakpoint || !sessionId) return;

    setIsBreakpointLoading(true);
    try {
      await api.rejectBreakpoint(sessionId, breakpoint.task_id, reason);
      setBreakpoint(null);

      if (reason) {
        // With feedback: worker will re-run, keep streaming state
        // Update activity to show re-running
        setCurrentActivity({
          agent: 'worker' as AgentType,
          status: 'running',
          message: 'Re-running with user feedback...',
          startedAt: new Date().toISOString(),
        });
      } else {
        // Without feedback: task cancelled
        if (streamingMessageIdRef.current) {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === streamingMessageIdRef.current
                ? {
                  ...msg,
                  content: 'Task cancelled by user.',
                  isStreaming: false,
                }
                : msg
            )
          );
        }

        setStreaming({ isStreaming: false, chunks: [] });
        setIsLoading(false);
        setCurrentActivity(null);
        currentTaskIdRef.current = null;
        streamingMessageIdRef.current = null;
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to reject task';
      setError(errorMsg);
      onError?.(errorMsg);
    } finally {
      setIsBreakpointLoading(false);
    }
  }, [breakpoint, sessionId, onError]);

  // Set API token and load initial session when auth changes
  const hasLoadedRef = useRef<string | null>(null);
  useEffect(() => {
    if (accessToken) {
      api.setToken(accessToken);
      // Load initial session if provided (after token is set)
      if (initialSessionId && hasLoadedRef.current !== initialSessionId) {
        hasLoadedRef.current = initialSessionId;
        loadSession(initialSessionId);
      }
    }
  }, [accessToken, initialSessionId, loadSession]);

  // Get the current trace URL from the streaming message (empty string means no trace)
  const traceUrl = messages.find(
    (msg) => msg.isStreaming || msg.taskId === currentTaskIdRef.current
  )?.traceUrl;
  const currentTraceUrl = traceUrl && traceUrl.length > 0 ? traceUrl : null;

  return {
    sessionId,
    messages,
    isLoading,
    isStreaming: streaming.isStreaming,
    error,
    stats,
    currentActivity,
    completedAgents,
    agentHistory,
    currentTraceUrl,
    breakpoint,
    isBreakpointLoading,
    streamingChunks: streaming.chunks,
    streamingAgent: streaming.currentAgent,
    sendMessage,
    cancelTask,
    createNewChat,
    loadSession,
    clearError,
    resumeFromBreakpoint,
    rejectAtBreakpoint,
  };
}
