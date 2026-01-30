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
    response_format: dict[str, Any] | None = None


# =============================================================================
# Structured Output Schemas
# =============================================================================


class MilestoneSchema(BaseModel):
    """Schema for a single milestone in Conductor output."""

    model_config = {"extra": "forbid"}

    description: str = Field(..., description="Brief description of what needs to be done")
    complexity: Literal["TRIVIAL", "SIMPLE", "MODERATE", "COMPLEX", "CONTEXT_HEAVY"] = Field(
        ..., description="Task complexity level"
    )
    acceptance_criteria: str = Field(..., description="Criteria to validate completion")


class ConductorOutput(BaseModel):
    """Structured output schema for Conductor agent."""

    model_config = {"extra": "forbid"}

    milestones: list[MilestoneSchema] = Field(
        ..., description="List of milestones to complete the task"
    )


class QAOutput(BaseModel):
    """Structured output schema for QA agent validation."""

    model_config = {"extra": "forbid"}

    decision: Literal["PASS", "RETRY"] = Field(..., description="Validation decision")
    feedback: str = Field(..., description="Detailed explanation of decision")
    issues: list[str] = Field(..., description="Specific issues found (empty if PASS)")
    suggestions: list[str] = Field(..., description="Improvement suggestions (empty if PASS)")

    # Note: All fields must be required (no defaults) for OpenAI strict mode
    # which requires all properties to be in the 'required' array
    plan_viability: Literal["VIABLE", "NEEDS_REVISION", "BLOCKED"] = Field(
        ...,
        description="Assessment of whether current plan can achieve goal",
    )
    plan_viability_reason: str | None = Field(
        ...,
        description="Reason if plan needs revision or is blocked (null if VIABLE)",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in the assessment (0.0-1.0)",
    )


class FileArtifact(BaseModel):
    """Schema for a single file artifact."""

    model_config = {"extra": "forbid"}

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

    model_config = {"extra": "forbid"}

    explanation: str = Field(
        ..., description="Brief explanation of what was created (in user's language)"
    )
    files: list[FileArtifact] = Field(
        ..., description="List of generated file artifacts with paths and content"
    )
    deleted_files: list[str] = Field(
        ...,
        description="List of file paths to delete. Use empty array [] if no files to delete.",
    )


class WorkerReActOutput(BaseModel):
    """Extended worker output with ReAct observations for dynamic replanning."""

    model_config = {"extra": "forbid"}

    explanation: str = Field(
        ..., description="Brief explanation of what was created (in user's language)"
    )
    files: list[FileArtifact] = Field(
        ..., description="List of generated file artifacts with paths and content"
    )
    deleted_files: list[str] = Field(
        ...,
        description="List of file paths to delete. Use empty array [] if no files to delete.",
    )

    # ReAct observation fields
    observations: list[str] = Field(
        default_factory=list,
        description="Observations discovered during execution",
    )
    discovered_issues: list[str] = Field(
        default_factory=list,
        description="Issues that may affect future milestones",
    )
    suggested_plan_changes: list[str] = Field(
        default_factory=list,
        description="Suggested modifications to remaining milestones",
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


# =============================================================================
# ReAct Replanning Schemas
# =============================================================================


class MilestoneModification(BaseModel):
    """Schema for a single milestone modification during replanning."""

    model_config = {"extra": "forbid"}

    action: Literal["ADD", "MODIFY", "REMOVE", "REORDER"] = Field(
        ..., description="Type of modification"
    )
    target_index: int | None = Field(
        default=None,
        description="Index of milestone to modify/remove (None for ADD)",
    )
    new_milestone: MilestoneSchema | None = Field(
        default=None,
        description="New milestone data (for ADD/MODIFY)",
    )
    reason: str = Field(..., description="Reason for this modification")


class ConductorReplanOutput(BaseModel):
    """Structured output for Conductor replanning based on execution observations."""

    model_config = {"extra": "forbid"}

    analysis: str = Field(..., description="Analysis of current situation and why replan is needed")
    modifications: list[MilestoneModification] = Field(
        ..., description="List of plan modifications to apply"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in the revised plan (0.0-1.0)",
    )
    reasoning: str = Field(..., description="Reasoning for the plan changes")
