"""Responder Agent for final user-facing response generation.

The Responder is responsible for:
1. Detecting user's original language
2. Generating a clean, user-friendly response summary
3. Separating artifacts (code) from conversational response
4. Ensuring response matches user's language
"""

from functools import lru_cache
from uuid import UUID

import structlog
from lingua import Language, LanguageDetector, LanguageDetectorBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.config import get_agent_settings
from agent.db.models.enums import TaskComplexity
from agent.llm import ChatMessage, LiteLLMClient, LLMRequest, LLMRouter
from agent.prompts import PromptManager, ResponderPrompts

logger = structlog.get_logger()


@lru_cache(maxsize=1)
def _get_language_detector() -> LanguageDetector:
    """Get cached language detector instance.

    Uses lingua-py for accurate language detection.
    Detector is cached to avoid repeated initialization.

    Returns:
        Configured language detector
    """
    return LanguageDetectorBuilder.from_all_languages().with_minimum_relative_distance(0.25).build()


def detect_language(text: str) -> str:
    """Detect the primary language of text.

    Uses lingua-py for accurate language detection with support
    for 75+ languages including short text.

    Args:
        text: Text to analyze

    Returns:
        ISO 639-1 language code (e.g., 'ko', 'en', 'ja', 'zh')
    """
    if not text or not text.strip():
        return "en"

    detector = _get_language_detector()
    detected = detector.detect_language_of(text)

    if detected is None:
        return "en"

    return detected.iso_code_639_1.name.lower()


def get_language_name(code: str) -> str:
    """Get human-readable language name from code.

    Uses lingua's Language enum for comprehensive language support.

    Args:
        code: ISO 639-1 language code

    Returns:
        Language name in English
    """
    for lang in Language:
        if lang.iso_code_639_1.name.lower() == code.lower():
            return lang.name.title()
    return "English"


class ResponderAgent:
    """Responder agent for generating final user-facing responses.

    Takes the worker output and original request to generate
    a clean, localized response for the user.
    """

    def __init__(
        self,
        llm_client: LiteLLMClient,
        router: LLMRouter,
        prompt_manager: PromptManager,
        session: AsyncSession,
    ) -> None:
        """Initialize Responder agent.

        Args:
            llm_client: LLM client for API calls
            router: Router for model selection
            prompt_manager: Prompt manager for template rendering
            session: Database session
        """
        self.llm_client = llm_client
        self.router = router
        self.prompt_manager = prompt_manager
        self.session = session

    async def generate_response(
        self,
        task_id: UUID,
        original_request: str,
        worker_output: str,
        has_artifacts: bool = False,
    ) -> str:
        """Generate final user-facing response.

        Args:
            task_id: Task ID for logging
            original_request: User's original request
            worker_output: Output from the last worker
            has_artifacts: Whether artifacts were generated

        Returns:
            Clean, localized response for user
        """
        # Detect user's language
        user_language = detect_language(original_request)
        language_name = get_language_name(user_language)

        logger.info(
            "responder_start",
            task_id=str(task_id),
            detected_language=user_language,
            has_artifacts=has_artifacts,
        )

        # Use a fast, simple model for response generation
        model = self.router.select_model(TaskComplexity.SIMPLE)

        # Build prompt
        system_prompt = self.prompt_manager.render(
            "responder",
            ResponderPrompts.SYSTEM_PROMPT,
            language=language_name,
            has_artifacts=has_artifacts,
        )

        user_prompt = self.prompt_manager.render(
            "responder",
            ResponderPrompts.GENERATE_RESPONSE,
            original_request=original_request,
            worker_output=worker_output,
            language=language_name,
            has_artifacts=has_artifacts,
        )

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]

        settings = get_agent_settings()
        request = LLMRequest(
            model=model.name,
            messages=messages,
            temperature=settings.worker_temperature,
            max_tokens=500,  # Keep response concise
            api_base=model.api_base,
            api_key=model.api_key,
        )

        response = await self.llm_client.chat_completion(request)
        final_response = response.content.strip()

        logger.info(
            "responder_complete",
            task_id=str(task_id),
            response_length=len(final_response),
            tokens=response.usage.total_tokens,
        )

        return final_response
