"""Configuration tests."""

from __future__ import annotations

from agent.api.config import (
    APISettings,
    AuthSettings,
    CacheSettings,
    get_api_settings,
    get_auth_settings,
    get_cache_settings,
)


class TestAuthSettings:
    """Auth settings tests."""

    def test_default_values(self) -> None:
        """Default values are set correctly."""
        settings = AuthSettings()

        assert settings.keycloak_url == "http://localhost:8080"
        assert settings.keycloak_realm == "bsai"
        assert settings.keycloak_client_id == "bsai-api"
        assert settings.keycloak_client_secret is None
        assert settings.keycloak_admin_secret is None
        assert settings.callback_uri == "http://localhost:8000/callback"

    def test_custom_values(self) -> None:
        """Custom values can be set."""
        settings = AuthSettings(
            keycloak_url="https://auth.example.com",
            keycloak_realm="test-realm",
            keycloak_client_id="test-client",
            keycloak_client_secret="secret123",
            callback_uri="https://example.com/callback",
        )

        assert settings.keycloak_url == "https://auth.example.com"
        assert settings.keycloak_realm == "test-realm"
        assert settings.keycloak_client_id == "test-client"
        assert settings.keycloak_client_secret == "secret123"
        assert settings.callback_uri == "https://example.com/callback"


class TestCacheSettings:
    """Cache settings tests."""

    def test_default_values(self) -> None:
        """Default values are set correctly."""
        settings = CacheSettings()

        assert settings.redis_url == "redis://localhost:6379/0"
        assert settings.redis_max_connections == 20
        assert settings.session_state_ttl == 3600
        assert settings.session_context_ttl == 1800


class TestAPISettings:
    """API settings tests."""

    def test_default_values(self) -> None:
        """Default values are set correctly."""
        settings = APISettings()

        assert settings.title == "BSAI API"
        assert settings.version == "1.0.0"
        assert settings.debug is False
        assert settings.api_prefix == "/api/v1"
        assert "http://localhost:3000" in settings.cors_origins

    def test_pagination_defaults(self) -> None:
        """Pagination defaults are set."""
        settings = APISettings()

        assert settings.default_page_size == 20
        assert settings.max_page_size == 100


class TestSettingsSingletons:
    """Settings singleton tests."""

    def test_get_auth_settings_cached(self) -> None:
        """Auth settings are cached."""
        # Clear cache first
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
