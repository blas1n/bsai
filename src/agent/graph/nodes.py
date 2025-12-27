"""LangGraph node functions for agent orchestration.

Each node:
1. Receives AgentState and database session
2. Calls appropriate agent method
3. Returns partial state update (immutable)
4. Handles errors gracefully

All nodes follow the pattern of returning partial state dicts
that LangGraph merges with the existing state.
"""

from enum import StrEnum
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.container import get_container
from agent.core import (
    ConductorAgent,
    MetaPrompterAgent,
    QAAgent,
    QADecision,
    SummarizerAgent,
    WorkerAgent,
)
from agent.db.models.enums import MilestoneStatus, TaskComplexity, TaskStatus
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.llm import ChatMessage

from .state import AgentState, MilestoneData

logger = structlog.get_logger()


class Node(StrEnum):
    """Workflow node names."""

    ANALYZE_TASK = "analyze_task"
    SELECT_LLM = "select_llm"
    GENERATE_PROMPT = "generate_prompt"
    EXECUTE_WORKER = "execute_worker"
    VERIFY_QA = "verify_qa"
    CHECK_CONTEXT = "check_context"
    SUMMARIZE = "summarize"
    ADVANCE = "advance"


async def analyze_task_node(
    state: AgentState,
    session: AsyncSession,
) -> dict[str, Any]:
    """Analyze task and create milestones via Conductor.

    This is the entry node that breaks down the user request
    into manageable milestones with complexity assessments.

    Args:
        state: Current workflow state
        session: Database session (per-request)

    Returns:
        Partial state with milestones list and initial status
    """
    container = get_container()

    try:
        conductor = ConductorAgent(
            llm_client=container.llm_client,
            router=container.router,
            session=session,
        )

        milestones_raw = await conductor.analyze_and_plan(
            task_id=state["task_id"],
            original_request=state["original_request"],
        )

        # Fetch persisted milestones from database to get actual IDs
        milestone_repo = MilestoneRepository(session)
        db_milestones = await milestone_repo.get_by_task_id(state["task_id"])

        # Convert to MilestoneData format with actual DB IDs
        milestones: list[MilestoneData] = []
        for i, m in enumerate(milestones_raw):
            # Get DB ID if available, otherwise use placeholder
            db_id = db_milestones[i].id if i < len(db_milestones) else UUID(int=i)

            # Ensure complexity is TaskComplexity
            complexity = m["complexity"]
            if not isinstance(complexity, TaskComplexity):
                complexity = TaskComplexity(complexity)

            milestones.append(
                MilestoneData(
                    id=db_id,
                    description=str(m["description"]),
                    complexity=complexity,
                    acceptance_criteria=str(m["acceptance_criteria"]),
                    status=MilestoneStatus.PENDING,
                    selected_model=None,
                    generated_prompt=None,
                    worker_output=None,
                    qa_feedback=None,
                    retry_count=0,
                )
            )

        logger.info(
            "analyze_task_complete",
            task_id=str(state["task_id"]),
            milestone_count=len(milestones),
        )

        return {
            "milestones": milestones,
            "current_milestone_index": 0,
            "task_status": TaskStatus.IN_PROGRESS,
            "retry_count": 0,
        }

    except Exception as e:
        logger.error(
            "analyze_task_failed",
            task_id=str(state["task_id"]),
            error=str(e),
        )
        return {
            "error": str(e),
            "error_node": "analyze_task",
            "task_status": TaskStatus.FAILED,
            "workflow_complete": True,
        }


