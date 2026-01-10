/**
 * MCP (Model Context Protocol) type definitions.
 * These types mirror the backend schemas from agent.api.schemas.mcp
 */

export type TransportType = 'stdio' | 'http' | 'sse';
export type AuthType = 'bearer' | 'api_key' | 'oauth2' | 'basic' | 'none';
export type ApprovalMode = 'always' | 'never' | 'conditional';

/**
 * MCP server response (list view).
 */
export interface McpServerResponse {
  id: string;
  user_id: string;
  name: string;
  description: string | null;
  transport_type: TransportType;
  server_url: string | null;
  auth_type: AuthType | null;
  has_credentials: boolean;
  has_stdio_config: boolean;
  available_tools: string[] | null;
  require_approval: ApprovalMode;
  enabled_for_worker: boolean;
  enabled_for_qa: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/**
 * stdio configuration for native app execution.
 */
export interface McpStdioConfig {
  command: string;
  args: string[];
  env_vars: Record<string, string>;
}

/**
 * MCP server detailed response (includes stdio config).
 */
export interface McpServerDetailResponse extends McpServerResponse {
  stdio_config?: McpStdioConfig;
}

/**
 * Request to create a new MCP server.
 */
export interface McpServerCreateRequest {
  name: string;
  description?: string;
  transport_type: TransportType;
  // HTTP/SSE
  server_url?: string;
  auth_type?: AuthType;
  auth_credentials?: Record<string, string>;
  // stdio
  command?: string;
  args?: string[];
  env_vars?: Record<string, string>;
  // Configuration
  available_tools?: string[];
  require_approval?: ApprovalMode;
  enabled_for_worker?: boolean;
  enabled_for_qa?: boolean;
}

/**
 * Request to update an MCP server.
 */
export interface McpServerUpdateRequest {
  name?: string;
  description?: string;
  is_active?: boolean;
  // HTTP/SSE
  server_url?: string;
  auth_type?: AuthType;
  auth_credentials?: Record<string, string>;
  // stdio
  command?: string;
  args?: string[];
  env_vars?: Record<string, string>;
  // Configuration
  available_tools?: string[];
  require_approval?: ApprovalMode;
  enabled_for_worker?: boolean;
  enabled_for_qa?: boolean;
}

/**
 * MCP server connection test response.
 */
export interface McpServerTestResponse {
  success: boolean;
  error: string | null;
  available_tools: string[] | null;
  latency_ms: number | null;
}

/**
 * MCP tool schema definition.
 */
export interface McpToolSchema {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

/**
 * MCP tool execution log entry.
 */
export interface McpToolExecutionLog {
  id: string;
  user_id: string;
  session_id: string;
  task_id: string | null;
  milestone_id: string | null;
  mcp_server_id: string;
  tool_name: string;
  tool_input: Record<string, unknown>;
  tool_output: Record<string, unknown> | null;
  agent_type: 'worker' | 'qa';
  execution_time_ms: number | null;
  status: 'success' | 'error' | 'rejected';
  error_message: string | null;
  required_approval: boolean;
  approved_by_user: boolean | null;
  created_at: string;
}

/**
 * Paginated response for logs.
 */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

// OAuth2 related types
export interface McpOAuthStartRequest {
  server_url: string;
  callback_url: string;
}

export interface McpOAuthStartResponse {
  authorization_url: string;
  state: string;
}

export interface McpOAuthCallbackRequest {
  code: string;
  state: string;
  server_id: string;
}

export interface McpOAuthCallbackResponse {
  success: boolean;
  error: string | null;
}

export interface McpOAuthStatus {
  has_oauth_tokens: boolean;
  auth_type: string | null;
}
