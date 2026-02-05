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
    """Agent types in the simplified 7-node workflow.

    Workflow: architect -> plan_review -> execute_worker -> verify_qa
        -> execution_breakpoint -> advance -> generate_response -> END
    """

    ARCHITECT = "architect"
    WORKER = "worker"
    QA = "qa"
    RESPONDER = "responder"


class SnapshotType(str, Enum):
    """Memory snapshot creation trigger."""

    AUTO = "auto"
    MANUAL = "manual"
    MILESTONE = "milestone"


class MemoryType(str, Enum):
    """Episodic memory type classification."""

    TASK_RESULT = "task_result"
    DECISION = "decision"
    LEARNING = "learning"
    ERROR = "error"
    USER_PREFERENCE = "user_preference"
    DOMAIN_KNOWLEDGE = "domain_knowledge"