async def select_llm_node(
    state: AgentState,
    session: AsyncSession,
) -> dict[str, Any]:
    """Select LLM for current milestone.

    Uses the Conductor's model selection logic based on
    milestone complexity and user preferences.

    Args:
        state: Current workflow state
        session: Database session

    Returns:
        Partial state with selected model in milestone
    """
    container = get_container()

    try:
        idx = state["current_milestone_index"]
        milestone = state["milestones"][idx]

        conductor = ConductorAgent(
            llm_client=container.llm_client,
            router=container.router,
            session=session,
        )

        model_name = await conductor.select_model_for_milestone(
            complexity=milestone["complexity"],
        )

        # Update milestone with selected model (immutable update)
        updated_milestones = list(state["milestones"])
        updated_milestone = dict(milestone)
        updated_milestone["selected_model"] = model_name
        updated_milestone["status"] = MilestoneStatus.IN_PROGRESS
        updated_milestones[idx] = MilestoneData(**updated_milestone)  # type: ignore[typeddict-item]

        logger.info(
            "llm_selected",
            milestone_index=idx,
            model=model_name,
            complexity=milestone["complexity"].name,
        )

        return {"milestones": updated_milestones}

    except Exception as e:
        logger.error("select_llm_failed", error=str(e))
        return {
            "error": str(e),
            "error_node": "select_llm",
        }


async def generate_prompt_node(
    state: AgentState,
    session: AsyncSession,
) -> dict[str, Any]:
    """Generate optimized prompt via MetaPrompter.

    Only called for MODERATE+ complexity tasks where
    prompt optimization provides significant value.

    Args:
        state: Current workflow state
        session: Database session

    Returns:
        Partial state with generated prompt
    """
    container = get_container()

    try:
        idx = state["current_milestone_index"]
        milestone = state["milestones"][idx]

        meta_prompter = MetaPrompterAgent(
            llm_client=container.llm_client,
            router=container.router,
            session=session,
        )

        # Build context string from recent messages
        context = None
        context_messages = state.get("context_messages", [])
        if context_messages:
            context_parts = [f"{m.role}: {m.content}" for m in context_messages[-5:]]
            context = "\n".join(context_parts)

        prompt = await meta_prompter.generate_prompt(
            milestone_id=milestone["id"],
            milestone_description=milestone["description"],
            milestone_complexity=milestone["complexity"],
            acceptance_criteria=milestone["acceptance_criteria"],
            context=context,
        )

        # Update milestone with prompt (immutable)
        updated_milestones = list(state["milestones"])
        updated_milestone = dict(milestone)
        updated_milestone["generated_prompt"] = prompt
        updated_milestones[idx] = MilestoneData(**updated_milestone)  # type: ignore[typeddict-item]

        logger.info(
            "prompt_generated",
            milestone_index=idx,
            prompt_length=len(prompt),
        )

        return {
            "milestones": updated_milestones,
            "current_prompt": prompt,
        }

    except Exception as e:
        logger.error("generate_prompt_failed", error=str(e))
        return {
            "error": str(e),
            "error_node": "generate_prompt",
        }


