"""MCP API request/response schemas."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class McpStdioConfig(BaseModel):
    """stdio MCP server execution configuration."""

    command: str = Field(..., description="Executable command")
    args: list[str] = Field(default_factory=list, description="Command arguments")
    env_vars: dict[str, str] = Field(default_factory=dict, description="Environment variables")


class McpServerCreateRequest(BaseModel):
    """Request to create MCP server configuration."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Server name (alphanumeric, underscore, hyphen only)",
    )
    description: str | None = Field(None, description="Optional description")
    transport_type: Literal["stdio", "http", "sse"] = Field(..., description="Transport type")

    # HTTP/SSE specific
    server_url: str | None = Field(None, max_length=500, description="Server URL for HTTP/SSE")
    auth_type: Literal["bearer", "api_key", "oauth2", "basic", "none"] | None = Field(
        None, description="Authentication type"
    )
    auth_credentials: dict[str, str] | None = Field(
        None, description="Authentication credentials (will be encrypted)"
    )

    # stdio specific
    command: str | None = Field(None, description="Command for stdio server")
    args: list[str] | None = Field(None, description="Command arguments for stdio")
    env_vars: dict[str, str] | None = Field(None, description="Environment variables for stdio")

    # Configuration
    available_tools: list[str] | None = Field(
        None, description="Optional list of allowed tool names"
    )
    require_approval: Literal["always", "never", "conditional"] = Field(
        "always", description="Tool approval requirement"
    )
    enabled_for_worker: bool = Field(True, description="Enable for Worker agent")
    enabled_for_qa: bool = Field(True, description="Enable for QA agent")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate server name."""
        if not v or not v.strip():
            raise ValueError("Server name cannot be empty")
        return v.strip()

    def model_post_init(self, __context: Any) -> None:
        """Validate transport-specific fields after model creation."""
        if self.transport_type in ["http", "sse"]:
            if not self.server_url:
                raise ValueError(f"server_url is required for {self.transport_type} transport")
        elif self.transport_type == "stdio":
            if not self.command:
                raise ValueError("command is required for stdio transport")


class McpServerUpdateRequest(BaseModel):
    """Request to update MCP server configuration."""

    name: str | None = Field(None, min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    description: str | None = None
    is_active: bool | None = None

    # HTTP/SSE updates
    server_url: str | None = None
    auth_type: Literal["bearer", "api_key", "oauth2", "basic", "none"] | None = None
    auth_credentials: dict[str, str] | None = None

    # stdio updates
    command: str | None = None
    args: list[str] | None = None
    env_vars: dict[str, str] | None = None

    # Configuration updates
    available_tools: list[str] | None = None
    require_approval: Literal["always", "never", "conditional"] | None = None
    enabled_for_worker: bool | None = None
    enabled_for_qa: bool | None = None


class McpServerResponse(BaseModel):
    """MCP server configuration response (excludes sensitive data)."""

    id: UUID
    user_id: str
    name: str
    description: str | None
    transport_type: str

    # HTTP/SSE info (credentials excluded for security)
    server_url: str | None
    auth_type: str | None
    has_credentials: bool = Field(..., description="Whether credentials are configured")

    # stdio info (command info excluded for web users)
    has_stdio_config: bool = Field(..., description="Whether stdio config is available")

    # Configuration
    available_tools: list[str] | None
    require_approval: str
    enabled_for_worker: bool
    enabled_for_qa: bool

    # Metadata
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class McpServerDetailResponse(McpServerResponse):
    """Detailed MCP server response including stdio config for native apps."""

    stdio_config: McpStdioConfig | None = Field(
        None, description="stdio execution config (only for native apps)"
    )


class McpToolSchema(BaseModel):
    """MCP tool definition."""

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    input_schema: dict[str, Any] = Field(..., description="JSON Schema for tool input")


class McpServerTestRequest(BaseModel):
    """Request to test MCP server connection."""

    pass  # No additional parameters needed, uses server config


class McpServerTestResponse(BaseModel):
    """Response from MCP server connection test."""

    success: bool = Field(..., description="Whether connection test succeeded")
    error: str | None = Field(None, description="Error message if failed")
    available_tools: list[str] | None = Field(None, description="List of available tool names")
    latency_ms: int | None = Field(None, description="Connection latency in milliseconds")


class McpToolExecutionLogResponse(BaseModel):
    """MCP tool execution log entry."""

    id: UUID
    tool_name: str
    tool_input: dict[str, Any]
    tool_output: dict[str, Any] | None
    status: str  # "success" | "error" | "rejected"
    execution_time_ms: int | None
    agent_type: str
    error_message: str | None
    required_approval: bool
    approved_by_user: bool | None
    created_at: datetime

    model_config = {"from_attributes": True}


class McpLogQueryParams(BaseModel):
    """Query parameters for MCP tool execution logs."""

    session_id: UUID | None = Field(None, description="Filter by session")
    status: Literal["success", "error", "rejected"] | None = Field(
        None, description="Filter by status"
    )
    agent_type: Literal["worker", "qa"] | None = Field(None, description="Filter by agent type")
    limit: int = Field(100, ge=1, le=1000, description="Maximum number of logs")
    offset: int = Field(0, ge=0, description="Number of logs to skip")


class PaginatedResponse(BaseModel):
    """Paginated response wrapper."""

    items: list[Any] = Field(..., description="List of items")
    total: int = Field(..., description="Total number of items")
    limit: int = Field(..., description="Items per page")
    offset: int = Field(..., description="Number of items skipped")
    has_more: bool = Field(..., description="Whether more items are available")
