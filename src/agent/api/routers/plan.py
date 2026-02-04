"""Plan API Router.

Provides endpoints for Human-in-the-Loop plan review:
- GET plan details
- Approve plan
- Request revision
- Reject plan
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from agent.services.plan_service import (
    InvalidPlanStateError,
    PlanNotFoundError,
    PlanService,
)

from ..dependencies import DBSession

router = APIRouter(prefix="/sessions/{session_id}/tasks/{task_id}/plan", tags=["plan"])
logger = structlog.get_logger()


# Request/Response Models


class PlanResponse(BaseModel):
    """Plan details response."""

    id: UUID
    task_id: UUID
    session_id: UUID
    title: str
    overview: str | None
    tech_stack: list[str]
    structure_type: str
    plan_data: dict[str, Any]
    status: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    approved_at: str | None = None
    approved_by: str | None = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class ApproveRequest(BaseModel):
    """Plan approval request."""

    approved_by: str | None = Field(None, description="Who approved the plan")


class ReviseRequest(BaseModel):
    """Plan revision request."""

    feedback: str = Field(..., min_length=1, description="Revision feedback")


class RejectRequest(BaseModel):
    """Plan rejection request."""

    reason: str | None = Field(None, description="Rejection reason")


class ActionResponse(BaseModel):
    """Generic action response."""

    success: bool
    message: str
    plan: PlanResponse


# Endpoints


@router.get(
    "",
    response_model=PlanResponse,
    summary="Get plan details",
)
async def get_plan(
    session_id: UUID,
    task_id: UUID,
    db: DBSession,
) -> PlanResponse:
    """Get plan details for a task.

    Args:
        session_id: Session UUID
        task_id: Task UUID
        db: Database session

    Returns:
        Plan details

    Raises:
        HTTPException: If plan not found (404)
    """
    service = PlanService(db)

    try:
        plan = await service.get_plan_by_task(task_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan not found for task {task_id}",
            )

        logger.info(
            "plan_retrieved",
            session_id=str(session_id),
            task_id=str(task_id),
            plan_id=str(plan.id),
        )
        return PlanResponse.model_validate(plan)
    except PlanNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.post(
    "/approve",
    response_model=ActionResponse,
    summary="Approve plan for execution",
)
async def approve_plan(
    session_id: UUID,
    task_id: UUID,
    request: ApproveRequest,
    db: DBSession,
) -> ActionResponse:
    """Approve a plan for execution.

    Transitions plan from DRAFT to APPROVED status.

    Args:
        session_id: Session UUID
        task_id: Task UUID
        request: Approval request with optional approver
        db: Database session

    Returns:
        Action response with updated plan

    Raises:
        HTTPException: If plan not found (404) or invalid state (400)
    """
    service = PlanService(db)

    try:
        plan = await service.get_plan_by_task(task_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan not found for task {task_id}",
            )

        updated_plan = await service.approve_plan(
            plan_id=plan.id,
            approved_by=request.approved_by,
        )

        logger.info(
            "plan_approved_via_api",
            session_id=str(session_id),
            task_id=str(task_id),
            plan_id=str(plan.id),
            approved_by=request.approved_by,
        )

        return ActionResponse(
            success=True,
            message="Plan approved successfully",
            plan=PlanResponse.model_validate(updated_plan),
        )
    except PlanNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except InvalidPlanStateError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post(
    "/revise",
    response_model=ActionResponse,
    summary="Request plan revision",
)
async def revise_plan(
    session_id: UUID,
    task_id: UUID,
    request: ReviseRequest,
    db: DBSession,
) -> ActionResponse:
    """Request plan revision with feedback.

    Uses the Architect agent to revise the plan based on
    user feedback while maintaining the plan in DRAFT status.

    Note: Architect agent injection needed for full functionality.

    Args:
        session_id: Session UUID
        task_id: Task UUID
        request: Revision request with feedback
        db: Database session

    Returns:
        Action response with revised plan

    Raises:
        HTTPException: If plan not found (404), invalid state (400),
            or Architect not configured (501)
    """
    service = PlanService(db)

    try:
        plan = await service.get_plan_by_task(task_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan not found for task {task_id}",
            )

        logger.info(
            "plan_revision_requested_via_api",
            session_id=str(session_id),
            task_id=str(task_id),
            plan_id=str(plan.id),
            feedback_length=len(request.feedback),
        )

        revised_plan = await service.request_revision(
            plan_id=plan.id,
            feedback=request.feedback,
        )

        return ActionResponse(
            success=True,
            message="Plan revised successfully",
            plan=PlanResponse.model_validate(revised_plan),
        )
    except PlanNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except InvalidPlanStateError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except RuntimeError as e:
        # Architect not configured
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(e),
        ) from e


@router.post(
    "/reject",
    response_model=ActionResponse,
    summary="Reject plan",
)
async def reject_plan(
    session_id: UUID,
    task_id: UUID,
    request: RejectRequest,
    db: DBSession,
) -> ActionResponse:
    """Reject a plan.

    Transitions plan from DRAFT to REJECTED status.

    Args:
        session_id: Session UUID
        task_id: Task UUID
        request: Rejection request with optional reason
        db: Database session

    Returns:
        Action response with rejected plan

    Raises:
        HTTPException: If plan not found (404) or invalid state (400)
    """
    service = PlanService(db)

    try:
        plan = await service.get_plan_by_task(task_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan not found for task {task_id}",
            )

        rejected_plan = await service.reject_plan(
            plan_id=plan.id,
            reason=request.reason,
        )

        logger.info(
            "plan_rejected_via_api",
            session_id=str(session_id),
            task_id=str(task_id),
            plan_id=str(plan.id),
            reason=request.reason,
        )

        return ActionResponse(
            success=True,
            message="Plan rejected",
            plan=PlanResponse.model_validate(rejected_plan),
        )
    except PlanNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except InvalidPlanStateError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
