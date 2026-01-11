"""API configuration settings.

Provides settings for authentication, caching, and API behavior.
"""

from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database connection settings."""

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/bsai",
        description="PostgreSQL connection URL (must use asyncpg driver)",
    )

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")


class AuthSettings(BaseSettings):
    """Keycloak authentication settings for fastapi-keycloak-middleware."""

    keycloak_url: str = Field(
        default="http://localhost:8080",
        description="Keycloak server URL",
    )
    keycloak_realm: str = Field(
        default="bsai",
        description="Keycloak realm name",
    )
    keycloak_client_id: str = Field(
        default="bsai-api",
        description="Keycloak client ID",
    )
    keycloak_client_secret: str | None = Field(
        default=None,
        description="Keycloak client secret (for introspection endpoint)",
    )
    auth_enabled: bool = Field(
        default=True,
        description="Enable Keycloak authentication. Set to False for testing.",
    )

    model_config = SettingsConfigDict(env_file=".env", env_prefix="AUTH_", extra="ignore")


class CacheSettings(BaseSettings):
    """Redis cache settings."""

    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    redis_max_connections: int = Field(
        default=20,
        description="Maximum number of Redis connections",
    )

    # TTL settings (in seconds)
    session_state_ttl: int = Field(default=3600, description="Session state TTL")
    session_context_ttl: int = Field(default=1800, description="Context TTL")
    task_progress_ttl: int = Field(default=900, description="Task progress TTL")
    user_sessions_ttl: int = Field(default=600, description="User sessions TTL")

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CACHE_", extra="ignore")


class APISettings(BaseSettings):
    """General API settings."""

    title: str = Field(
        default="BSAI API",
        description="API title",
    )
    description: str = Field(
        default="Multi-Agent LLM Orchestration System API",
        description="API description",
    )
    version: str = Field(
        default="1.0.0",
        description="API version",
    )
    debug: bool = Field(default=False, description="Enable debug mode")
    api_prefix: str = Field(default="/api/v1", description="API route prefix")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:13000"],
        description="Allowed CORS origins",
    )

    # Pagination defaults
    default_page_size: int = Field(default=20, description="Default page size")
    max_page_size: int = Field(default=100, description="Maximum page size")

    # Request limits
    max_request_body_size: int = Field(
        default=10 * 1024 * 1024,  # 10MB
        description="Maximum request body size",
    )

    model_config = SettingsConfigDict(env_file=".env", env_prefix="API_", extra="ignore")


@lru_cache
def get_database_settings() -> DatabaseSettings:
    """Get cached database settings."""
    return DatabaseSettings()


@lru_cache
def get_auth_settings() -> AuthSettings:
    """Get cached auth settings."""
    return AuthSettings()


@lru_cache
def get_cache_settings() -> CacheSettings:
    """Get cached cache settings."""
    return CacheSettings()


class AgentSettings(BaseSettings):
    """Agent-specific settings for consistency control.

    Lower temperature values produce more consistent, deterministic outputs.
    Higher values produce more creative but variable outputs.
    """

    # Temperature settings (0.0-2.0, lower = more consistent)
    conductor_temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Conductor agent temperature for task analysis",
    )
    meta_prompter_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Meta Prompter temperature for prompt generation",
    )
    worker_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Worker agent temperature for task execution",
    )
    worker_max_tokens: int = Field(
        default=16000,
        ge=1000,
        le=128000,
        description="Worker agent max output tokens (increase for large content)",
    )
    qa_temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="QA agent temperature for validation decisions",
    )
    summarizer_temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Summarizer temperature for context compression",
    )

    # Workflow control settings
    max_milestone_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum retry attempts per milestone before failing",
    )
    max_tool_iterations: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum tool calling iterations in LLM completion",
    )

    model_config = SettingsConfigDict(env_file=".env", env_prefix="AGENT_", extra="ignore")


@lru_cache
def get_api_settings() -> APISettings:
    """Get cached API settings."""
    return APISettings()


@lru_cache
def get_agent_settings() -> AgentSettings:
    """Get cached agent settings."""
    return AgentSettings()


class McpSettings(BaseSettings):
    """MCP (Model Context Protocol) security and configuration settings."""

    # Encryption key for credentials (base64-encoded Fernet key)
    # If not provided, a random key will be generated (works but doesn't persist across restarts)
    # For production, set MCP_ENCRYPTION_KEY to persist encrypted credentials
    encryption_key: str = Field(
        default="",
        description="Fernet encryption key for MCP credentials (base64). Auto-generated if not set.",
    )

    # Cache for auto-generated key
    _generated_key: str | None = None

    def get_encryption_key(self) -> str:
        """Get encryption key, generating one if not configured.

        Returns:
            Fernet-compatible encryption key (base64-encoded)

        Note:
            If MCP_ENCRYPTION_KEY is not set, a random key is generated.
            This works but encrypted data won't persist across application restarts.
        """
        if self.encryption_key:
            return self.encryption_key

        # Generate and cache a random key if not configured
        if self._generated_key is None:
            self._generated_key = Fernet.generate_key().decode()
        return self._generated_key

    # Allowlisted commands for stdio MCP servers
    allowed_stdio_commands: list[str] = Field(
        default=["npx", "node", "python", "python3", "deno"],
        description="Allowlisted commands for stdio MCP servers",
    )

    # Blocked URL patterns for SSRF prevention (regex patterns)
    blocked_url_patterns: list[str] = Field(
        default=[
            r"^https?://localhost",
            r"^https?://127\.0\.0\.1",
            r"^https?://0\.0\.0\.0",
            r"^https?://10\.",
            r"^https?://172\.(1[6-9]|2[0-9]|3[01])\.",
            r"^https?://192\.168\.",
            r"^https?://169\.254\.",
            r"^https?://\[::1\]",
            r"^https?://\[0:0:0:0:0:0:0:1\]",
        ],
        description="Blocked URL patterns for SSRF prevention",
    )

    # Rate limiting
    tool_calls_per_hour: int = Field(
        default=100,
        description="Maximum tool calls per user per hour",
    )

    # Resource limits
    tool_execution_timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Tool execution timeout in seconds",
    )
    max_tool_calls_per_request: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum tool calls in a single LLM request",
    )
    max_tool_output_size: int = Field(
        default=1024 * 1024,  # 1MB
        description="Maximum tool output size in bytes",
    )

    # Risk assessment keywords
    high_risk_keywords: list[str] = Field(
        default=[
            "delete",
            "remove",
            "destroy",
            "drop",
            "truncate",
            "execute",
            "exec",
            "eval",
            "system",
            "shell",
            "kill",
            "terminate",
        ],
        description="Keywords that indicate high-risk tool operations",
    )
    medium_risk_keywords: list[str] = Field(
        default=[
            "write",
            "update",
            "modify",
            "create",
            "change",
            "edit",
            "move",
            "rename",
        ],
        description="Keywords that indicate medium-risk tool operations",
    )

    model_config = SettingsConfigDict(env_file=".env", env_prefix="MCP_", extra="ignore")


@lru_cache
def get_mcp_settings() -> McpSettings:
    """Get cached MCP settings.

    Returns:
        McpSettings instance
    """
    return McpSettings()


class LangfuseSettings(BaseSettings):
    """Langfuse observability settings for LLM tracing.

    Configure connection to Langfuse Cloud or self-hosted instance for
    tracing, debugging, and monitoring LLM operations.
    """

    enabled: bool = Field(
        default=True,
        description="Enable Langfuse tracing. Set to False to disable.",
    )
    host: str = Field(
        default="https://cloud.langfuse.com",
        description="Langfuse server URL (default: Langfuse Cloud)",
    )
    public_key: str = Field(
        default="",
        description="Langfuse public API key",
    )
    secret_key: str = Field(
        default="",
        description="Langfuse secret API key",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug logging for Langfuse SDK",
    )
    flush_at: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Number of events to accumulate before flushing",
    )
    flush_interval: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="Maximum time in seconds between flushes",
    )
    sample_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Sampling rate for traces (1.0 = trace everything)",
    )

    model_config = SettingsConfigDict(env_file=".env", env_prefix="LANGFUSE_", extra="ignore")


@lru_cache
def get_langfuse_settings() -> LangfuseSettings:
    """Get cached Langfuse settings.

    Returns:
        LangfuseSettings instance
    """
    return LangfuseSettings()
