"""Task management endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from bsai.db.models.enums import TaskStatus
from bsai.llm.schemas import BreakpointConfig, QAConfig

from ..dependencies import (
    AppBreakpointService,
    AppEventBus,
    Cache,
    CurrentUserId,
    DBSession,
    WSManager,
)
from ..schemas import (
    ActionResponse,
    BuildResultResponse,
    LintResultResponse,
    PaginatedResponse,
    ProgressResponse,
    QAConfigRequest,
    QAResultResponse,
    TaskCreate,
    TaskDetailResponse,
    TaskReject,
    TaskResponse,
    TaskResume,
    TestResultResponse,
    TypecheckResultResponse,
)
from ..services import TaskService

router = APIRouter(prefix="/sessions/{session_id}/tasks", tags=["tasks"])


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create and execute task",
)
async def create_task(
    session_id: UUID,
    request: TaskCreate,
    db: DBSession,
    cache: Cache,
    event_bus: AppEventBus,
    ws_manager: WSManager,
    breakpoint_service: AppBreakpointService,
    user_id: CurrentUserId,
) -> TaskResponse:
    """Create a new task and start execution.

    The task will be executed asynchronously. Use WebSocket
    to receive real-time progress updates.

    Args:
        session_id: Session UUID
        request: Task creation request
        db: Database session
        cache: Session cache
        event_bus: EventBus for event-driven notifications
        ws_manager: WebSocket connection manager
        breakpoint_service: BreakpointService for HITL workflows
        user_id: Current user ID

    Returns:
        Created task (202 Accepted)
    """
    service = TaskService(db, cache, event_bus, ws_manager, breakpoint_service)
    return await service.create_and_execute_task(
        session_id=session_id,
        user_id=user_id,
        request=request,
    )


@router.get(
    "",
    response_model=PaginatedResponse[TaskResponse],
    summary="List session tasks",
)
async def list_tasks(
    session_id: UUID,
    db: DBSession,
    cache: Cache,
    event_bus: AppEventBus,
    ws_manager: WSManager,
    breakpoint_service: AppBreakpointService,
    user_id: CurrentUserId,
    status: TaskStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> PaginatedResponse[TaskResponse]:
    """List tasks for a session.

    Args:
        session_id: Session UUID
        db: Database session
        cache: Session cache
        event_bus: EventBus for event-driven notifications
        ws_manager: WebSocket connection manager
        breakpoint_service: BreakpointService for HITL workflows
        user_id: Current user ID
        status: Optional status filter
        limit: Maximum results per page
        offset: Offset for pagination

    Returns:
        Paginated list of tasks
    """
    service = TaskService(db, cache, event_bus, ws_manager, breakpoint_service)
    return await service.list_tasks(
        session_id=session_id,
        user_id=user_id,
        status=status,
        limit=min(limit, 100),
        offset=offset,
    )


@router.get(
    "/{task_id}",
    response_model=TaskDetailResponse,
    summary="Get task details",
)
async def get_task(
    session_id: UUID,
    task_id: UUID,
    db: DBSession,
    cache: Cache,
    event_bus: AppEventBus,
    ws_manager: WSManager,
    breakpoint_service: AppBreakpointService,
    user_id: CurrentUserId,
) -> TaskDetailResponse:
    """Get detailed task information including milestones.

    Args:
        session_id: Session UUID (for URL consistency)
        task_id: Task UUID
        db: Database session
        cache: Session cache
        event_bus: EventBus for event-driven notifications
        ws_manager: WebSocket connection manager
        breakpoint_service: BreakpointService for HITL workflows
        user_id: Current user ID

    Returns:
        Task details with milestones
    """
    # session_id is included in path for REST consistency
    # but task_id is globally unique
    _ = session_id
    service = TaskService(db, cache, event_bus, ws_manager, breakpoint_service)
    return await service.get_task(task_id, user_id)


@router.put(
    "/{task_id}/cancel",
    response_model=TaskResponse,
    summary="Cancel running task",
)
async def cancel_task(
    session_id: UUID,
    task_id: UUID,
    db: DBSession,
    cache: Cache,
    event_bus: AppEventBus,
    ws_manager: WSManager,
    breakpoint_service: AppBreakpointService,
    user_id: CurrentUserId,
) -> TaskResponse:
    """Cancel a running task.

    Only tasks with status IN_PROGRESS can be cancelled.

    Args:
        session_id: Session UUID (for URL consistency)
        task_id: Task UUID
        db: Database session
        cache: Session cache
        event_bus: EventBus for event-driven notifications
        ws_manager: WebSocket connection manager
        breakpoint_service: BreakpointService for HITL workflows
        user_id: Current user ID

    Returns:
        Updated task
    """
    _ = session_id
    service = TaskService(db, cache, event_bus, ws_manager, breakpoint_service)
    return await service.cancel_task(task_id, user_id)


@router.put(
    "/{task_id}/resume",
    response_model=TaskResponse,
    summary="Resume paused task",
)
async def resume_task(
    session_id: UUID,
    task_id: UUID,
    request: TaskResume,
    db: DBSession,
    cache: Cache,
    event_bus: AppEventBus,
    ws_manager: WSManager,
    breakpoint_service: AppBreakpointService,
    user_id: CurrentUserId,
) -> TaskResponse:
    """Resume a task that is paused at a breakpoint.

    This endpoint is used for Human-in-the-Loop workflows where
    a task has been paused for user review.

    Args:
        session_id: Session UUID (for URL consistency)
        task_id: Task UUID
        request: Resume request with optional user input
        db: Database session
        cache: Session cache
        event_bus: EventBus for event-driven notifications
        ws_manager: WebSocket connection manager
        breakpoint_service: BreakpointService for HITL workflows
        user_id: Current user ID

    Returns:
        Updated task
    """
    _ = session_id
    service = TaskService(db, cache, event_bus, ws_manager, breakpoint_service)
    return await service.resume_task(task_id, user_id, request.user_input, request.rejected)


@router.put(
    "/{task_id}/reject",
    response_model=TaskResponse,
    summary="Reject task at breakpoint",
)
async def reject_task(
    session_id: UUID,
    task_id: UUID,
    request: TaskReject,
    db: DBSession,
    cache: Cache,
    event_bus: AppEventBus,
    ws_manager: WSManager,
    breakpoint_service: AppBreakpointService,
    user_id: CurrentUserId,
) -> TaskResponse:
    """Reject and cancel a task at a breakpoint.

    This endpoint is used when the user wants to abort the task
    during a Human-in-the-Loop review.

    Args:
        session_id: Session UUID (for URL consistency)
        task_id: Task UUID
        request: Reject request with optional reason
        db: Database session
        cache: Session cache
        event_bus: EventBus for event-driven notifications
        ws_manager: WebSocket connection manager
        breakpoint_service: BreakpointService for HITL workflows
        user_id: Current user ID

    Returns:
        Updated task (with FAILED status)
    """
    _ = session_id
    service = TaskService(db, cache, event_bus, ws_manager, breakpoint_service)
    return await service.reject_task(task_id, user_id, request.reason)


@router.get(
    "/{task_id}/progress",
    response_model=ProgressResponse,
    summary="Get task execution progress",
)
async def get_task_progress(
    session_id: UUID,
    task_id: UUID,
    db: DBSession,
    cache: Cache,
    event_bus: AppEventBus,
    ws_manager: WSManager,
    breakpoint_service: AppBreakpointService,
    user_id: CurrentUserId,
) -> ProgressResponse:
    """Get current task execution progress.

    Returns progress information including:
    - Overall completion percentage
    - Task/Feature/Epic level progress
    - Current breakpoint reason (if paused)

    Args:
        session_id: Session UUID (for URL consistency)
        task_id: Task UUID
        db: Database session
        cache: Session cache
        event_bus: EventBus for event-driven notifications
        ws_manager: WebSocket connection manager
        breakpoint_service: BreakpointService for HITL workflows
        user_id: Current user ID

    Returns:
        Progress information for the task
    """
    _ = session_id
    service = TaskService(db, cache, event_bus, ws_manager, breakpoint_service)
    progress = await service.get_progress(task_id, user_id)
    return ProgressResponse(**progress)


@router.put(
    "/{task_id}/breakpoint-config",
    response_model=ActionResponse,
    summary="Update breakpoint configuration",
)
async def update_breakpoint_config(
    session_id: UUID,
    task_id: UUID,
    config: BreakpointConfig,
    db: DBSession,
    cache: Cache,
    event_bus: AppEventBus,
    ws_manager: WSManager,
    breakpoint_service: AppBreakpointService,
    user_id: CurrentUserId,
) -> ActionResponse:
    """Update breakpoint configuration during execution.

    Allows changing breakpoint settings while task is running.

    Args:
        session_id: Session UUID (for URL consistency)
        task_id: Task UUID
        config: New breakpoint configuration
        db: Database session
        cache: Session cache
        event_bus: EventBus for event-driven notifications
        ws_manager: WebSocket connection manager
        breakpoint_service: BreakpointService for HITL workflows
        user_id: Current user ID

    Returns:
        Success status
    """
    _ = session_id
    service = TaskService(db, cache, event_bus, ws_manager, breakpoint_service)
    await service.update_breakpoint_config(task_id, user_id, config)
    return ActionResponse(
        success=True,
        message="Breakpoint config updated",
    )


@router.get(
    "/{task_id}/qa-results",
    response_model=QAResultResponse,
    summary="Get QA validation results",
)
async def get_qa_results(
    session_id: UUID,
    task_id: UUID,
    db: DBSession,
    cache: Cache,
    event_bus: AppEventBus,
    ws_manager: WSManager,
    breakpoint_service: AppBreakpointService,
    user_id: CurrentUserId,
) -> QAResultResponse:
    """Get QA validation results for a task.

    Returns detailed results of all QA validations including:
    - Static analysis (LLM)
    - Lint results
    - Type check results
    - Test results
    - Build results

    Args:
        session_id: Session UUID (for URL consistency)
        task_id: Task UUID
        db: Database session
        cache: Session cache
        event_bus: EventBus for event-driven notifications
        ws_manager: WebSocket connection manager
        breakpoint_service: BreakpointService for HITL workflows
        user_id: Current user ID

    Returns:
        QA validation results
    """
    _ = session_id
    service = TaskService(db, cache, event_bus, ws_manager, breakpoint_service)
    qa_result = await service.get_qa_result(task_id, user_id)
    if qa_result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="QA results not found",
        )

    return QAResultResponse(
        task_id=task_id,
        decision=qa_result.decision,
        confidence=qa_result.confidence,
        summary=qa_result.summary,
        static_analysis=(
            {
                "issues": qa_result.static_issues,
                "suggestions": qa_result.static_suggestions,
            }
            if qa_result.static_issues or qa_result.static_suggestions
            else None
        ),
        lint=(
            LintResultResponse(
                success=qa_result.lint_result.success,
                errors=qa_result.lint_result.errors,
                warnings=qa_result.lint_result.warnings,
                issues=qa_result.lint_result.issues,
            )
            if qa_result.lint_result
            else None
        ),
        typecheck=(
            TypecheckResultResponse(
                success=qa_result.typecheck_result.success,
                errors=qa_result.typecheck_result.errors,
                issues=qa_result.typecheck_result.issues,
            )
            if qa_result.typecheck_result
            else None
        ),
        test=(
            TestResultResponse(
                success=qa_result.test_result.success,
                passed=qa_result.test_result.passed,
                failed=qa_result.test_result.failed,
                skipped=qa_result.test_result.skipped,
                total=qa_result.test_result.total,
                coverage=qa_result.test_result.coverage,
                failed_tests=qa_result.test_result.failed_tests,
            )
            if qa_result.test_result
            else None
        ),
        build=(
            BuildResultResponse(
                success=qa_result.build_result.success,
                error_message=qa_result.build_result.error_message,
            )
            if qa_result.build_result
            else None
        ),
    )


@router.put(
    "/{task_id}/qa-config",
    response_model=ActionResponse,
    summary="Update QA configuration",
)
async def update_qa_config(
    session_id: UUID,
    task_id: UUID,
    config: QAConfigRequest,
    db: DBSession,
    cache: Cache,
    event_bus: AppEventBus,
    ws_manager: WSManager,
    breakpoint_service: AppBreakpointService,
    user_id: CurrentUserId,
) -> ActionResponse:
    """Update QA configuration for a task.

    Allows changing which validations are enabled:
    - STATIC: LLM-based analysis
    - LINT: Code linting
    - TYPECHECK: Type checking
    - TEST: Test execution
    - BUILD: Build verification

    Args:
        session_id: Session UUID (for URL consistency)
        task_id: Task UUID
        config: QA configuration request
        db: Database session
        cache: Session cache
        event_bus: EventBus for event-driven notifications
        ws_manager: WebSocket connection manager
        breakpoint_service: BreakpointService for HITL workflows
        user_id: Current user ID

    Returns:
        Success status
    """
    _ = session_id
    service = TaskService(db, cache, event_bus, ws_manager, breakpoint_service)

    # Convert QAConfigRequest to QAConfig
    qa_config = QAConfig(
        validations=config.validations,
        test_command=config.test_command,
        lint_command=config.lint_command,
        typecheck_command=config.typecheck_command,
        build_command=config.build_command,
        allow_lint_warnings=config.allow_lint_warnings,
        require_all_tests_pass=config.require_all_tests_pass,
    )

    await service.update_qa_config(task_id, user_id, qa_config)
    return ActionResponse(
        success=True,
        message="QA config updated",
    )
