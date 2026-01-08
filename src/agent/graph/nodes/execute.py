"""Worker execution node."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core import WorkerAgent
from agent.core.artifact_extractor import extract_artifacts
from agent.db.repository.artifact_repo import ArtifactRepository
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.llm import ChatMessage

from ..broadcast import broadcast_agent_completed, broadcast_agent_started
from ..state import AgentState, MilestoneData
from . import get_container, get_ws_manager

logger = structlog.get_logger()


async def execute_worker_node(
    state: AgentState,
    config: RunnableConfig,
    session: AsyncSession,
) -> dict[str, Any]:
    """Execute milestone via Worker agent.

    Handles both fresh execution and retry scenarios,
    passing QA feedback for retries.

    Args:
        state: Current workflow state
        config: LangGraph config with ws_manager
        session: Database session

    Returns:
        Partial state with worker output and updated context
    """
    container = get_container(config)
    ws_manager = get_ws_manager(config)

    try:
        milestones = state.get("milestones")
        idx = state.get("current_milestone_index")

        if milestones is None or idx is None:
            return {"error": "No milestones available", "error_node": "execute_worker"}

        milestone = milestones[idx]
        retry_count = state.get("retry_count", 0)

        # Broadcast worker started
        message = (
            "Executing task" if retry_count == 0 else f"Retrying task (attempt {retry_count + 1})"
        )
        await broadcast_agent_started(
            ws_manager=ws_manager,
            session_id=state["session_id"],
            task_id=state["task_id"],
            milestone_id=milestone["id"],
            sequence_number=idx + 1,
            agent="worker",
            message=message,
        )

        worker = WorkerAgent(
            llm_client=container.llm_client,
            router=container.router,
            prompt_manager=container.prompt_manager,
            session=session,
            ws_manager=ws_manager,
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
                user_id=state["user_id"],
                session_id=state["session_id"],
            )
        else:
            response = await worker.execute_milestone(
                milestone_id=milestone["id"],
                prompt=prompt,
                complexity=milestone["complexity"],
                user_id=state["user_id"],
                session_id=state["session_id"],
                preferred_model=milestone.get("selected_model"),
                context_messages=state.get("context_messages"),
            )

        # Update milestone with output (immutable)
        updated_milestones = list(milestones)
        updated_milestone = dict(milestone)
        updated_milestone["worker_output"] = response.content
        updated_milestones[idx] = cast(MilestoneData, updated_milestone)

        # Update context with new exchange
        context_messages = list(state.get("context_messages", []))
        context_messages.append(ChatMessage(role="user", content=prompt))
        context_messages.append(ChatMessage(role="assistant", content=response.content))

        # Update token count
        current_tokens = state.get("current_context_tokens", 0)
        current_tokens += response.usage.total_tokens

        # Update total tokens and cost
        total_input = state.get("total_input_tokens", 0) + response.usage.input_tokens
        total_output = state.get("total_output_tokens", 0) + response.usage.output_tokens

        # Calculate cost for this call
        model = container.router.select_model(
            complexity=milestone["complexity"],
            preferred_model=milestone.get("selected_model"),
        )
        call_cost = container.router.calculate_cost(
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        current_cost = Decimal(state.get("total_cost_usd", "0"))
        total_cost = current_cost + call_cost

        logger.info(
            "worker_executed",
            milestone_index=idx,
            output_length=len(response.content),
            tokens=response.usage.total_tokens,
            cost_usd=float(call_cost),
            is_retry=retry_count > 0,
        )

        # Update milestone in DB with token/cost and selected model
        milestone_repo = MilestoneRepository(session)
        await milestone_repo.update_llm_usage(
            milestone_id=milestone["id"],
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost=call_cost,
        )
        # Also update selected_llm and worker_output in DB
        await milestone_repo.update(
            milestone["id"],
            selected_llm=model.name,
            worker_output=response.content,
        )

        # Extract and save artifacts from worker output
        extracted_artifacts = extract_artifacts(response.content)
        saved_artifacts = []

        if extracted_artifacts:
            artifact_repo = ArtifactRepository(session)
            for artifact in extracted_artifacts:
                saved = await artifact_repo.create_artifact(
                    task_id=state["task_id"],
                    milestone_id=milestone["id"],
                    artifact_type=artifact.artifact_type,
                    filename=artifact.filename,
                    kind=artifact.kind,
                    content=artifact.content,
                    path=artifact.path,
                    sequence_number=artifact.sequence_number,
                )
                saved_artifacts.append(
                    {
                        "id": str(saved.id),
                        "type": saved.artifact_type,
                        "filename": saved.filename,
                        "kind": saved.kind,
                        "content": saved.content,
                        "path": saved.path,
                    }
                )

            logger.info(
                "artifacts_extracted",
                milestone_id=str(milestone["id"]),
                count=len(saved_artifacts),
            )

        # Build worker output details for broadcast
        output_preview = (
            response.content[:500] + "..." if len(response.content) > 500 else response.content
        )
        worker_details = {
            "output": response.content,
            "output_preview": output_preview,
            "output_length": len(response.content),
            "tokens_used": response.usage.total_tokens,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "model": model.name,  # Only pass model name string, not entire LLMModel object
            "cost_usd": float(call_cost),
            "is_retry": retry_count > 0,
            "artifacts": saved_artifacts,  # Include artifacts in broadcast
        }

        # Broadcast worker completed with output details
        await broadcast_agent_completed(
            ws_manager=ws_manager,
            session_id=state["session_id"],
            task_id=state["task_id"],
            milestone_id=milestone["id"],
            sequence_number=idx + 1,
            agent="worker",
            message=f"Task executed ({response.usage.total_tokens} tokens)",
            details=worker_details,
        )

        return {
            "milestones": updated_milestones,
            "current_output": response.content,
            "context_messages": context_messages,
            "current_context_tokens": current_tokens,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cost_usd": str(total_cost),
        }

    except Exception as e:
        logger.error("execute_worker_failed", error=str(e))
        return {
            "error": str(e),
            "error_node": "execute_worker",
        }
