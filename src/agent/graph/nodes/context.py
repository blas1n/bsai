"""Context management nodes (check and summarize)."""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core import SummarizerAgent
from agent.llm import ChatMessage

from ..broadcast import broadcast_agent_completed, broadcast_agent_started
from ..state import AgentState
from . import get_container, get_ws_manager

logger = structlog.get_logger()


async def check_context_node(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Check if context compression is needed.

    Evaluates current token usage against threshold
    to determine if Summarizer should run.

    Args:
        state: Current workflow state
        config: LangGraph config with container
        session: Database session

    Returns:
        Partial state with needs_compression flag
    """
    container = get_container(config)

    current_tokens = state.get("current_context_tokens", 0)
    max_tokens = state.get("max_context_tokens", 100000)

    # Use summarizer's threshold check (default 85%)
    summarizer = SummarizerAgent(
        llm_client=container.llm_client,
        router=container.router,
        prompt_manager=container.prompt_manager,
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
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Compress context via Summarizer agent.

    Reduces context size while preserving key information
    for session continuity.

    Args:
        state: Current workflow state
        config: LangGraph config with ws_manager
        session: Database session

    Returns:
        Partial state with compressed context
    """
    container = get_container(config)
    ws_manager = get_ws_manager(config)
    idx = state.get("current_milestone_index", 0)
    milestones = state.get("milestones", [])
    milestone_id = (
        milestones[idx]["id"] if milestones and idx < len(milestones) else state["task_id"]
    )

    # Broadcast summarizer started
    await broadcast_agent_started(
        ws_manager=ws_manager,
        session_id=state["session_id"],
        task_id=state["task_id"],
        milestone_id=milestone_id,
        sequence_number=idx + 1,
        agent="summarizer",
        message="Compressing context to preserve memory",
    )

    try:
        summarizer = SummarizerAgent(
            llm_client=container.llm_client,
            router=container.router,
            prompt_manager=container.prompt_manager,
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

        # Build summarizer details for broadcast
        summarizer_details = {
            "summary": summary,
            "summary_preview": summary[:300] + "..." if len(summary) > 300 else summary,
            "old_message_count": len(context_messages),
            "new_message_count": len(new_context),
            "tokens_saved_estimate": (len(context_messages) - len(new_context))
            * 100,  # Rough estimate
        }

        # Broadcast summarizer completed with details
        await broadcast_agent_completed(
            ws_manager=ws_manager,
            session_id=state["session_id"],
            task_id=state["task_id"],
            milestone_id=milestone_id,
            sequence_number=idx + 1,
            agent="summarizer",
            message=f"Context compressed ({len(context_messages)} → {len(new_context)} messages)",
            details=summarizer_details,
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
