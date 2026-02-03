"""LLM request/response schemas.

Type-safe Pydantic models for LLM interactions.
"""

from __future__ import annotations

from enum import Enum
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


# =============================================================================
# Project Plan Schemas
# =============================================================================


class StructureType(str, Enum):
    """Project plan structure type."""

    FLAT = "flat"
    GROUPED = "grouped"
    HIERARCHICAL = "hierarchical"


class PlanStatus(str, Enum):
    """Project plan status."""

    DRAFT = "draft"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"


class PauseLevel(str, Enum):
    """Breakpoint pause level."""

    NONE = "none"
    TASK = "task"
    FEATURE = "feature"
    EPIC = "epic"


class QAValidationType(str, Enum):
    """QA validation type."""

    STATIC = "static"
    LINT = "lint"
    TYPECHECK = "typecheck"
    TEST = "test"
    BUILD = "build"


# =============================================================================
# Hierarchy Models
# =============================================================================


class PlanTask(BaseModel):
    """Execution unit task."""

    model_config = {"extra": "forbid"}

    id: str = Field(..., description="Task ID (e.g., T1.1.1)")
    description: str
    complexity: Literal["TRIVIAL", "SIMPLE", "MODERATE", "COMPLEX", "CONTEXT_HEAVY"]
    acceptance_criteria: str
    dependencies: list[str] = Field(default_factory=list)
    parent_feature_id: str | None = None
    parent_epic_id: str | None = None


class Feature(BaseModel):
    """Feature (mid-level grouping)."""

    model_config = {"extra": "forbid"}

    id: str = Field(..., description="Feature ID (e.g., F1.1)")
    title: str
    description: str
    tasks: list[PlanTask] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class Epic(BaseModel):
    """Epic (top-level grouping)."""

    model_config = {"extra": "forbid"}

    id: str = Field(..., description="Epic ID (e.g., E1)")
    title: str
    description: str
    features: list[Feature] = Field(default_factory=list)


class ProjectPlanOutput(BaseModel):
    """Structured output for Architect agent."""

    model_config = {"extra": "forbid"}

    title: str
    overview: str
    tech_stack: list[str] = Field(default_factory=list)
    structure_type: Literal["flat", "grouped", "hierarchical"]
    epics: list[Epic] | None = None
    features: list[Feature] | None = None
    tasks: list[PlanTask] = Field(default_factory=list)


# =============================================================================
# Configuration Models
# =============================================================================


class BreakpointConfig(BaseModel):
    """Breakpoint configuration."""

    model_config = {"extra": "forbid"}

    pause_on_plan_review: bool = True
    pause_level: Literal["none", "task", "feature", "epic"] = "none"
    pause_on_task_ids: list[str] = Field(default_factory=list)
    pause_on_failure: bool = True


class QAConfig(BaseModel):
    """QA configuration."""

    model_config = {"extra": "forbid"}

    validations: list[Literal["static", "lint", "typecheck", "test", "build"]] = Field(
        default=["static"]
    )
    test_command: str | None = None
    lint_command: str | None = None
    typecheck_command: str | None = None
    build_command: str | None = None
    allow_lint_warnings: bool = True
    require_all_tests_pass: bool = True


# =============================================================================
# QA Result Models
# =============================================================================


class TestResult(BaseModel):
    """Test execution result."""

    model_config = {"extra": "forbid"}

    success: bool
    passed: int
    failed: int
    skipped: int
    total: int
    coverage: float | None = None
    failed_tests: list[str] = Field(default_factory=list)
    output: str


class LintResult(BaseModel):
    """Lint result."""

    model_config = {"extra": "forbid"}

    success: bool
    errors: int
    warnings: int
    issues: list[str] = Field(default_factory=list)
    output: str


class TypecheckResult(BaseModel):
    """Type check result."""

    model_config = {"extra": "forbid"}

    success: bool
    errors: int
    issues: list[str] = Field(default_factory=list)
    output: str


class BuildResult(BaseModel):
    """Build result."""

    model_config = {"extra": "forbid"}

    success: bool
    output: str
    error_message: str | None = None


class ExtendedQAOutput(BaseModel):
    """Extended QA output with dynamic validation."""

    model_config = {"extra": "forbid"}

    decision: Literal["PASS", "RETRY"]
    feedback: str
    issues: list[str]
    suggestions: list[str]
    confidence: float = Field(..., ge=0.0, le=1.0)

    # Dynamic validation results (optional)
    lint_result: LintResult | None = None
    typecheck_result: TypecheckResult | None = None
    test_result: TestResult | None = None
    build_result: BuildResult | None = None


# =============================================================================
# Architect Replanning Schemas
# =============================================================================


class PlanTaskModification(BaseModel):
    """Schema for a single task modification during Architect replanning."""

    model_config = {"extra": "forbid"}

    action: Literal["add", "update", "remove"] = Field(..., description="Type of modification")
    task_id: str = Field(..., description="Task ID to modify (existing) or new task ID (for add)")
    task: PlanTask | None = Field(
        default=None,
        description="Full task object for add/update, null for remove",
    )
    reason: str = Field(..., description="Reason for this modification")


class ArchitectReplanOutput(BaseModel):
    """Structured output for Architect replanning based on execution observations."""

    model_config = {"extra": "forbid"}

    analysis: str = Field(
        ..., description="Detailed analysis of what happened and why replanning is needed"
    )
    action: Literal["continue", "modify", "abort"] = Field(
        ..., description="Action to take: continue (no changes), modify (update plan), abort (stop)"
    )
    modifications: list[PlanTaskModification] | None = Field(
        default=None,
        description="List of task modifications to apply (empty for continue/abort)",
    )
    reasoning: str = Field(..., description="Overall reasoning for the decision")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in the revised plan (0.0-1.0)",
    )