async def execute_worker_node(
    state: AgentState,
    session: AsyncSession,
) -> dict[str, Any]:
    """Execute milestone via Worker agent.

    Handles both fresh execution and retry scenarios,
    passing QA feedback for retries.

    Args:
        state: Current workflow state
        session: Database session

    Returns:
        Partial state with worker output and updated context
    """
    container = get_container()

    try:
        idx = state["current_milestone_index"]
        milestone = state["milestones"][idx]
        retry_count = state.get("retry_count", 0)

        worker = WorkerAgent(
            llm_client=container.llm_client,
            router=container.router,
            session=session,
        )

        # Determine prompt to use (MetaPrompter output or description)
        prompt = state.get("current_prompt") or milestone["description"]

        # Check if this is a retry with feedback
        previous_output = milestone.get("worker_output")
        qa_feedback = state.get("current_qa_feedback")
        if retry_count > 0 and previous_output and qa_feedback:
            response = await worker.retry_with_feedback(
                milestone_id=milestone["id"],
                original_prompt=prompt,
                previous_output=previous_output,
                qa_feedback=qa_feedback,
                complexity=milestone["complexity"],
            )
        else:
            response = await worker.execute_milestone(
                milestone_id=milestone["id"],
                prompt=prompt,
                complexity=milestone["complexity"],
                preferred_model=milestone.get("selected_model"),
                context_messages=state.get("context_messages"),
            )

        # Update milestone with output (immutable)
        updated_milestones = list(state["milestones"])
        updated_milestone = dict(milestone)
        updated_milestone["worker_output"] = response.content
        updated_milestones[idx] = MilestoneData(**updated_milestone)  # type: ignore[typeddict-item]

        # Update context with new exchange
        context_messages = list(state.get("context_messages", []))
        context_messages.append(ChatMessage(role="user", content=prompt))
        context_messages.append(ChatMessage(role="assistant", content=response.content))

        # Update token count
        current_tokens = state.get("current_context_tokens", 0)
        current_tokens += response.usage.total_tokens

        logger.info(
            "worker_executed",
            milestone_index=idx,
            output_length=len(response.content),
            tokens=response.usage.total_tokens,
            is_retry=retry_count > 0,
        )

        return {
            "milestones": updated_milestones,
            "current_output": response.content,
            "context_messages": context_messages,
            "current_context_tokens": current_tokens,
        }

    except Exception as e:
        logger.error("execute_worker_failed", error=str(e))
        return {
            "error": str(e),
            "error_node": "execute_worker",
        }


async def verify_qa_node(
    state: AgentState,
    session: AsyncSession,
) -> dict[str, Any]:
    """Validate worker output via QA agent.

    Performs independent validation of Worker output
    and provides structured feedback for improvements.

    Args:
        state: Current workflow state
        session: Database session

    Returns:
        Partial state with QA decision and feedback
    """
    container = get_container()

    try:
        idx = state["current_milestone_index"]
        milestone = state["milestones"][idx]
        retry_count = state.get("retry_count", 0)

        qa = QAAgent(
            llm_client=container.llm_client,
            router=container.router,
            session=session,
            max_retries=3,
        )

        decision, feedback = await qa.validate_output(
            milestone_id=milestone["id"],
            milestone_description=milestone["description"],
            acceptance_criteria=milestone["acceptance_criteria"],
            worker_output=milestone["worker_output"] or "",
            attempt_number=retry_count + 1,
        )

        # Update milestone with QA result (immutable)
        updated_milestones = list(state["milestones"])
        updated_milestone = dict(milestone)
        updated_milestone["qa_feedback"] = feedback

        if decision == QADecision.PASS:
            updated_milestone["status"] = MilestoneStatus.PASSED
        elif decision == QADecision.FAIL:
            updated_milestone["status"] = MilestoneStatus.FAILED
        # RETRY keeps IN_PROGRESS status

        updated_milestones[idx] = MilestoneData(**updated_milestone)  # type: ignore[typeddict-item]

        logger.info(
            "qa_verified",
            milestone_index=idx,
            decision=decision.value,
            retry_count=retry_count,
        )

        return {
            "milestones": updated_milestones,
            "current_qa_decision": decision.value,
            "current_qa_feedback": feedback,
        }

    except Exception as e:
        logger.error("verify_qa_failed", error=str(e))
        return {
            "error": str(e),
            "error_node": "verify_qa",
        }


async def check_context_node(
    state: AgentState,
    session: AsyncSession,
) -> dict[str, Any]:
    """Check if context compression is needed.

    Evaluates current token usage against threshold
    to determine if Summarizer should run.

    Args:
        state: Current workflow state
        session: Database session

    Returns:
        Partial state with needs_compression flag
    """
    container = get_container()

    current_tokens = state.get("current_context_tokens", 0)
    max_tokens = state.get("max_context_tokens", 100000)

    # Use summarizer's threshold check (default 85%)
    summarizer = SummarizerAgent(
        llm_client=container.llm_client,
        router=container.router,
        session=session,
    )

    needs_compression = summarizer.should_compress(current_tokens, max_tokens)

    logger.debug(
        "context_checked",
        current_tokens=current_tokens,
        max_tokens=max_tokens,
        needs_compression=needs_compression,
    )

    return {"needs_compression": needs_compression}


