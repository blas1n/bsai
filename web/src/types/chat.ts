import { TaskComplexity, MilestoneStatus } from './session';
import { AgentDetails, ArtifactData } from './websocket';

// Agent types in the workflow
export type AgentType =
  | 'conductor'
  | 'meta_prompter'
  | 'worker'
  | 'qa'
  | 'summarizer'
  | 'responder'
  | 'advance'
  | 'recovery'
  | 'replan'
  | 'artifact_extractor'
  | 'task_summary';

// Re-export for convenience
export type { ArtifactData } from './websocket';

// QA decision types
export type QADecision = 'pass' | 'retry' | 'fail';

// Message roles
export type MessageRole = 'user' | 'assistant' | 'system';

// Chat message with BSAI-specific metadata
export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: string;

  // BSAI-specific fields (only for assistant messages)
  taskId?: string;
  milestones?: MilestoneInfo[];
  agentActivity?: AgentActivity[];
  usage?: MessageUsage;
  isStreaming?: boolean;
  artifacts?: ArtifactData[];  // Extracted artifacts from worker output
  rawContent?: string;  // Original content with code blocks (for artifact extraction)
  /** Langfuse trace URL for debugging and observability (empty string if not available) */
  traceUrl?: string;
}

// Milestone information for display
export interface MilestoneInfo {
  id: string;
  sequenceNumber: number;
  title: string;
  description: string;
  complexity: TaskComplexity;
  status: MilestoneStatus;
  selectedModel?: string;
  qaResult?: QAResult;
  usage?: MilestoneUsage;
}

// QA result for a milestone
export interface QAResult {
  decision: QADecision;
  feedback?: string;
  retryCount: number;
  maxRetries: number;
}

// Agent activity tracking
export interface AgentActivity {
  agent: AgentType;
  status: 'pending' | 'running' | 'completed' | 'failed';
  message?: string;
  startedAt?: string;
  completedAt?: string;
  model?: string;
  details?: AgentDetails;
}

// Token and cost usage for a message
export interface MessageUsage {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  costUsd: number;
  model: string;
}

// Token and cost usage for a milestone
export interface MilestoneUsage {
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
  model: string;
  duration?: number;
}

// Conversation (session) summary for sidebar
export interface Conversation {
  id: string;
  title: string;
  preview: string;
  status: 'active' | 'paused' | 'completed' | 'failed';
  messageCount: number;
  totalTokens: number;
  totalCostUsd: number;
  createdAt: string;
  updatedAt: string;
}

// Grouped conversations by date
export interface ConversationGroup {
  label: string;
  conversations: Conversation[];
}

// Session stats for sidebar
export interface SessionStats {
  totalTokens: number;
  totalCostUsd: number;
  inputTokens: number;
  outputTokens: number;
}

// Streaming state
export interface StreamingState {
  isStreaming: boolean;
  currentAgent?: AgentType;
  currentMilestone?: number;
  totalMilestones?: number;
  chunks: string[];
}

// Chat state
export interface ChatState {
  sessionId: string | null;
  messages: ChatMessage[];
  isLoading: boolean;
  error: string | null;
  streaming: StreamingState;
  stats: SessionStats;
}

// Agent display info
export const AGENT_DISPLAY: Record<AgentType, { label: string; color: string; icon: string }> = {
  conductor: { label: 'Conductor', color: 'blue', icon: '🎯' },
  meta_prompter: { label: 'Meta Prompter', color: 'purple', icon: '✨' },
  worker: { label: 'Worker', color: 'green', icon: '⚙️' },
  qa: { label: 'QA Agent', color: 'orange', icon: '✓' },
  summarizer: { label: 'Summarizer', color: 'gray', icon: '📝' },
  responder: { label: 'Responder', color: 'teal', icon: '💬' },
  advance: { label: 'Advance', color: 'indigo', icon: '➡️' },
  recovery: { label: 'Recovery', color: 'red', icon: '🔄' },
  replan: { label: 'Replan', color: 'amber', icon: '📋' },
  artifact_extractor: { label: 'Artifact Extractor', color: 'cyan', icon: '📦' },
  task_summary: { label: 'Task Summary', color: 'lime', icon: '📊' },
};

// Complexity display info
export const COMPLEXITY_DISPLAY: Record<TaskComplexity, { label: string; color: string }> = {
  trivial: { label: 'Trivial', color: 'gray' },
  simple: { label: 'Simple', color: 'green' },
  moderate: { label: 'Moderate', color: 'blue' },
  complex: { label: 'Complex', color: 'orange' },
  context_heavy: { label: 'Context Heavy', color: 'red' },
};

// QA decision display info
export const QA_DECISION_DISPLAY: Record<QADecision, { label: string; color: string; icon: string }> = {
  pass: { label: 'Passed', color: 'green', icon: '✓' },
  retry: { label: 'Retry', color: 'yellow', icon: '↻' },
  fail: { label: 'Failed', color: 'red', icon: '✗' },
};
