"""Custom exceptions for memory operations."""

from __future__ import annotations


class MemoryError(Exception):
    """Base exception for memory operations.

    Attributes:
        message: Error description
        cause: Original exception that caused this error
    """

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        """Initialize memory error.

        Args:
            message: Error description
            cause: Original exception that caused this error
        """
        super().__init__(message)
        self.cause = cause


class MemoryDatabaseError(MemoryError):
    """Database operation failed (non-recoverable).

    Raised when a database operation fails in a way that
    cannot be recovered from (e.g., connection failure,
    constraint violation).
    """

    pass


class MemoryEmbeddingError(MemoryError):
    """Embedding generation failed.

    Raised when the embedding service fails to generate
    embeddings for memory content.
    """

    pass


class MemoryValidationError(MemoryError):
    """Input validation failed.

    Raised when memory input data fails validation
    (e.g., invalid user_id, content too long).
    """

    pass
