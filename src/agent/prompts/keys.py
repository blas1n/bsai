"""Prompt key enums for type-safe prompt management."""

from enum import StrEnum


class WorkerPrompts(StrEnum):
    """Prompt keys for Worker agent."""

    SYSTEM_PROMPT = "system_prompt"
    RETRY_PROMPT = "retry_prompt"


class QAAgentPrompts(StrEnum):
    """Prompt keys for QA Agent."""

    VALIDATION_PROMPT = "validation_prompt"


class ResponderPrompts(StrEnum):
    """Prompt keys for Responder agent."""

    SYSTEM_PROMPT = "system_prompt"
    GENERATE_RESPONSE = "generate_response"
    GENERATE_RESPONSE_WITH_SUMMARY = "generate_response_with_summary"
    FAILURE_REPORT_PROMPT = "failure_report_prompt"


class MemoryPrompts(StrEnum):
    """Prompt keys for Memory content templates."""

    TASK_RESULT_CONTENT = "task_result_content"
    QA_LEARNING_CONTENT = "qa_learning_content"
    ERROR_CONTENT = "error_content"
    CONTEXT_HEADER = "context_header"
    CONTEXT_MEMORY_ITEM = "context_memory_item"


class ArchitectPrompts(StrEnum):
    """Prompt keys for Architect agent."""

    PLANNING_PROMPT = "planning_prompt"
    REVISE_PROMPT = "revise_prompt"
    REPLAN_PROMPT = "replan_prompt"
