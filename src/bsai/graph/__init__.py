"""LangGraph workflow module for multi-agent orchestration.

This module provides the LangGraph-based workflow that orchestrates
the specialized agents (Architect, Worker, QA, Responder) for task
execution with project planning, quality validation, and context management.

Simplified 7-node workflow:
    architect -> plan_review -> execute_worker -> verify_qa
        -> execution_breakpoint -> advance -> generate_response -> END

Exports:
    State:
        - AgentState: Workflow state TypedDict

    Workflow:
        - build_workflow: Graph builder function
        - compile_workflow: Graph compiler function
        - WorkflowRunner: High-level runner class

    Container:
        - AgentContainer: Singleton DI container class
        - get_container: Container accessor function
        - reset_container: Container reset for testing

Example:
    >>> from bsai.graph import WorkflowRunner
    >>> async with get_db_session() as session:
    ...     runner = WorkflowRunner(
    ...         session, ws_manager, cache, event_bus, breakpoint_service
    ...     )
    ...     result = await runner.run(
    ...         session_id="...",
    ...         task_id="...",
    ...         original_request="Build a web scraper",
    ...     )
    ...     print(result["task_status"])
"""

from .state import AgentState
from .workflow import WorkflowRunner, build_workflow, compile_workflow

__all__ = [
    # State
    "AgentState",
    # Workflow
    "build_workflow",
    "compile_workflow",
    "WorkflowRunner",
]
