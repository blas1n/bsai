"""
Application configuration using Pydantic Settings
"""

from typing import List
from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    ENVIRONMENT: str = Field(default="development", description="Environment name")
    HOST: str = Field(default="0.0.0.0", description="Server host")
    PORT: int = Field(default=8000, description="Server port")
    DEBUG: bool = Field(default=False, description="Debug mode")

    # CORS
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Allowed CORS origins",
    )

    # Database
    DATABASE_URL: PostgresDsn = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/bsai",
        description="PostgreSQL connection URL",
    )
    DB_POOL_SIZE: int = Field(default=10, description="Database connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=20, description="Database max overflow")

    # Redis
    REDIS_URL: RedisDsn = Field(
        default="redis://localhost:6379/0", description="Redis connection URL"
    )
    REDIS_MAX_CONNECTIONS: int = Field(
        default=50, description="Redis max connections"
    )

    # LLM Providers
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API Key")
    ANTHROPIC_API_KEY: str = Field(default="", description="Anthropic API Key")
    GOOGLE_API_KEY: str = Field(default="", description="Google AI API Key")

    # Security
    SECRET_KEY: str = Field(
        default="your-secret-key-change-in-production",
        description="Secret key for JWT",
    )
    ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30, description="Access token expiration"
    )

    # Observability
    OTLP_ENDPOINT: str = Field(
        default="http://localhost:4317", description="OpenTelemetry collector endpoint"
    )
    ENABLE_TRACING: bool = Field(default=True, description="Enable OpenTelemetry tracing")
    TRACE_SAMPLE_RATE: float = Field(
        default=1.0, description="Trace sampling rate (0.0-1.0)"
    )

    # Sentry (optional)
    SENTRY_DSN: str = Field(default="", description="Sentry DSN for error tracking")

    # Cost Management
    MONTHLY_BUDGET_USD: float = Field(
        default=1000.0, description="Monthly LLM budget in USD"
    )
    COST_ALERT_THRESHOLD: float = Field(
        default=0.8, description="Alert threshold (0.8 = 80%)"
    )


# Global settings instance
settings = Settings()
