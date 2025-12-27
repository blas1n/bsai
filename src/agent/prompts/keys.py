"""Prompt key enums for type-safe prompt management."""

from enum import Enum


class ConductorPrompts(str, Enum):
    """Prompt keys for Conductor agent."""

    ANALYSIS_PROMPT = "analysis_prompt"


class MetaPrompterPrompts(str, Enum):
    """Prompt keys for Meta Prompter agent."""

    META_PROMPT = "meta_prompt"
    STRATEGIES = "strategies"


class WorkerPrompts(str, Enum):
    """Prompt keys for Worker agent."""

    RETRY_PROMPT = "retry_prompt"


class QAAgentPrompts(str, Enum):
    """Prompt keys for QA Agent."""

    VALIDATION_PROMPT = "validation_prompt"
    RETRY_CONTEXT_TEMPLATE = "retry_context_template"


class SummarizerPrompts(str, Enum):
    """Prompt keys for Summarizer agent."""

    SUMMARY_PROMPT = "summary_prompt"
    CHECKPOINT_PROMPT = "checkpoint_prompt"