async def summarize_node(
    state: AgentState,
    session: AsyncSession,
) -> dict[str, Any]:
    """Compress context via Summarizer agent.

    Reduces context size while preserving key information
    for session continuity.

    Args:
        state: Current workflow state
        session: Database session

    Returns:
        Partial state with compressed context
    """
    container = get_container()

    try:
        summarizer = SummarizerAgent(
            llm_client=container.llm_client,
            router=container.router,
            session=session,
        )

        context_messages = state.get("context_messages", [])

        summary, remaining = await summarizer.compress_context(
            session_id=state["session_id"],
            task_id=state["task_id"],
            conversation_history=context_messages,
            current_context_size=state.get("current_context_tokens", 0),
            max_context_size=state.get("max_context_tokens", 100000),
        )

        # Build new context with summary as system message
        new_context: list[ChatMessage] = [
            ChatMessage(role="system", content=f"Previous context summary:\n{summary}")
        ]
        new_context.extend(remaining)

        # Estimate new token count (rough estimate: 4 chars per token)
        new_token_count = len(summary) // 4 + sum(len(m.content) // 4 for m in remaining)

        logger.info(
            "context_summarized",
            old_message_count=len(context_messages),
            new_message_count=len(new_context),
            summary_length=len(summary),
        )

        return {
            "context_messages": new_context,
            "context_summary": summary,
            "current_context_tokens": new_token_count,
            "needs_compression": False,
        }

    except Exception as e:
        logger.error("summarize_failed", error=str(e))
        return {
            "error": str(e),
            "error_node": "summarize",
        }


async def advance_node(
    state: AgentState,
    session: AsyncSession,  # noqa: ARG001 - Required for node signature
) -> dict[str, Any]:
    """Advance to next milestone or complete workflow.

    Handles three scenarios:
    1. Retry - Increment retry count, stay on milestone
    2. Fail - Mark task as failed, complete workflow
    3. Pass - Move to next milestone or complete

    Args:
        state: Current workflow state
        session: Database session (unused but required for signature)

    Returns:
        Partial state with updated index or completion flag
    """
    idx = state["current_milestone_index"]
    milestones = state["milestones"]
    qa_decision = state.get("current_qa_decision")

    if qa_decision == "retry":
        # Increment retry count, stay on same milestone
        new_retry = state.get("retry_count", 0) + 1

        logger.info(
            "milestone_retry",
            milestone_index=idx,
            retry_count=new_retry,
        )

        return {
            "retry_count": new_retry,
            "current_qa_decision": None,
            "current_qa_feedback": None,
            "should_continue": False,  # Signal to go back to worker
        }

    elif qa_decision == "fail":
        # Milestone failed, mark task as failed
        logger.warning(
            "milestone_failed",
            milestone_index=idx,
        )

        return {
            "task_status": TaskStatus.FAILED,
            "workflow_complete": True,
            "should_continue": False,
        }

    else:  # pass
        # Move to next milestone
        next_idx = idx + 1

        if next_idx >= len(milestones):
            # All milestones complete
            logger.info(
                "workflow_complete",
                task_id=str(state["task_id"]),
                milestone_count=len(milestones),
            )

            return {
                "task_status": TaskStatus.COMPLETED,
                "workflow_complete": True,
                "should_continue": False,
            }

        # Advance to next milestone
        logger.info(
            "milestone_advanced",
            from_index=idx,
            to_index=next_idx,
        )

        return {
            "current_milestone_index": next_idx,
            "retry_count": 0,
            "current_prompt": None,
            "current_output": None,
            "current_qa_decision": None,
            "current_qa_feedback": None,
            "should_continue": True,
        }
