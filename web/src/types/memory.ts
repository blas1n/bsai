export type MemoryType = 'task_result' | 'learning' | 'error' | 'user_preference';

export interface Memory {
  id: string;
  user_id: string;
  session_id: string;
  task_id: string | null;
  summary: string;
  memory_type: string;
  importance_score: number;
  access_count: number;
  tags: string[] | null;
  created_at: string;
  last_accessed_at: string | null;
}

export interface MemoryDetail extends Memory {
  content: string;
  metadata_json: Record<string, unknown> | null;
}

export interface MemorySearchResult {
  memory: Memory;
  similarity: number;
}

export interface MemorySearchRequest {
  query: string;
  limit?: number;
  memory_types?: string[];
  min_similarity?: number;
}

export interface MemoryStats {
  total_memories: number;
  by_type: Record<string, number>;
  average_importance: number;
}

export interface ConsolidateResult {
  consolidated_count: number;
  remaining_count: number;
}

export interface DecayResult {
  decayed_count: number;
}
