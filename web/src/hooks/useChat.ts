'use client';

import { api } from '@/lib/api';
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
  ArtifactData,
  ConductorDetails,
  LLMChunkPayload,
  LLMCompletePayload,
  MilestoneProgressPayload,
  TaskCompletedPayload,
  TaskFailedPayload,
  TaskProgressPayload,
  TaskStartedPayload,
  WorkerDetails,
  WSMessage,
  WSMessageType,
} from '@/types/websocket';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from './useAuth';
import { useWebSocket } from './useWebSocket';
import { useSessionStore } from '@/stores/sessionStore';

interface UseChatOptions {
  sessionId?: string;
  onError?: (error: string) => void;
}

/**
 * Extract user-facing message from final result, removing code blocks and artifacts.
 * Keeps only the conversational text that should be displayed in chat.
 */
function extractUserMessage(content: string): string {
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
  sendMessage: (content: string) => Promise<void>;
  cancelTask: () => void;
  createNewChat: () => Promise<string>;
  loadSession: (sessionId: string) => Promise<void>;
  clearError: () => void;
}

export function useChat(options: UseChatOptions = {}): UseChatReturn {
  const { sessionId: initialSessionId, onError } = options;
  const { accessToken } = useAuth();
  const updateSessionTitle = useSessionStore((state) => state.updateSessionTitle);

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

  const currentTaskIdRef = useRef<string | null>(null);
  const streamingMessageIdRef = useRef<string | null>(null);

  // WebSocket message handler
  const handleWebSocketMessage = useCallback((message: WSMessage) => {
    switch (message.type) {
      case WSMessageType.TASK_STARTED: {
        const payload = message.payload as TaskStartedPayload;
        const taskIdStr = String(payload.task_id);

        // If we already created the message (e.g., from MILESTONE event), just update milestone count
        if (streamingMessageIdRef.current && currentTaskIdRef.current === taskIdStr) {
          setStreaming((prev) => ({
            ...prev,
            totalMilestones: payload.milestone_count,
          }));
          break;
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
          const title = payload.original_request.length > 50
            ? payload.original_request.slice(0, 50) + '...'
            : payload.original_request;
          updateSessionTitle(String(payload.session_id), title);
        }
        break;
      }

      case WSMessageType.TASK_PROGRESS: {
        const payload = message.payload as TaskProgressPayload;
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
        break;
      }

      case WSMessageType.MILESTONE_STARTED:
      case WSMessageType.MILESTONE_PROGRESS: {
        const payload = message.payload as MilestoneProgressPayload;
        const agentType = payload.agent as AgentType;
        const taskIdStr = String(payload.task_id);

        // Ensure we have a streaming message for this task
        // This handles cases where MILESTONE_STARTED arrives before TASK_STARTED
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
            // Check if we already have a streaming message
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

        // Check if this is a completion message
        // Completion events have details attached, started events don't
        const hasDetails = !!payload.details && Object.keys(payload.details).length > 0;
        const msgLower = payload.message.toLowerCase();
        const isCompletion = hasDetails ||
          payload.status === 'passed' ||
          payload.status === 'completed' ||
          msgLower.includes('completed') ||
          msgLower.includes('created') ||
          msgLower.includes('optimized') ||
          msgLower.includes('executed') ||
          msgLower.includes('passed') ||
          msgLower.includes('check passed') ||
          msgLower.includes('retry needed') ||
          msgLower.includes('failed');

        if (isCompletion) {
          // Add agent to completed list
          setCompletedAgents((prev) =>
            prev.includes(agentType) ? prev : [...prev, agentType]
          );
        }

        const activity: AgentActivity = {
          agent: agentType,
          status: isCompletion ? 'completed' : 'running',
          message: payload.message,
          startedAt: new Date().toISOString(),
          completedAt: isCompletion ? new Date().toISOString() : undefined,
          details: payload.details as AgentDetails | undefined,
        };
        setCurrentActivity(activity);

        // Add to activity history - update existing running entry if completing same agent
        setAgentHistory((prev) => {
          if (isCompletion) {
            // Find and update the last running entry for this agent
            const lastRunningIndex = [...prev].reverse().findIndex(
              (a) => a.agent === agentType && a.status === 'running'
            );
            if (lastRunningIndex !== -1) {
              const actualIndex = prev.length - 1 - lastRunningIndex;
              const updated = [...prev];
              updated[actualIndex] = activity;
              return updated;
            }
          }
          return [...prev, activity];
        });

        // If conductor completed, initialize all milestones from details
        if (agentType === 'conductor' && isCompletion && payload.details) {
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

            // Update streaming message with milestones
            setMessages((prev) => {
              const targetId = streamingMessageIdRef.current;

              // First check if we have a streaming message to update
              const streamingMsg = prev.find((msg) => (targetId && msg.id === targetId) || msg.isStreaming);

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
                // No streaming message yet - create one with milestones
                // This can happen if conductor message arrives before TASK_STARTED
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

            // Update streaming state with total milestones
            setStreaming((prev) => ({
              ...prev,
              isStreaming: true,
              totalMilestones: conductorDetails.milestones.length,
            }));
            break; // Skip the default message update since we already did it
          }
        }

        // If worker completed with artifacts, add them to the message
        if (agentType === 'worker' && isCompletion && payload.details) {
          const workerDetails = payload.details as WorkerDetails;
          if (workerDetails.artifacts && workerDetails.artifacts.length > 0) {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === streamingMessageIdRef.current
                  ? {
                    ...msg,
                    artifacts: [...(msg.artifacts || []), ...workerDetails.artifacts!],
                    rawContent: workerDetails.output,  // Store raw output with code blocks
                    agentActivity: [...(msg.agentActivity || []), activity],
                  }
                  : msg
              )
            );
            break; // Skip the default activity update since we already did it
          }
        }

        // Update message with activity
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
        break;
      }

      case WSMessageType.MILESTONE_COMPLETED: {
        const payload = message.payload as MilestoneProgressPayload;
        const agent = payload.agent as AgentType;

        // Add agent to completed list if not already there
        setCompletedAgents((prev) =>
          prev.includes(agent) ? prev : [...prev, agent]
        );

        setCurrentActivity((prev) =>
          prev
            ? {
              ...prev,
              status: 'completed',
              completedAt: new Date().toISOString(),
            }
            : null
        );

        // Update milestone status in message (update existing or add new)
        if (streamingMessageIdRef.current) {
          setMessages((prev) =>
            prev.map((msg) => {
              if (msg.id !== streamingMessageIdRef.current) return msg;

              const existingMilestones = msg.milestones || [];
              // Find milestone by sequence number and update its status
              const milestoneIndex = existingMilestones.findIndex(
                (m) => m.sequenceNumber === payload.sequence_number
              );

              if (milestoneIndex >= 0) {
                // Update existing milestone
                const updatedMilestones = [...existingMilestones];
                updatedMilestones[milestoneIndex] = {
                  ...updatedMilestones[milestoneIndex],
                  id: payload.milestone_id,
                  status: 'passed' as MilestoneStatus,
                };
                return { ...msg, milestones: updatedMilestones };
              } else {
                // Add new milestone if not found (fallback)
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
        break;
      }

      case WSMessageType.MILESTONE_RETRY: {
        const payload = message.payload as MilestoneProgressPayload;
        // Update QA result for retry
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
        break;
      }

      case WSMessageType.LLM_CHUNK: {
        const payload = message.payload as LLMChunkPayload;
        setStreaming((prev) => ({
          ...prev,
          currentAgent: payload.agent as AgentType,
          chunks: [...prev.chunks, payload.chunk],
        }));

        // Update message content
        if (streamingMessageIdRef.current) {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === streamingMessageIdRef.current
                ? { ...msg, content: msg.content + payload.chunk }
                : msg
            )
          );
        }
        break;
      }

      case WSMessageType.LLM_COMPLETE: {
        const payload = message.payload as LLMCompletePayload;
        setCurrentActivity(null);

        // Update usage for current milestone
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
        break;
      }

      case WSMessageType.TASK_COMPLETED: {
        const payload = message.payload as TaskCompletedPayload;

        // Extract user-facing message (without code blocks/artifacts)
        const userMessage = extractUserMessage(payload.final_result);

        // Finalize message
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
                }
                : msg
            )
          );
        }

        // Update stats
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
        break;
      }

      case WSMessageType.TASK_FAILED: {
        const payload = message.payload as TaskFailedPayload;

        // Update message with error
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
        break;
      }

      case WSMessageType.CONTEXT_COMPRESSED: {
        // Show system message about context compression
        const systemMessage: ChatMessage = {
          id: `sys-${Date.now()}`,
          role: 'system',
          content: 'Context was compressed to free up memory.',
          timestamp: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, systemMessage]);
        break;
      }
    }
  }, [onError, updateSessionTitle]);

  // WebSocket connection with auth token
  const { isConnected, reconnect: wsReconnect } = useWebSocket({
    sessionId: sessionId || undefined,
    token: accessToken || undefined,
    onMessage: handleWebSocketMessage,
  });

  // Create new chat session
  const createNewChat = useCallback(async (): Promise<string> => {
    setIsLoading(true);
    setError(null);

    try {
      const session = await api.createSession();
      setSessionId(session.id);
      setMessages([]);
      setStats({
        totalTokens: 0,
        totalCostUsd: 0,
        inputTokens: 0,
        outputTokens: 0,
      });
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

      // Convert tasks to messages
      const loadedMessages: ChatMessage[] = [];
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
          let artifacts: ArtifactData[] = [];

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
                selectedModel: m.llm_model || undefined,
                usage: {
                  inputTokens: m.input_tokens,
                  outputTokens: m.output_tokens,
                  costUsd: parseFloat(m.cost_usd),
                  model: m.llm_model || 'unknown',
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
                  model: m.llm_model || undefined,
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

          // Fetch artifacts
          try {
            const artifactResult = await api.getArtifacts(targetSessionId, task.id);
            if (artifactResult.items) {
              artifacts = artifactResult.items.map((a) => ({
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

          loadedMessages.push({
            id: `assistant-${task.id}`,
            role: 'assistant',
            content: task.final_result,
            timestamp: task.updated_at,
            taskId: task.id,
            milestones,
            agentActivity,
            artifacts: artifacts.length > 0 ? artifacts : undefined,
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
      await api.createTask(currentSessionId, content);
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

  // Set API token when auth changes
  useEffect(() => {
    if (accessToken) {
      api.setToken(accessToken);
    }
  }, [accessToken]);

  // Load initial session if provided (after token is set)
  const hasLoadedRef = useRef<string | null>(null);
  useEffect(() => {
    if (initialSessionId && accessToken && hasLoadedRef.current !== initialSessionId) {
      hasLoadedRef.current = initialSessionId;
      loadSession(initialSessionId);
    }
  }, [initialSessionId, accessToken, loadSession]);

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
    sendMessage,
    cancelTask,
    createNewChat,
    loadSession,
    clearError,
  };
}
