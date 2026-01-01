"""Summarizer Agent for context compression.

The Summarizer is responsible for:
1. Compressing context when memory pressure occurs
2. Preserving key decisions and artifacts
3. Creating memory snapshots for recovery
4. Maintaining session continuity
"""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.config import get_agent_settings
from agent.db.models.enums import SnapshotType, TaskComplexity
from agent.db.repository.memory_snapshot_repo import MemorySnapshotRepository
from agent.llm import ChatMessage, LiteLLMClient, LLMRequest, LLMRouter
from agent.prompts import PromptManager, SummarizerPrompts

logger = structlog.get_logger()


class SummarizerAgent:
    """Summarizer agent for context compression.

    Uses a medium-complexity LLM to intelligently compress conversation
    context while preserving critical information for session continuity.
    """

    def __init__(
        self,
        llm_client: LiteLLMClient,
        router: LLMRouter,
        prompt_manager: PromptManager,
        session: AsyncSession,
        compression_threshold: float = 0.85,
    ) -> None:
        """Initialize Summarizer agent.

        Args:
            llm_client: LLM client for API calls
            router: Router for model selection
            prompt_manager: Prompt manager for template rendering
            session: Database session
            compression_threshold: Context usage ratio to trigger compression (0.0-1.0)
        """
        self.llm_client = llm_client
        self.router = router
        self.prompt_manager = prompt_manager
        self.session = session
        self.compression_threshold = compression_threshold
        self.snapshot_repo = MemorySnapshotRepository(session)

    async def compress_context(
        self,
        session_id: UUID,
        task_id: UUID,
        conversation_history: list[ChatMessage],
        current_context_size: int,
        max_context_size: int,
    ) -> tuple[str, list[ChatMessage]]:
        """Compress conversation context to free memory.

        Args:
            session_id: Session ID for snapshot tracking
            task_id: Associated task ID
            conversation_history: Full conversation history to compress
            current_context_size: Current token count
            max_context_size: Maximum allowed token count

        Returns:
            Tuple of (summary, remaining_messages):
                - summary: Compressed context summary
                - remaining_messages: Recent messages to keep (last 3-5)

        Raises:
            ValueError: If compression fails
        """
        logger.info(
            "summarizer_start",
            session_id=str(session_id),
            task_id=str(task_id),
            current_size=current_context_size,
            max_size=max_context_size,
            message_count=len(conversation_history),
        )

        # Determine how many recent messages to preserve
        preserve_count = self._calculate_preserve_count(
            current_context_size,
            max_context_size,
        )

        # Split history into compressible and preserved parts
        messages_to_compress = (
            conversation_history[:-preserve_count] if preserve_count > 0 else conversation_history
        )
        preserved_messages = conversation_history[-preserve_count:] if preserve_count > 0 else []

        # Generate summary
        model = self.router.select_model(TaskComplexity.MODERATE)
        summary_prompt = self._build_summary_prompt(messages_to_compress)

        settings = get_agent_settings()
        request = LLMRequest(
            model=model.name,
            messages=[ChatMessage(role="user", content=summary_prompt)],
            temperature=settings.summarizer_temperature,
            api_base=model.api_base,
            api_key=model.api_key,
        )

        response = await self.llm_client.chat_completion(request)
        summary = response.content.strip()

        # Persist snapshot
        await self._persist_snapshot(
            session_id=session_id,
            summary=summary,
            compressed_message_count=len(messages_to_compress),
            preserved_message_count=preserve_count,
            snapshot_type=SnapshotType.AUTO,
        )

        logger.info(
            "summarizer_complete",
            session_id=str(session_id),
            compressed_count=len(messages_to_compress),
            preserved_count=preserve_count,
            summary_length=len(summary),
            tokens_used=response.usage.total_tokens,
        )

        return summary, preserved_messages

    async def create_manual_snapshot(
        self,
        session_id: UUID,
        task_id: UUID,
        conversation_history: list[ChatMessage],
        reason: str = "Manual checkpoint",
    ) -> str:
        """Create a manual memory snapshot for session pause/resume.

        Args:
            session_id: Session ID
            task_id: Task ID
            conversation_history: Full conversation to snapshot
            reason: Reason for snapshot

        Returns:
            Summary of conversation state
        """
        logger.info(
            "manual_snapshot_start",
            session_id=str(session_id),
            task_id=str(task_id),
            message_count=len(conversation_history),
        )

        model = self.router.select_model(TaskComplexity.MODERATE)
        summary_prompt = self._build_checkpoint_prompt(conversation_history)

        settings = get_agent_settings()
        request = LLMRequest(
            model=model.name,
            messages=[ChatMessage(role="user", content=summary_prompt)],
            temperature=settings.summarizer_temperature,
            api_base=model.api_base,
            api_key=model.api_key,
        )

        response = await self.llm_client.chat_completion(request)
        summary = response.content.strip()

        # Persist snapshot with manual type
        await self._persist_snapshot(
            session_id=session_id,
            summary=summary,
            compressed_message_count=len(conversation_history),
            preserved_message_count=0,
            snapshot_type=SnapshotType.MANUAL,
        )

        logger.info(
            "manual_snapshot_complete",
            session_id=str(session_id),
            summary_length=len(summary),
        )

        return summary

    def _build_summary_prompt(
        self,
        messages: list[ChatMessage],
    ) -> str:
        """Build prompt for context summarization.

        Args:
            messages: Messages to summarize

        Returns:
            Formatted summary prompt
        """
        conversation_text = self._format_conversation(messages)

        return self.prompt_manager.render(
            "summarizer",
            SummarizerPrompts.SUMMARY_PROMPT,
            conversation_text=conversation_text,
        )

    def _build_checkpoint_prompt(
        self,
        messages: list[ChatMessage],
    ) -> str:
        """Build prompt for manual checkpoint.

        Args:
            messages: Full conversation history

        Returns:
            Formatted checkpoint prompt
        """
        conversation_text = self._format_conversation(messages)

        return self.prompt_manager.render(
            "summarizer",
            SummarizerPrompts.CHECKPOINT_PROMPT,
            conversation_text=conversation_text,
        )

    def _format_conversation(
        self,
        messages: list[ChatMessage],
    ) -> str:
        """Format conversation history into text.

        Args:
            messages: Chat messages to format

        Returns:
            Formatted conversation text
        """
        formatted = []
        for msg in messages:
            role = msg.role.upper()
            formatted.append(f"{role}: {msg.content}\n")

        return "\n".join(formatted)

    def _calculate_preserve_count(
        self,
        current_size: int,
        max_size: int,
    ) -> int:
        """Calculate how many recent messages to preserve.

        Args:
            current_size: Current token count
            max_size: Maximum allowed tokens

        Returns:
            Number of recent messages to preserve
        """
        # Preserve 3-5 recent messages based on context pressure
        usage_ratio = current_size / max_size

        if usage_ratio > 0.95:
            return 2  # Extreme pressure - minimal preservation
        elif usage_ratio > 0.90:
            return 3  # High pressure
        elif usage_ratio > 0.85:
            return 4  # Moderate pressure
        else:
            return 5  # Standard preservation

    async def _persist_snapshot(
        self,
        session_id: UUID,
        summary: str,
        compressed_message_count: int,
        preserved_message_count: int,
        snapshot_type: SnapshotType,
    ) -> None:
        """Persist memory snapshot to database.

        Args:
            session_id: Session ID
            summary: Compressed summary
            compressed_message_count: Number of messages compressed
            preserved_message_count: Number of messages preserved
            snapshot_type: Type of snapshot
        """
        token_count = self.router.estimate_tokens(summary)

        await self.snapshot_repo.create(
            session_id=session_id,
            snapshot_type=snapshot_type.value,
            compressed_context=summary,
            token_count=token_count,
        )

        logger.debug(
            "snapshot_persisted",
            session_id=str(session_id),
            type=snapshot_type.value,
            token_count=token_count,
            compressed_count=compressed_message_count,
            preserved_count=preserved_message_count,
        )

    def should_compress(
        self,
        current_tokens: int,
        max_tokens: int,
    ) -> bool:
        """Determine if context compression is needed.

        Args:
            current_tokens: Current context token count
            max_tokens: Maximum allowed tokens

        Returns:
            True if compression should be triggered
        """
        usage_ratio = current_tokens / max_tokens
        return usage_ratio >= self.compression_threshold
