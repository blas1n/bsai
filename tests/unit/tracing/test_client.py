"""Unit tests for the Langfuse tracing client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from agent.tracing.client import (
    LangfuseTracer,
    get_langfuse_callback,
    get_langfuse_tracer,
)


class TestLangfuseTracer:
    """Tests for the LangfuseTracer class."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock Langfuse settings."""
        with patch("agent.tracing.client.get_langfuse_settings") as mock:
            settings = MagicMock()
            settings.enabled = True
            settings.host = "http://langfuse:3000"  # Internal Docker network URL
            settings.public_key = "pk-test-key"
            settings.secret_key = "sk-test-key"
            settings.debug = False
            settings.flush_at = 5
            settings.flush_interval = 1.0
            settings.sample_rate = 1.0
            mock.return_value = settings
            yield settings

    @pytest.fixture
    def disabled_settings(self):
        """Create mock disabled Langfuse settings."""
        with patch("agent.tracing.client.get_langfuse_settings") as mock:
            settings = MagicMock()
            settings.enabled = False
            settings.host = "http://localhost:3000"
            settings.public_key = ""
            settings.secret_key = ""
            settings.debug = False
            settings.flush_at = 5
            settings.flush_interval = 1.0
            settings.sample_rate = 1.0
            mock.return_value = settings
            yield settings

    def test_tracer_init(self, mock_settings):
        """Test tracer initialization."""
        tracer = LangfuseTracer()
        assert tracer.settings == mock_settings
        assert tracer._client is None
        assert not tracer._initialized

    def test_tracer_enabled_with_keys(self, mock_settings):
        """Test tracer is enabled when properly configured."""
        tracer = LangfuseTracer()
        assert tracer.enabled is True

    def test_tracer_disabled_without_keys(self, disabled_settings):
        """Test tracer is disabled without API keys."""
        tracer = LangfuseTracer()
        assert tracer.enabled is False

    def test_tracer_disabled_when_setting_false(self, mock_settings):
        """Test tracer is disabled when enabled=False."""
        mock_settings.enabled = False
        tracer = LangfuseTracer()
        assert tracer.enabled is False

    def test_tracer_disabled_without_public_key(self, mock_settings):
        """Test tracer is disabled without public key."""
        mock_settings.public_key = ""
        tracer = LangfuseTracer()
        assert tracer.enabled is False

    def test_tracer_disabled_without_secret_key(self, mock_settings):
        """Test tracer is disabled without secret key."""
        mock_settings.secret_key = ""
        tracer = LangfuseTracer()
        assert tracer.enabled is False

    def test_should_sample_always_true(self, mock_settings):
        """Test sampling when sample_rate is 1.0."""
        tracer = LangfuseTracer()
        # With sample_rate=1.0, should always return True
        results = [tracer.should_sample() for _ in range(100)]
        assert all(results)

    def test_should_sample_always_false(self, mock_settings):
        """Test sampling when sample_rate is 0.0."""
        mock_settings.sample_rate = 0.0
        tracer = LangfuseTracer()
        # With sample_rate=0.0, should always return False
        results = [tracer.should_sample() for _ in range(100)]
        assert not any(results)

    def test_should_sample_partial(self, mock_settings):
        """Test sampling with partial rate."""
        mock_settings.sample_rate = 0.5
        tracer = LangfuseTracer()
        # With sample_rate=0.5, should get a mix
        results = [tracer.should_sample() for _ in range(1000)]
        true_count = sum(results)
        # Should be roughly 50% (allow 10% variance for randomness)
        assert 400 <= true_count <= 600

    def test_get_trace_url_enabled(self, mock_settings):
        """Test trace URL generation when enabled."""
        tracer = LangfuseTracer()
        task_id = uuid4()
        url = tracer.get_trace_url(task_id)
        assert url is not None
        assert str(task_id) in url
        assert mock_settings.host in url

    def test_get_trace_url_disabled(self, disabled_settings):
        """Test trace URL is empty string when disabled."""
        tracer = LangfuseTracer()
        task_id = uuid4()
        url = tracer.get_trace_url(task_id)
        assert url == ""

    def test_get_trace_url_with_string_id(self, mock_settings):
        """Test trace URL with string task ID."""
        tracer = LangfuseTracer()
        task_id = str(uuid4())
        url = tracer.get_trace_url(task_id)
        assert url is not None
        assert task_id in url

    def test_client_lazy_initialization(self, mock_settings):
        """Test client is lazily initialized."""
        tracer = LangfuseTracer()
        assert tracer._client is None
        assert not tracer._initialized

    def test_client_returns_none_when_disabled(self, disabled_settings):
        """Test client property returns None when disabled."""
        tracer = LangfuseTracer()
        assert tracer.client is None

    def test_client_initialization(self, mock_settings):
        """Test client is properly initialized on first access."""
        mock_client = MagicMock()

        with patch(
            "agent.tracing.client.Langfuse", return_value=mock_client
        ) as mock_langfuse_class:
            tracer = LangfuseTracer()
            client = tracer.client

            assert client == mock_client
            assert tracer._initialized
            mock_langfuse_class.assert_called_once_with(
                public_key=mock_settings.public_key,
                secret_key=mock_settings.secret_key,
                host=mock_settings.host,
                debug=mock_settings.debug,
                flush_at=mock_settings.flush_at,
                flush_interval=mock_settings.flush_interval,
            )

    def test_client_initialization_failure(self, mock_settings):
        """Test graceful handling of client initialization failure."""
        with patch("agent.tracing.client.Langfuse", side_effect=Exception("Connection failed")):
            tracer = LangfuseTracer()
            client = tracer.client

            assert client is None
            assert tracer._initialized  # Still marked as initialized to prevent retries

    def test_create_callback_handler_disabled(self, disabled_settings):
        """Test callback handler is None when disabled."""
        tracer = LangfuseTracer()
        handler = tracer.create_callback_handler()
        assert handler is None

    def test_create_callback_handler_with_params(self, mock_settings):
        """Test callback handler creation with parameters."""
        mock_handler = MagicMock()

        with patch(
            "agent.tracing.client.CallbackHandler", return_value=mock_handler
        ) as mock_callback_class:
            tracer = LangfuseTracer()
            session_id = uuid4()
            task_id = uuid4()
            user_id = "test-user"
            trace_name = "test-trace"
            metadata = {"key": "value"}
            tags = ["tag1", "tag2"]

            handler = tracer.create_callback_handler(
                session_id=session_id,
                task_id=task_id,
                user_id=user_id,
                trace_name=trace_name,
                metadata=metadata,
                tags=tags,
            )

            assert handler == mock_handler
            # In Langfuse v3, CallbackHandler only takes public_key
            mock_callback_class.assert_called_once_with(
                public_key=mock_settings.public_key,
            )
            # Metadata is stored for later use in invoke config
            invoke_metadata = tracer.get_invoke_config_metadata()
            assert invoke_metadata["langfuse_session_id"] == str(session_id)
            assert invoke_metadata["langfuse_user_id"] == user_id
            assert invoke_metadata["langfuse_tags"] == tags

    def test_create_callback_handler_not_sampled(self, mock_settings):
        """Test callback handler is None when not sampled."""
        mock_settings.sample_rate = 0.0

        with patch("agent.tracing.client.CallbackHandler") as mock_callback_class:
            tracer = LangfuseTracer()
            handler = tracer.create_callback_handler()
            assert handler is None
            mock_callback_class.assert_not_called()

    def test_create_trace(self, mock_settings):
        """Test trace creation."""
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_client.trace.return_value = mock_trace

        with patch("agent.tracing.client.Langfuse", return_value=mock_client):
            tracer = LangfuseTracer()
            session_id = uuid4()
            task_id = uuid4()

            trace = tracer.create_trace(
                name="test-trace",
                session_id=session_id,
                task_id=task_id,
                user_id="test-user",
                metadata={"key": "value"},
                tags=["tag1"],
            )

            assert trace == mock_trace
            mock_client.trace.assert_called_once()

    def test_create_trace_disabled(self, disabled_settings):
        """Test trace creation returns None when disabled."""
        tracer = LangfuseTracer()
        trace = tracer.create_trace("test")
        assert trace is None

    def test_flush(self, mock_settings):
        """Test flush method."""
        mock_client = MagicMock()

        with patch("agent.tracing.client.Langfuse", return_value=mock_client):
            tracer = LangfuseTracer()
            _ = tracer.client  # Initialize client
            tracer.flush()

            mock_client.flush.assert_called_once()

    def test_shutdown(self, mock_settings):
        """Test shutdown method."""
        mock_client = MagicMock()

        with patch("agent.tracing.client.Langfuse", return_value=mock_client):
            tracer = LangfuseTracer()
            _ = tracer.client  # Initialize client
            tracer.shutdown()

            mock_client.shutdown.assert_called_once()
            assert tracer._client is None
            assert not tracer._initialized


class TestGetLangfuseTracer:
    """Tests for the get_langfuse_tracer function."""

    def test_returns_singleton(self):
        """Test that get_langfuse_tracer returns the same instance."""
        # Clear cache for test
        get_langfuse_tracer.cache_clear()

        tracer1 = get_langfuse_tracer()
        tracer2 = get_langfuse_tracer()

        assert tracer1 is tracer2


class TestGetLangfuseCallback:
    """Tests for the get_langfuse_callback function."""

    @pytest.fixture
    def mock_tracer(self):
        """Create mock tracer."""
        with patch("agent.tracing.client.get_langfuse_tracer") as mock:
            tracer = MagicMock()
            mock.return_value = tracer
            yield tracer

    def test_delegates_to_tracer(self, mock_tracer):
        """Test that get_langfuse_callback delegates to tracer."""
        session_id = uuid4()
        task_id = uuid4()
        user_id = "test-user"

        get_langfuse_callback(
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
        )

        mock_tracer.create_callback_handler.assert_called_once_with(
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            trace_name=None,
            metadata=None,
            tags=None,
        )
