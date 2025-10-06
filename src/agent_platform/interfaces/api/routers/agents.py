"""
Agent orchestration endpoints
"""

from typing import Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
import structlog

from agent_platform.core.orchestrator.orchestrator import AgentOrchestrator
from agent_platform.interfaces.api.dependencies.auth import get_current_user

logger = structlog.get_logger()

router = APIRouter()


class AgentRequest(BaseModel):
    """Agent execution request"""

    message: str = Field(..., description="User message/instruction")
    session_id: Optional[UUID] = Field(None, description="Session ID for context")
    model: Optional[str] = Field(None, description="Preferred LLM model")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="LLM temperature")
    max_tokens: Optional[int] = Field(None, description="Maximum tokens to generate")
    tools: Optional[list[str]] = Field(None, description="Enabled tools")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class AgentResponse(BaseModel):
    """Agent execution response"""

    request_id: UUID
    session_id: UUID
    message: str
    reasoning: Optional[str] = None
    tool_calls: Optional[list[dict]] = None
    metadata: dict


class AgentStreamEvent(BaseModel):
    """Server-sent event for streaming responses"""

    event_type: str  # "token", "tool_call", "reasoning", "done", "error"
    data: dict


@router.post("/execute", response_model=AgentResponse, status_code=status.HTTP_200_OK)
async def execute_agent(
    request: AgentRequest,
    current_user: dict = Depends(get_current_user),
) -> AgentResponse:
    """
    Execute agent with given request

    This endpoint orchestrates the full agent workflow:
    1. Planning: Decompose request into executable tasks
    2. Execution: Execute tasks using LLMs and tools
    3. Memory: Store context for future interactions
    """
    request_id = uuid4()
    session_id = request.session_id or uuid4()

    logger.info(
        "agent_request_received",
        request_id=str(request_id),
        session_id=str(session_id),
        user_id=current_user["user_id"],
        message_length=len(request.message),
    )

    try:
        # Get orchestrator instance
        orchestrator = AgentOrchestrator()

        # Execute agent
        result = await orchestrator.process_request(
            request_id=request_id,
            session_id=session_id,
            user_id=current_user["user_id"],
            message=request.message,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            tools=request.tools,
            metadata=request.metadata,
        )

        logger.info(
            "agent_request_completed",
            request_id=str(request_id),
            session_id=str(session_id),
        )

        return AgentResponse(
            request_id=request_id,
            session_id=session_id,
            message=result.message,
            reasoning=result.reasoning,
            tool_calls=result.tool_calls,
            metadata=result.metadata,
        )

    except Exception as e:
        logger.error(
            "agent_request_failed",
            request_id=str(request_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent execution failed: {str(e)}",
        )


@router.get("/sessions/{session_id}", status_code=status.HTTP_200_OK)
async def get_session_history(
    session_id: UUID,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Get conversation history for a session"""
    from agent_platform.core.memory.short_term import short_term_memory

    logger.info("fetching_session_history", session_id=str(session_id))

    try:
        messages = await short_term_memory.get_context(
            session_id=str(session_id), limit=limit
        )

        return {"session_id": session_id, "messages": messages, "count": len(messages)}

    except Exception as e:
        logger.error(
            "session_history_fetch_failed", session_id=str(session_id), error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch session history: {str(e)}",
        )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_session(
    session_id: UUID,
    current_user: dict = Depends(get_current_user),
) -> None:
    """Clear conversation history for a session"""
    from agent_platform.core.memory.short_term import short_term_memory

    logger.info("clearing_session", session_id=str(session_id))

    try:
        await short_term_memory.clear_session(session_id=str(session_id))
        logger.info("session_cleared", session_id=str(session_id))

    except Exception as e:
        logger.error("session_clear_failed", session_id=str(session_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear session: {str(e)}",
        )
