"""Configuration tests."""

from __future__ import annotations

from agent.api.config import (
    AgentSettings,
    APISettings,
    AuthSettings,
    CacheSettings,
    LangfuseSettings,
    McpSettings,
    get_agent_settings,
    get_api_settings,
    get_auth_settings,
    get_cache_settings,
    get_langfuse_settings,
    get_mcp_settings,
)


class TestAuthSettings:
    """Auth settings tests."""

    def test_custom_values(self) -> None:
        """Custom values can be set."""
        settings = AuthSettings(
            keycloak_url="https://auth.example.com",
            keycloak_realm="test-realm",
            keycloak_client_id="test-client",
            keycloak_client_secret="secret123",
        )

        assert settings.keycloak_url == "https://auth.example.com"
        assert settings.keycloak_realm == "test-realm"
        assert settings.keycloak_client_id == "test-client"
        assert settings.keycloak_client_secret == "secret123"


class TestCacheSettings:
    """Cache settings tests."""

    def test_custom_values(self) -> None:
        """Custom values can be set."""
        settings = CacheSettings(
            redis_url="redis://custom:6379/1",
            redis_max_connections=50,
        )

        assert settings.redis_url == "redis://custom:6379/1"
        assert settings.redis_max_connections == 50


class TestAPISettings:
    """API settings tests."""

    def test_custom_values(self) -> None:
        """Custom values can be set."""
        settings = APISettings(
            title="Custom API",
            debug=True,
        )

        assert settings.title == "Custom API"
        assert settings.debug is True


class TestSettingsSingletons:
    """Settings singleton tests."""

    def test_get_auth_settings_cached(self) -> None:
        """Auth settings are cached."""
        get_auth_settings.cache_clear()

        settings1 = get_auth_settings()
        settings2 = get_auth_settings()

        assert settings1 is settings2

    def test_get_cache_settings_cached(self) -> None:
        """Cache settings are cached."""
        get_cache_settings.cache_clear()

        settings1 = get_cache_settings()
        settings2 = get_cache_settings()

        assert settings1 is settings2

    def test_get_api_settings_cached(self) -> None:
        """API settings are cached."""
        get_api_settings.cache_clear()

        settings1 = get_api_settings()
        settings2 = get_api_settings()

        assert settings1 is settings2

    def test_get_agent_settings_cached(self) -> None:
        """Agent settings are cached."""
        get_agent_settings.cache_clear()

        settings1 = get_agent_settings()
        settings2 = get_agent_settings()

        assert settings1 is settings2

    def test_get_mcp_settings_cached(self) -> None:
        """MCP settings are cached."""
        get_mcp_settings.cache_clear()

        settings1 = get_mcp_settings()
        settings2 = get_mcp_settings()

        assert settings1 is settings2

    def test_get_langfuse_settings_cached(self) -> None:
        """Langfuse settings are cached."""
        get_langfuse_settings.cache_clear()

        settings1 = get_langfuse_settings()
        settings2 = get_langfuse_settings()

        assert settings1 is settings2


class TestAgentSettings:
    """Agent settings tests."""

    def test_default_values(self) -> None:
        """Default values are set correctly."""
        settings = AgentSettings()

        assert settings.conductor_temperature == 0.2
        assert settings.meta_prompter_temperature == 0.3
        assert settings.worker_temperature == 0.3
        assert settings.worker_max_tokens == 16000
        assert settings.qa_temperature == 0.1
        assert settings.summarizer_temperature == 0.2
        assert settings.max_milestone_retries == 3
        assert settings.max_tool_iterations == 10

    def test_custom_values(self) -> None:
        """Custom values can be set."""
        settings = AgentSettings(
            conductor_temperature=0.5,
            worker_max_tokens=32000,
            max_milestone_retries=5,
        )

        assert settings.conductor_temperature == 0.5
        assert settings.worker_max_tokens == 32000
        assert settings.max_milestone_retries == 5

    def test_temperature_bounds(self) -> None:
        """Temperature values are bounded correctly."""
        settings = AgentSettings(
            conductor_temperature=0.0,
            worker_temperature=2.0,
        )

        assert settings.conductor_temperature == 0.0
        assert settings.worker_temperature == 2.0


