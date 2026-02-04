"""Responder Agent for final user-facing response generation.

The Responder is responsible for:
1. Detecting user's original language
2. Generating a clean, user-friendly response summary
3. Separating artifacts (code) from conversational response
4. Ensuring response matches user's language
5. Integrating task summary for project plan executions
"""

from functools import lru_cache
from typing import Any
from uuid import UUID

import structlog
from lingua import Language, LanguageDetector, LanguageDetectorBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.config import get_agent_settings
from agent.db.models.enums import TaskComplexity
from agent.db.models.project_plan import ProjectPlan
from agent.llm import ChatMessage, LiteLLMClient, LLMRequest, LLMRouter
from agent.llm.schemas import QAResult
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
    for lang in Language.all():
        if lang.iso_code_639_1.name.lower() == code.lower():
            return lang.name.title()
    return "English"


class ResponderAgent:
    """Responder agent for generating final user-facing responses.

    Takes the worker output and original request to generate
    a clean, localized response for the user.

    Now includes task summary functionality for project plan executions.
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
            max_tokens=2000,
            api_base=model.api_base,
            api_key=model.api_key,
        )

        response = await self.llm_client.chat_completion(request, mcp_servers=[])
        final_response = response.content.strip()

        logger.info(
            "responder_complete",
            task_id=str(task_id),
            response_length=len(final_response),
            tokens=response.usage.total_tokens,
        )

        return final_response

    async def generate_failure_report(
        self,
        task_id: UUID,
        original_request: str,
        failure_context: dict[str, Any],
    ) -> str:
        """Generate a detailed failure report for the user.

        Called when a task has failed after all retry attempts and strategy
        changes. Provides the user with context about what was tried and
        suggestions for next steps.

        Args:
            task_id: Task ID for logging
            original_request: User's original request
            failure_context: Dict containing:
                - attempted_milestones: List of milestones that were attempted
                - final_error: The final error message
                - partial_results: Any partial results that were achieved

        Returns:
            Detailed failure report for the user
        """
        # Detect user's language
        user_language = detect_language(original_request)
        language_name = get_language_name(user_language)

        logger.info(
            "responder_failure_report_start",
            task_id=str(task_id),
            detected_language=user_language,
        )

        # Build attempted summary from milestones
        attempted_milestones = failure_context.get("attempted_milestones", [])
        attempted_parts = []
        for i, m in enumerate(attempted_milestones):
            status = m.get("status", "unknown")
            if hasattr(status, "value"):
                status = status.value
            attempted_parts.append(
                f"{i + 1}. {m.get('description', 'Unknown task')} - Status: {status}"
            )
        attempted_summary = (
            "\n".join(attempted_parts) if attempted_parts else "No milestones attempted"
        )

        # Build failure reasons
        failure_reasons_list = []
        final_error = failure_context.get("final_error")
        if final_error:
            failure_reasons_list.append(f"Final error: {final_error}")

        # Extract QA feedback from failed milestones
        for m in attempted_milestones:
            qa_feedback = m.get("qa_feedback")
            if qa_feedback:
                failure_reasons_list.append(f"QA feedback: {qa_feedback}")

        failure_reasons = (
            "\n".join(failure_reasons_list) if failure_reasons_list else "Unknown failure reason"
        )

        # Build partial results
        partial_results_list = []
        for m in attempted_milestones:
            if m.get("status") and str(m.get("status")).lower() in ("passed", "pass"):
                output = m.get("worker_output", "")
                if output:
                    desc = m.get("description", "Completed step")
                    partial_results_list.append(f"**{desc}**:\n{output[:500]}...")
        partial_results = (
            "\n\n".join(partial_results_list)
            if partial_results_list
            else "No partial results available"
        )
        has_partial_results = bool(partial_results_list)

        # Use a MODERATE model for failure report (needs reasoning)
        model = self.router.select_model(TaskComplexity.MODERATE)

        # Build prompt
        system_prompt = self.prompt_manager.render(
            "responder",
            ResponderPrompts.SYSTEM_PROMPT,
            language=language_name,
            has_artifacts=False,
        )

        user_prompt = self.prompt_manager.render(
            "responder",
            ResponderPrompts.FAILURE_REPORT_PROMPT,
            original_request=original_request,
            attempted_summary=attempted_summary,
            failure_reasons=failure_reasons,
            partial_results=partial_results,
            language=language_name,
            has_partial_results=has_partial_results,
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
            max_tokens=3000,
            api_base=model.api_base,
            api_key=model.api_key,
        )

        response = await self.llm_client.chat_completion(request, mcp_servers=[])
        failure_report = response.content.strip()

        logger.info(
            "responder_failure_report_complete",
            task_id=str(task_id),
            report_length=len(failure_report),
            tokens=response.usage.total_tokens,
        )

        return failure_report

    def _generate_task_summary(
        self,
        project_plan: ProjectPlan | None,
        task_results: dict[str, dict[str, Any]],
        qa_results: dict[str, QAResult],
    ) -> str:
        """Generate summary of all completed tasks.

        Creates a markdown-formatted summary of task execution results
        including status icons, QA results, and overall statistics.

        Args:
            project_plan: Project plan (if available)
            task_results: Results from all tasks, keyed by task ID
            qa_results: QA results for all tasks, keyed by task ID

        Returns:
            Markdown-formatted task summary string
        """
        if not project_plan:
            return ""

        lines: list[str] = ["## Task Summary\n"]

        # Get tasks from plan_data
        plan_data = project_plan.plan_data or {}
        tasks = plan_data.get("tasks", [])

        if not tasks:
            return ""

        completed = 0
        failed = 0

        for task in tasks:
            task_id = task.get("id", "unknown")
            task_desc = task.get("description", "No description")
            result = task_results.get(task_id, {})
            qa = qa_results.get(task_id)

            # Determine status
            status = result.get("status", "unknown")
            if status == "success" or status == "passed":
                status_icon = "[OK]"
                completed += 1
            elif status == "failed" or status == "error":
                status_icon = "[FAIL]"
                failed += 1
            elif status == "skipped":
                status_icon = "[SKIP]"
            else:
                status_icon = "[?]"

            # Truncate description if too long
            desc_truncated = task_desc[:50] + "..." if len(task_desc) > 50 else task_desc
            lines.append(f"- {status_icon} **{task_id}**: {desc_truncated}")

            # Add QA result if available
            if qa:
                confidence_str = f"{qa.confidence:.2f}" if qa.confidence else "N/A"
                lines.append(f"  - QA: {qa.decision} (confidence: {confidence_str})")

        # Add summary statistics
        total = len(tasks)
        pending = total - completed - failed
        lines.append(
            f"\n**Total**: {completed} completed, {failed} failed"
            + (f", {pending} pending" if pending > 0 else "")
            + f" out of {total}"
        )

        return "\n".join(lines)

    async def generate_response_with_summary(
        self,
        task_id: UUID,
        original_request: str,
        project_plan: ProjectPlan | None,
        task_results: dict[str, dict[str, Any]],
        qa_results: dict[str, QAResult],
        has_artifacts: bool = False,
    ) -> str:
        """Generate final response including task summary.

        This method integrates task summary functionality for project plan
        executions. It generates a comprehensive summary of all completed
        tasks and includes it in the final response.

        Args:
            task_id: Task ID for logging
            original_request: Original user request
            project_plan: Project plan (if available)
            task_results: Results from all tasks, keyed by task ID
            qa_results: QA results for all tasks, keyed by task ID
            has_artifacts: Whether artifacts were generated

        Returns:
            User-friendly response string with task summary
        """
        # Detect user's language
        user_language = detect_language(original_request)
        language_name = get_language_name(user_language)

        logger.info(
            "responder_with_summary_start",
            task_id=str(task_id),
            detected_language=user_language,
            has_artifacts=has_artifacts,
            has_project_plan=project_plan is not None,
            task_count=len(task_results),
        )

        # Generate task summary
        summary = self._generate_task_summary(
            project_plan=project_plan,
            task_results=task_results,
            qa_results=qa_results,
        )

        # Build worker output from task results for the main response
        worker_output_parts: list[str] = []
        for tid, result in task_results.items():
            if result.get("output"):
                worker_output_parts.append(f"**{tid}**: {result.get('output', '')[:500]}")

        worker_output = "\n\n".join(worker_output_parts) if worker_output_parts else ""

        # Use a fast, simple model for response generation
        model = self.router.select_model(TaskComplexity.SIMPLE)

        # Build prompt with task summary
        system_prompt = self.prompt_manager.render(
            "responder",
            ResponderPrompts.SYSTEM_PROMPT,
            language=language_name,
            has_artifacts=has_artifacts,
        )

        user_prompt = self.prompt_manager.render(
            "responder",
            ResponderPrompts.GENERATE_RESPONSE_WITH_SUMMARY,
            original_request=original_request,
            task_summary=summary,
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
            max_tokens=3000,
            api_base=model.api_base,
            api_key=model.api_key,
        )

        response = await self.llm_client.chat_completion(request, mcp_servers=[])
        final_response = response.content.strip()

        logger.info(
            "responder_with_summary_complete",
            task_id=str(task_id),
            response_length=len(final_response),
            tokens=response.usage.total_tokens,
        )

        return final_response
