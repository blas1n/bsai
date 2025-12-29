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

    def test_custom_values(self) -> None:
        """Custom values can be set."""
        settings = AuthSettings(
            keycloak_url="https://auth.example.com",
            keycloak_realm="test-realm",
            keycloak_client_id="test-client",
            keycloak_client_secret="secret123",
            callback_uri="https://example.com/callback",
            _env_file=None,
        )

        assert settings.keycloak_url == "https://auth.example.com"
        assert settings.keycloak_realm == "test-realm"
        assert settings.keycloak_client_id == "test-client"
        assert settings.keycloak_client_secret == "secret123"
        assert settings.callback_uri == "https://example.com/callback"


class TestCacheSettings:
    """Cache settings tests."""

    def test_custom_values(self) -> None:
        """Custom values can be set."""
        settings = CacheSettings(
            redis_url="redis://custom:6379/1",
            redis_max_connections=50,
            _env_file=None,
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
            _env_file=None,
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
