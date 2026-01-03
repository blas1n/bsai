// WebSocket message types matching backend schemas

export enum WSMessageType {
  // Client -> Server
  AUTH = 'auth',
  SUBSCRIBE = 'subscribe',
  UNSUBSCRIBE = 'unsubscribe',
  PING = 'ping',

  // Server -> Client (Auth)
  AUTH_SUCCESS = 'auth_success',
  AUTH_ERROR = 'auth_error',
  SUBSCRIBED = 'subscribed',
  UNSUBSCRIBED = 'unsubscribed',
  PONG = 'pong',

  // Task Events
  TASK_STARTED = 'task_started',
  TASK_PROGRESS = 'task_progress',
  TASK_COMPLETED = 'task_completed',
  TASK_FAILED = 'task_failed',

  // Milestone Events
  MILESTONE_STARTED = 'milestone_started',
  MILESTONE_PROGRESS = 'milestone_progress',
  MILESTONE_COMPLETED = 'milestone_completed',
  MILESTONE_FAILED = 'milestone_failed',
  MILESTONE_RETRY = 'milestone_retry',

  // LLM Streaming
  LLM_CHUNK = 'llm_chunk',
  LLM_COMPLETE = 'llm_complete',

  // Session Events
  SESSION_PAUSED = 'session_paused',
  SESSION_RESUMED = 'session_resumed',
  CONTEXT_COMPRESSED = 'context_compressed',

  // Errors
  ERROR = 'error',
}

export interface WSMessage<T = unknown> {
  type: WSMessageType;
  payload: T;
  timestamp: string;
  request_id?: string;
}

// Previous milestone info for session continuity
export interface PreviousMilestoneInfo {
  id: string;
  sequence_number: number;
  description: string;
  complexity: string;
  status: string;
  worker_output?: string | null;
}

// Payload types
export interface TaskStartedPayload {
  task_id: string;
  session_id: string;
  original_request: string;
  milestone_count: number;
  previous_milestones?: PreviousMilestoneInfo[];
}

export interface TaskProgressPayload {
  task_id: string;
  current_milestone: number;
  total_milestones: number;
  progress: number;
  current_milestone_title: string;
}

export interface TaskCompletedPayload {
  task_id: string;
  final_result: string;
  total_tokens: number;
  total_cost_usd: string;
  duration_seconds: number;
}

export interface TaskFailedPayload {
  task_id: string;
  error: string;
  failed_milestone?: number;
}

export interface MilestoneProgressPayload {
  milestone_id: string;
  task_id: string;
  sequence_number: number;
  status: string;
  agent: string;
  message: string;
  details?: AgentDetails;
}

// Agent-specific detail types
export interface ConductorDetails {
  milestones: Array<{
    index: number;
    description: string;
    complexity: string;
    acceptance_criteria: string;
  }>;
}

export interface MetaPrompterDetails {
  generated_prompt: string;
  prompt_length: number;
  milestone_description: string;
}

export interface ArtifactData {
  id: string;
  type: string;
  filename: string;
  language: string | null;
  content: string;
  path: string | null;
}

export interface WorkerDetails {
  output: string;
  output_preview: string;
  output_length: number;
  tokens_used: number;
  input_tokens: number;
  output_tokens: number;
  model: string;
  cost_usd: number;
  is_retry: boolean;
  artifacts?: ArtifactData[];
}

export interface QADetails {
  decision: string;
  feedback: string | null;
  acceptance_criteria: string;
  attempt_number: number;
  max_retries: number;
}

export interface SummarizerDetails {
  summary: string;
  summary_preview: string;
  old_message_count: number;
  new_message_count: number;
  tokens_saved_estimate: number;
}

export type AgentDetails =
  | ConductorDetails
  | MetaPrompterDetails
  | WorkerDetails
  | QADetails
  | SummarizerDetails
  | Record<string, unknown>;

export interface LLMChunkPayload {
  task_id: string;
  milestone_id: string;
  chunk: string;
  chunk_index: number;
  agent: string;
}

export interface LLMCompletePayload {
  task_id: string;
  milestone_id: string;
  full_content: string;
  tokens_used: number;
  agent: string;
}

export interface ErrorPayload {
  code: string;
  message: string;
}
