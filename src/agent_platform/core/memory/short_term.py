"""
Short-term memory (session-based conversation context)
"""

from typing import List, Optional
import structlog

logger = structlog.get_logger()


class ShortTermMemory:
    """Redis-based session memory"""

    async def add_message(self, session_id: str, message: dict) -> None:
        """Add message to session history"""
        logger.info("adding_message_to_session", session_id=session_id)
        # TODO: Implement Redis storage
        pass

    async def get_context(
        self, session_id: str, limit: int = 20
    ) -> List[dict]:
        """Get recent messages for session"""
        logger.info("fetching_session_context", session_id=session_id, limit=limit)
        # TODO: Implement Redis retrieval
        return []

    async def clear_session(self, session_id: str) -> None:
        """Clear session history"""
        logger.info("clearing_session", session_id=session_id)
        # TODO: Implement Redis deletion
        pass


# Global instance
short_term_memory = ShortTermMemory()
