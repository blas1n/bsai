"""API configuration settings.

Provides settings for authentication, caching, and API behavior.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    model_config = SettingsConfigDict(
        env_prefix="AUTH_",
        env_file=".env",
        extra="ignore",
    )


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

    model_config = SettingsConfigDict(
        env_prefix="CACHE_",
        env_file=".env",
        extra="ignore",
    )


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
        default=["http://localhost:3000"],
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

    model_config = SettingsConfigDict(
        env_prefix="API_",
        env_file=".env",
        extra="ignore",
    )


@lru_cache
def get_auth_settings() -> AuthSettings:
    """Get cached auth settings."""
    return AuthSettings()


@lru_cache
def get_cache_settings() -> CacheSettings:
    """Get cached cache settings."""
    return CacheSettings()


@lru_cache
def get_api_settings() -> APISettings:
    """Get cached API settings."""
    return APISettings()
