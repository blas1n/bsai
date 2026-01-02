"""LLM request/response schemas.

Type-safe Pydantic models for LLM interactions.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """Individual chat message."""

    role: Literal["system", "user", "assistant"]
    content: str


class LLMRequest(BaseModel):
    """LLM completion request."""

    model: str
    messages: list[ChatMessage]
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = None
    stream: bool = False
    api_base: str | None = None
    api_key: str | None = None
    response_format: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Structured Output Schemas
# =============================================================================


class MilestoneSchema(BaseModel):
    """Schema for a single milestone in Conductor output."""

    description: str = Field(..., description="Brief description of what needs to be done")
    complexity: Literal["TRIVIAL", "SIMPLE", "MODERATE", "COMPLEX", "CONTEXT_HEAVY"] = Field(
        ..., description="Task complexity level"
    )
    acceptance_criteria: str = Field(..., description="Criteria to validate completion")


class ConductorOutput(BaseModel):
    """Structured output schema for Conductor agent."""

    milestones: list[MilestoneSchema] = Field(
        ..., description="List of milestones to complete the task"
    )


class QAOutput(BaseModel):
    """Structured output schema for QA agent validation."""

    decision: Literal["PASS", "RETRY"] = Field(..., description="Validation decision")
    feedback: str = Field(..., description="Detailed explanation of decision")
    issues: list[str] | None = Field(default=None, description="Specific issues found (if RETRY)")
    suggestions: list[str] | None = Field(
        default=None, description="Improvement suggestions (if RETRY)"
    )


class FileArtifact(BaseModel):
    """Schema for a single file artifact."""

    path: str = Field(
        ...,
        description="File path including directory (e.g., 'src/app.js', 'docs/README.md')",
    )
    content: str = Field(..., description="Complete file content")
    kind: str = Field(
        ...,
        description="File type/extension (e.g., 'js', 'py', 'html', 'md', 'json', 'png')",
    )


class WorkerOutput(BaseModel):
    """Structured output schema for Worker agent."""

    explanation: str = Field(
        ..., description="Brief explanation of what was created (in user's language)"
    )
    files: list[FileArtifact] = Field(
        default_factory=list,
        description="List of generated file artifacts with paths and content",
    )


class UsageInfo(BaseModel):
    """Token usage information."""

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class LLMResponse(BaseModel):
    """LLM completion response."""

    content: str
    usage: UsageInfo
    model: str
    finish_reason: str | None = None