class TestMcpSettings:
    """MCP settings tests."""

    def test_default_values(self) -> None:
        """Default values are set correctly."""
        settings = McpSettings()

        assert settings.tool_calls_per_hour == 100
        assert settings.tool_execution_timeout == 30
        assert settings.max_tool_calls_per_request == 5
        assert settings.max_tool_output_size == 1024 * 1024
        assert "npx" in settings.allowed_stdio_commands
        assert "delete" in settings.high_risk_keywords
        assert "write" in settings.medium_risk_keywords

    def test_custom_values(self) -> None:
        """Custom values can be set."""
        settings = McpSettings(
            tool_calls_per_hour=200,
            tool_execution_timeout=60,
        )

        assert settings.tool_calls_per_hour == 200
        assert settings.tool_execution_timeout == 60

    def test_encryption_key_generation(self) -> None:
        """Encryption key is generated when not provided."""
        settings = McpSettings(encryption_key="")

        # Should generate a key
        key1 = settings.get_encryption_key()
        assert key1 is not None
        assert len(key1) > 0

        # Should return same generated key
        key2 = settings.get_encryption_key()
        assert key1 == key2

    def test_encryption_key_provided(self) -> None:
        """Provided encryption key is used."""
        custom_key = "custom-test-key-for-testing"
        settings = McpSettings(encryption_key=custom_key)

        assert settings.get_encryption_key() == custom_key

    def test_blocked_url_patterns(self) -> None:
        """Blocked URL patterns include common SSRF targets."""
        settings = McpSettings()

        patterns = settings.blocked_url_patterns
        assert any("localhost" in p for p in patterns)
        assert any("127.0.0.1" in p.replace("\\", "") for p in patterns)
        assert any("192.168" in p.replace("\\", "") for p in patterns)


class TestLangfuseSettings:
    """Langfuse settings tests."""

    def test_default_values(self, monkeypatch) -> None:
        """Default values are set correctly."""
        # Clear environment variables to test defaults
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)

        settings = LangfuseSettings(_env_file=None)

        assert settings.enabled is True
        assert settings.host == "https://cloud.langfuse.com"
        assert settings.public_key == ""
        assert settings.secret_key == ""
        assert settings.debug is False
        assert settings.flush_at == 5
        assert settings.flush_interval == 1.0
        assert settings.sample_rate == 1.0

    def test_custom_values(self) -> None:
        """Custom values can be set."""
        settings = LangfuseSettings(
            enabled=False,
            host="http://localhost:3000",
            public_key="pk-test-123",
            secret_key="sk-test-456",
            debug=True,
            flush_at=10,
            flush_interval=2.0,
            sample_rate=0.5,
        )

        assert settings.enabled is False
        assert settings.host == "http://localhost:3000"
        assert settings.public_key == "pk-test-123"
        assert settings.secret_key == "sk-test-456"
        assert settings.debug is True
        assert settings.flush_at == 10
        assert settings.flush_interval == 2.0
        assert settings.sample_rate == 0.5

    def test_sample_rate_bounds(self) -> None:
        """Sample rate is bounded between 0 and 1."""
        settings_min = LangfuseSettings(sample_rate=0.0, _env_file=None)
        settings_max = LangfuseSettings(sample_rate=1.0, _env_file=None)

        assert settings_min.sample_rate == 0.0
        assert settings_max.sample_rate == 1.0

    def test_flush_at_bounds(self) -> None:
        """Flush at is bounded correctly."""
        settings = LangfuseSettings(flush_at=1, _env_file=None)
        assert settings.flush_at == 1

        settings = LangfuseSettings(flush_at=100, _env_file=None)
        assert settings.flush_at == 100

    def test_flush_interval_bounds(self) -> None:
        """Flush interval is bounded correctly."""
        settings = LangfuseSettings(flush_interval=0.1, _env_file=None)
        assert settings.flush_interval == 0.1

        settings = LangfuseSettings(flush_interval=60.0, _env_file=None)
        assert settings.flush_interval == 60.0
