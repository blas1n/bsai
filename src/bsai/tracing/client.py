"""Langfuse tracing client for LLM observability.

Provides a centralized tracing client that integrates with LangGraph
workflows for debugging, cost tracking, and quality evaluation.
"""

from __future__ import annotations

import random
from functools import lru_cache
from typing import Any, cast
from uuid import UUID

import structlog
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from bsai.api.config import get_langfuse_settings

logger = structlog.get_logger()


class LangfuseTracer:
    """Langfuse tracing client wrapper.

    Provides a unified interface for creating traces and spans,
    with automatic configuration from environment variables.

    Attributes:
        enabled: Whether tracing is enabled
        client: The underlying Langfuse client (None if disabled)
        settings: Langfuse configuration settings
    """

    def __init__(self) -> None:
        """Initialize the Langfuse tracer.

        Reads configuration from environment variables via LangfuseSettings.
        If public_key or secret_key are not set, tracing is disabled.
        """
        self.settings = get_langfuse_settings()
        self._client: Langfuse | None = None
        self._initialized = False

    @property
    def enabled(self) -> bool:
        """Check if tracing is enabled and properly configured."""
        return (
            self.settings.enabled
            and bool(self.settings.public_key)
            and bool(self.settings.secret_key)
        )

    @property
    def client(self) -> Langfuse | None:
        """Get the Langfuse client, initializing lazily if needed."""
        if not self.enabled:
            return None

        if not self._initialized:
            self._initialize_client()

        return self._client

    def _initialize_client(self) -> None:
        """Initialize the Langfuse client with settings."""
        if self._initialized:
            return

        try:
            self._client = Langfuse(
                public_key=self.settings.public_key,
                secret_key=self.settings.secret_key,
                host=self.settings.host,
                debug=self.settings.debug,
                flush_at=self.settings.flush_at,
                flush_interval=self.settings.flush_interval,
            )
            self._initialized = True
            logger.info(
                "langfuse_client_initialized",
                host=self.settings.host,
                debug=self.settings.debug,
            )
        except Exception as e:
            logger.warning(
                "langfuse_client_initialization_failed",
                error=str(e),
            )
            self._client = None
            self._initialized = True

    def should_sample(self) -> bool:
        """Check if this request should be sampled based on sample_rate."""
        return random.random() < self.settings.sample_rate

    def create_callback_handler(
        self,
        session_id: str | UUID | None = None,
        task_id: str | UUID | None = None,
        user_id: str | None = None,
        trace_name: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> CallbackHandler | None:
        """Create a Langfuse callback handler for LangGraph integration.

        Args:
            session_id: Session UUID for grouping traces
            task_id: Task UUID as the trace ID
            user_id: User ID for attribution
            trace_name: Optional name for the trace
            metadata: Additional metadata to attach
            tags: Tags for filtering in Langfuse UI

        Returns:
            CallbackHandler if tracing is enabled, None otherwise
        """
        if not self.enabled or not self.should_sample():
            return None

        try:
            # Convert UUIDs to strings
            session_id_str = str(session_id) if session_id else None
            task_id_str = str(task_id) if task_id else None

            # Build langfuse metadata for v3 SDK
            # In v3, trace attributes are passed via config metadata with langfuse_ prefix
            langfuse_metadata: dict[str, Any] = {}
            if session_id_str:
                langfuse_metadata["langfuse_session_id"] = session_id_str
            if user_id:
                langfuse_metadata["langfuse_user_id"] = user_id
            if tags:
                langfuse_metadata["langfuse_tags"] = tags

            # Store additional context for retrieval during invoke
            self._pending_handler_metadata = {
                "trace_name": trace_name or f"task-{task_id_str or 'unknown'}",
                "task_id": task_id_str,
                "metadata": metadata or {},
                "langfuse_metadata": langfuse_metadata,
            }

            # In Langfuse v3, CallbackHandler only takes public_key
            # Authentication is handled via environment variables
            handler = CallbackHandler(
                public_key=self.settings.public_key,
            )

            logger.debug(
                "langfuse_callback_created",
                session_id=session_id_str,
                task_id=task_id_str,
                trace_name=trace_name,
            )

            return handler

        except Exception as e:
            logger.warning(
                "langfuse_callback_creation_failed",
                error=str(e),
                session_id=str(session_id) if session_id else None,
            )
            return None

    def get_invoke_config_metadata(self) -> dict[str, Any]:
        """Get metadata to pass to LangGraph invoke config.

        In Langfuse v3, trace attributes are passed via config metadata.
        Call this after create_callback_handler to get the metadata dict.

        Returns:
            Metadata dict with langfuse_ prefixed keys
        """
        if hasattr(self, "_pending_handler_metadata"):
            metadata = self._pending_handler_metadata.get("langfuse_metadata")
            if isinstance(metadata, dict):
                return metadata
        return {}

    def create_trace(
        self,
        name: str,
        session_id: str | UUID | None = None,
        task_id: str | UUID | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> Any | None:
        """Create a new trace directly via the Langfuse client.

        Use this for custom tracing outside of LangGraph workflows.

        Args:
            name: Name for the trace
            session_id: Session UUID for grouping
            task_id: Task UUID as trace ID
            user_id: User ID for attribution
            metadata: Additional metadata
            tags: Tags for filtering

        Returns:
            Span object if tracing is enabled, None otherwise
        """
        if not self.client or not self.should_sample():
            return None

        try:
            trace_metadata = metadata or {}
            if session_id:
                trace_metadata["session_id"] = str(session_id)
            if user_id:
                trace_metadata["user_id"] = user_id
            if tags:
                trace_metadata["tags"] = tags
            if task_id:
                trace_metadata["task_id"] = str(task_id)

            # Langfuse v3 uses start_span instead of trace
            # Cast to Any to satisfy type checker - the dict structure matches TraceContext
            trace_context = cast(Any, {"trace_id": str(task_id)}) if task_id else None
            span = self.client.start_span(
                name=name,
                metadata=trace_metadata,
                trace_context=trace_context,
            )

            logger.debug(
                "langfuse_trace_created",
                name=name,
                trace_id=str(task_id) if task_id else None,
            )

            return span

        except Exception as e:
            logger.warning(
                "langfuse_trace_creation_failed",
                error=str(e),
                name=name,
            )
            return None

    def flush(self) -> None:
        """Flush any pending events to Langfuse."""
        if self._client:
            try:
                self._client.flush()
                logger.debug("langfuse_flushed")
            except Exception as e:
                logger.warning("langfuse_flush_failed", error=str(e))

    def shutdown(self) -> None:
        """Shutdown the Langfuse client, flushing any pending events."""
        if self._client:
            try:
                self._client.shutdown()
                logger.info("langfuse_shutdown")
            except Exception as e:
                logger.warning("langfuse_shutdown_failed", error=str(e))
            finally:
                self._client = None
                self._initialized = False

    def get_trace_url(self, task_id: str | UUID) -> str:
        """Get the URL to view a trace in Langfuse UI.

        Args:
            task_id: The task/trace ID

        Returns:
            URL string if tracing is enabled, empty string otherwise
        """
        if not self.enabled:
            return ""

        return f"{self.settings.host}/trace/{task_id}"


# Global singleton instance
_tracer: LangfuseTracer | None = None


@lru_cache(maxsize=1)
def get_langfuse_tracer() -> LangfuseTracer:
    """Get the global Langfuse tracer instance.

    Returns:
        Singleton LangfuseTracer instance
    """
    global _tracer
    if _tracer is None:
        _tracer = LangfuseTracer()
    return _tracer


def get_langfuse_callback(
    session_id: str | UUID | None = None,
    task_id: str | UUID | None = None,
    user_id: str | None = None,
    trace_name: str | None = None,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> CallbackHandler | None:
    """Convenience function to get a Langfuse callback handler.

    Args:
        session_id: Session UUID for grouping traces
        task_id: Task UUID as the trace ID
        user_id: User ID for attribution
        trace_name: Optional name for the trace
        metadata: Additional metadata to attach
        tags: Tags for filtering in Langfuse UI

    Returns:
        CallbackHandler if tracing is enabled, None otherwise
    """
    tracer = get_langfuse_tracer()
    return tracer.create_callback_handler(
        session_id=session_id,
        task_id=task_id,
        user_id=user_id,
        trace_name=trace_name,
        metadata=metadata,
        tags=tags,
    )
