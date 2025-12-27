"""Session lifecycle management service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.cache import SessionCache
from agent.container import get_container
from agent.core import SummarizerAgent
from agent.db.models.enums import SessionStatus, TaskStatus
from agent.db.repository.memory_snapshot_repo import MemorySnapshotRepository
from agent.db.repository.session_repo import SessionRepository
from agent.db.repository.task_repo import TaskRepository
from agent.llm import ChatMessage

from ..exceptions import AccessDeniedError, InvalidStateError, NotFoundError
from ..schemas import (
    PaginatedResponse,
    SessionDetailResponse,
    SessionResponse,
    SnapshotResponse,
    TaskResponse,
    WSMessage,
    WSMessageType,
)

if TYPE_CHECKING:
    from agent.db.models import Session

    from ..websocket.manager import ConnectionManager

logger = structlog.get_logger()


class SessionService:
    """Session lifecycle management.

    Handles session creation, pause/resume, and completion.
    """

    def __init__(
        self,
        db_session: AsyncSession,
        cache: SessionCache,
        ws_manager: ConnectionManager | None = None,
    ) -> None:
        """Initialize session service.

        Args:
            db_session: Database session
            cache: Session cache
            ws_manager: Optional WebSocket manager for notifications
        """
        self.db = db_session
        self.cache = cache
        self.ws_manager = ws_manager
        self.session_repo = SessionRepository(db_session)
        self.task_repo = TaskRepository(db_session)
        self.snapshot_repo = MemorySnapshotRepository(db_session)

    async def create_session(
        self,
        user_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> SessionResponse:
        """Create a new session.

        Args:
            user_id: User ID
            metadata: Optional session metadata

        Returns:
            Created session response
        """
        session = await self.session_repo.create(
            user_id=user_id,
            status=SessionStatus.ACTIVE.value,
        )
        await self.db.commit()

        # Cache session state
        await self.cache.set_session_state(
            session.id,
            {
                "status": session.status,
                "user_id": user_id,
                "created_at": session.created_at.isoformat(),
            },
        )

        # Invalidate user sessions cache
        await self.cache.invalidate_user_sessions(user_id)

        logger.info(
            "session_created",
            session_id=str(session.id),
            user_id=user_id,
        )

        return SessionResponse.model_validate(session)

    async def get_session(
        self,
        session_id: UUID,
        user_id: str,
    ) -> SessionDetailResponse:
        """Get session details.

        Args:
            session_id: Session ID
            user_id: User ID for access check

        Returns:
            Session detail response

        Raises:
            NotFoundError: If session not found
            AccessDeniedError: If user doesn't own session
        """
        session = await self._get_session_for_user(session_id, user_id)

        # Get tasks
        tasks = await self.task_repo.get_by_session_id(session_id)
        task_responses = [TaskResponse.model_validate(t) for t in tasks]

        # Find active task
        active_task = None
        for task in tasks:
            if task.status == TaskStatus.IN_PROGRESS.value:
                active_task = TaskResponse.model_validate(task)
                break

        return SessionDetailResponse(
            **SessionResponse.model_validate(session).model_dump(),
            tasks=task_responses,
            active_task=active_task,
        )

    async def list_sessions(
        self,
        user_id: str,
        status: SessionStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedResponse[SessionResponse]:
        """List user sessions.

        Args:
            user_id: User ID
            status: Optional status filter
            limit: Maximum results
            offset: Offset for pagination

        Returns:
            Paginated session response
        """
        # Get sessions
        if status:
            sessions = await self.session_repo.get_by_user_id(
                user_id,
                limit=limit + 1,  # +1 to check has_more
                offset=offset,
            )
            # Filter by status
            sessions = [s for s in sessions if s.status == status.value]
        else:
            sessions = await self.session_repo.get_by_user_id(
                user_id,
                limit=limit + 1,
                offset=offset,
            )

        # Check if there are more
        has_more = len(sessions) > limit
        if has_more:
            sessions = sessions[:limit]

        return PaginatedResponse(
            items=[SessionResponse.model_validate(s) for s in sessions],
            total=len(sessions),  # Note: This is not accurate total count
            limit=limit,
            offset=offset,
            has_more=has_more,
        )

    async def pause_session(
        self,
        session_id: UUID,
        user_id: str,
        context_messages: list[ChatMessage] | None = None,
    ) -> SessionResponse:
        """Pause session and create memory snapshot.

        Args:
            session_id: Session ID
            user_id: User ID
            context_messages: Optional context to snapshot

        Returns:
            Updated session response

        Raises:
            InvalidStateError: If session cannot be paused
        """
        session = await self._get_session_for_user(session_id, user_id)

        if session.status != SessionStatus.ACTIVE.value:
            raise InvalidStateError(
                resource="Session",
                current_state=session.status,
                action="paused",
            )

        # Create snapshot if context provided
        if context_messages:
            await self._create_pause_snapshot(session_id, context_messages)

        # Update session status
        updated_session = await self.session_repo.pause_session(session_id)
        if updated_session is None:
            raise NotFoundError("Session", session_id)
        await self.db.commit()

        # Invalidate cache
        await self.cache.invalidate_session_state(session_id)

        # Notify WebSocket clients
        if self.ws_manager:
            await self.ws_manager.broadcast_to_session(
                session_id,
                WSMessage(
                    type=WSMessageType.SESSION_PAUSED,
                    payload={"session_id": str(session_id)},
                ),
            )

        logger.info("session_paused", session_id=str(session_id))

        return SessionResponse.model_validate(updated_session)

    async def resume_session(
        self,
        session_id: UUID,
        user_id: str,
    ) -> tuple[SessionResponse, dict[str, Any] | None]:
        """Resume paused session.

        Args:
            session_id: Session ID
            user_id: User ID

        Returns:
            Tuple of (session response, context if available)

        Raises:
            InvalidStateError: If session cannot be resumed
        """
        session = await self._get_session_for_user(session_id, user_id)

        if session.status != SessionStatus.PAUSED.value:
            raise InvalidStateError(
                resource="Session",
                current_state=session.status,
                action="resumed",
            )

        # Try to get context from cache first
        context = await self.cache.get_cached_context(session_id)

        # If not in cache, get from latest snapshot
        if context is None:
            snapshot = await self.snapshot_repo.get_latest_snapshot(session_id)
            if snapshot:
                context = {
                    "summary": snapshot.compressed_context,
                    "key_decisions": snapshot.key_decisions,
                    "snapshot_id": str(snapshot.id),
                }

        # Update session status
        updated_session = await self.session_repo.update(
            session_id,
            status=SessionStatus.ACTIVE.value,
        )
        if updated_session is None:
            raise NotFoundError("Session", session_id)
        await self.db.commit()

        # Invalidate cache
        await self.cache.invalidate_session_state(session_id)

        # Notify WebSocket clients
        if self.ws_manager:
            await self.ws_manager.broadcast_to_session(
                session_id,
                WSMessage(
                    type=WSMessageType.SESSION_RESUMED,
                    payload={
                        "session_id": str(session_id),
                        "has_context": context is not None,
                    },
                ),
            )

        logger.info(
            "session_resumed",
            session_id=str(session_id),
            has_context=context is not None,
        )

        return SessionResponse.model_validate(updated_session), context

    async def complete_session(
        self,
        session_id: UUID,
        user_id: str,
    ) -> SessionResponse:
        """Mark session as completed.

        Args:
            session_id: Session ID
            user_id: User ID

        Returns:
            Updated session response
        """
        session = await self._get_session_for_user(session_id, user_id)

        if session.status not in (
            SessionStatus.ACTIVE.value,
            SessionStatus.PAUSED.value,
        ):
            raise InvalidStateError(
                resource="Session",
                current_state=session.status,
                action="completed",
            )

        closed_session = await self.session_repo.close_session(session_id)
        if closed_session is None:
            raise NotFoundError("Session", session_id)
        await self.db.commit()

        # Invalidate caches
        await self.cache.invalidate_session_state(session_id)
        await self.cache.invalidate_user_sessions(user_id)

        logger.info("session_completed", session_id=str(session_id))

        return SessionResponse.model_validate(closed_session)

    async def delete_session(
        self,
        session_id: UUID,
        user_id: str,
    ) -> None:
        """Delete session.

        Args:
            session_id: Session ID
            user_id: User ID
        """
        session = await self._get_session_for_user(session_id, user_id)

        # Only allow deleting completed or failed sessions
        if session.status not in (
            SessionStatus.COMPLETED.value,
            SessionStatus.FAILED.value,
        ):
            raise InvalidStateError(
                resource="Session",
                current_state=session.status,
                action="deleted",
            )

        await self.session_repo.delete(session_id)
        await self.db.commit()

        # Invalidate caches
        await self.cache.invalidate_session_state(session_id)
        await self.cache.invalidate_user_sessions(user_id)

        logger.info("session_deleted", session_id=str(session_id))

    async def list_snapshots(
        self,
        session_id: UUID,
        user_id: str,
        limit: int = 20,
    ) -> list[SnapshotResponse]:
        """List session snapshots.

        Args:
            session_id: Session ID
            user_id: User ID
            limit: Maximum results

        Returns:
            List of snapshot responses
        """
        await self._get_session_for_user(session_id, user_id)

        snapshots = await self.snapshot_repo.get_by_session(
            session_id,
            limit=limit,
        )

        return [SnapshotResponse.model_validate(s) for s in snapshots]

    async def create_snapshot(
        self,
        session_id: UUID,
        user_id: str,
        reason: str = "Manual checkpoint",
    ) -> SnapshotResponse:
        """Create a manual memory snapshot.

        Args:
            session_id: Session ID
            user_id: User ID
            reason: Reason for snapshot

        Returns:
            Created snapshot response
        """
        session = await self._get_session_for_user(session_id, user_id)

        if session.status != SessionStatus.ACTIVE.value:
            raise InvalidStateError(
                resource="Session",
                current_state=session.status,
                action="snapshot",
            )

        # Get active task for snapshot
        tasks = await self.task_repo.get_by_session_id(session_id, limit=1)
        if not tasks:
            raise InvalidStateError(
                resource="Session",
                current_state="no active task",
                action="snapshot",
            )

        task = tasks[0]

        # Create snapshot using summarizer
        container = get_container()
        summarizer = SummarizerAgent(
            llm_client=container.llm_client,
            router=container.router,
            session=self.db,
        )

        # Get context from cache
        cached_context = await self.cache.get_cached_context(session_id)
        context_messages: list[ChatMessage] = []
        if cached_context and "messages" in cached_context:
            context_messages = cached_context["messages"]

        # Create snapshot (returns summary string)
        await summarizer.create_manual_snapshot(
            session_id=session_id,
            task_id=task.id,
            conversation_history=context_messages,
            reason=reason,
        )

        # Get the latest snapshot that was just created
        created_snapshot = await self.snapshot_repo.get_latest_snapshot(session_id)
        if created_snapshot is None:
            raise InvalidStateError(
                resource="Snapshot",
                current_state="not created",
                action="retrieve",
            )

        logger.info(
            "snapshot_created",
            session_id=str(session_id),
            snapshot_id=str(created_snapshot.id),
            reason=reason,
        )

        return SnapshotResponse.model_validate(created_snapshot)

    async def get_snapshot(
        self,
        snapshot_id: UUID,
        user_id: str,
    ) -> SnapshotResponse:
        """Get snapshot by ID.

        Args:
            snapshot_id: Snapshot ID
            user_id: User ID for access check

        Returns:
            Snapshot response

        Raises:
            NotFoundError: If snapshot not found
            AccessDeniedError: If user doesn't own session
        """
        snapshot = await self.snapshot_repo.get_by_id(snapshot_id)
        if snapshot is None:
            raise NotFoundError("Snapshot", snapshot_id)

        # Verify session ownership
        await self._get_session_for_user(snapshot.session_id, user_id)

        return SnapshotResponse.model_validate(snapshot)

    async def get_latest_snapshot(
        self,
        session_id: UUID,
        user_id: str,
    ) -> SnapshotResponse:
        """Get latest snapshot for session.

        Args:
            session_id: Session ID
            user_id: User ID for access check

        Returns:
            Latest snapshot response

        Raises:
            NotFoundError: If no snapshots exist
        """
        await self._get_session_for_user(session_id, user_id)

        snapshot = await self.snapshot_repo.get_latest_snapshot(session_id)
        if snapshot is None:
            raise NotFoundError("Snapshot", session_id)

        return SnapshotResponse.model_validate(snapshot)

    async def _get_session_for_user(
        self,
        session_id: UUID,
        user_id: str,
    ) -> Session:
        """Get session and verify ownership.

        Args:
            session_id: Session ID
            user_id: User ID

        Returns:
            Session model

        Raises:
            NotFoundError: If session not found
            AccessDeniedError: If user doesn't own session
        """
        session = await self.session_repo.get_by_id(session_id)

        if session is None:
            raise NotFoundError("Session", session_id)

        if session.user_id != user_id:
            raise AccessDeniedError("Session", session_id)

        return session

    async def _create_pause_snapshot(
        self,
        session_id: UUID,
        context_messages: list[ChatMessage],
    ) -> None:
        """Create snapshot for session pause.

        Args:
            session_id: Session ID
            context_messages: Context messages to snapshot
        """
        container = get_container()
        summarizer = SummarizerAgent(
            llm_client=container.llm_client,
            router=container.router,
            session=self.db,
        )

        # Get active task
        tasks = await self.task_repo.get_by_session_id(session_id, limit=1)
        if not tasks:
            return

        task_id = tasks[0].id

        await summarizer.create_manual_snapshot(
            session_id=session_id,
            task_id=task_id,
            conversation_history=context_messages,
            reason="Session paused",
        )
