export type SessionStatus = 'active' | 'paused' | 'completed' | 'failed';

export interface Session {
  id: string;
  user_id: string;
  status: string;  // API returns string
  title: string | null;  // Conversation preview from first task
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: string;
  created_at: string;
  updated_at: string;
}

export interface SessionWithTasks extends Session {
  tasks: Task[];
}

export interface Task {
  id: string;
  session_id: string;
  original_request: string;
  status: string;  // API returns string
  final_result: string | null;
  created_at: string;
  updated_at: string;
}

export type TaskStatus = 'pending' | 'in_progress' | 'completed' | 'failed' | 'cancelled' | 'paused';

export interface TaskWithMilestones extends Task {
  milestones: Milestone[];
}

export interface Milestone {
  id: string;
  task_id: string;
  sequence_number: number;
  title: string;
  description: string;
  complexity: string;  // API returns string
  status: string;  // API returns string
  llm_model: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: string;
  created_at: string;
  completed_at: string | null;
}

export type TaskComplexity = 'trivial' | 'simple' | 'moderate' | 'complex' | 'context_heavy';

export type MilestoneStatus = 'pending' | 'in_progress' | 'completed' | 'passed' | 'failed';
