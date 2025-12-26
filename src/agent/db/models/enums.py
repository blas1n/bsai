"""Enums for database models."""

from enum import Enum


class SessionStatus(str, Enum):
    """Session lifecycle status."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class MilestoneStatus(str, Enum):
    """Milestone completion status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"


class TaskComplexity(str, Enum):
    """Task complexity levels for LLM selection."""

    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    CONTEXT_HEAVY = "context_heavy"


class AgentType(str, Enum):
    """Agent types in the system."""

    CONDUCTOR = "conductor"
    META_PROMPTER = "meta_prompter"
    WORKER = "worker"
    QA = "qa"
    SUMMARIZER = "summarizer"


class SnapshotType(str, Enum):
    """Memory snapshot creation trigger."""

    AUTO = "auto"
    MANUAL = "manual"
    MILESTONE = "milestone"
