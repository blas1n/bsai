"""LangGraph workflow module for multi-agent orchestration.

This module provides the LangGraph-based workflow that orchestrates
the 5 specialized agents (Conductor, MetaPrompter, Worker, QA, Summarizer)
for task execution with automatic LLM selection, quality validation,
and context management.

Exports:
    State:
        - AgentState: Workflow state TypedDict
        - MilestoneData: Milestone data structure

    Workflow:
        - build_workflow: Graph builder function
        - compile_workflow: Graph compiler function
        - WorkflowRunner: High-level runner class

    Container:
        - AgentContainer: Singleton DI container class
        - get_container: Container accessor function
        - reset_container: Container reset for testing

Example:
    >>> from agent.graph import WorkflowRunner
    >>> async with get_db_session() as session:
    ...     runner = WorkflowRunner(session)
    ...     await runner.initialize()
    ...     result = await runner.run(
    ...         session_id="...",
    ...         task_id="...",
    ...         original_request="Build a web scraper",
    ...     )
    ...     print(result["task_status"])
"""

from .state import AgentState, MilestoneData
from .workflow import WorkflowRunner, build_workflow, compile_workflow

__all__ = [
    # State
    "AgentState",
    "MilestoneData",
    # Workflow
    "build_workflow",
    "compile_workflow",
    "WorkflowRunner",
]
