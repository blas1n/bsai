"""Worker Agent for task execution.

The Worker is responsible for:
1. Executing actual tasks based on prompts
2. Using dynamically selected LLM based on complexity
3. Generating output based on acceptance criteria
4. Tracking execution metadata
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.config import get_agent_settings
from agent.api.websocket.manager import ConnectionManager
from agent.db.models.enums import MilestoneStatus, TaskComplexity
from agent.db.models.mcp_server_config import McpServerConfig
from agent.db.repository.mcp_server_repo import McpServerRepository
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.llm import ChatMessage, LiteLLMClient, LLMRequest, LLMResponse, LLMRouter
from agent.llm.schemas import WorkerOutput
from agent.mcp.executor import McpToolExecutor
from agent.mcp.utils import load_user_mcp_servers
from agent.prompts import PromptManager, WorkerPrompts

logger = structlog.get_logger()


class WorkerAgent:
    """Worker agent for executing milestones.

    Uses dynamically selected LLM based on milestone complexity,
    optimizing for both cost and quality.
    """

    def __init__(
        self,
        llm_client: LiteLLMClient,
        router: LLMRouter,
        prompt_manager: PromptManager,
        session: AsyncSession,
        ws_manager: ConnectionManager | None = None,
    ) -> None:
        """Initialize Worker agent.

        Args:
            llm_client: LLM client for API calls
            router: Router for model selection
            prompt_manager: Prompt manager for template rendering
            session: Database session
            ws_manager: Optional WebSocket manager for MCP stdio tools
        """
        self.llm_client = llm_client
        self.router = router
        self.prompt_manager = prompt_manager
        self.session = session
        self.milestone_repo = MilestoneRepository(session)
        self.mcp_server_repo = McpServerRepository(session)
        self.ws_manager = ws_manager

    async def execute_milestone(
        self,
        milestone_id: UUID,
        prompt: str,
        complexity: TaskComplexity,
        user_id: str,
        session_id: UUID,
        preferred_model: str | None = None,
        context_messages: list[ChatMessage] | None = None,
        mcp_enabled: bool = True,
    ) -> LLMResponse:
        """Execute a milestone using the provided prompt.

        Args:
            milestone_id: Milestone ID being executed
            prompt: Execution prompt (from Meta Prompter or direct)
            complexity: Milestone complexity level
            user_id: User ID for MCP tool ownership
            session_id: Session ID for MCP tool logging
            preferred_model: Optional user-preferred model override
            context_messages: Optional conversation history for context
            mcp_enabled: Enable MCP tool calling (default: True)

        Returns:
            LLM response with execution result

        Raises:
            ValueError: If model selection fails
        """
        logger.info(
            "worker_execution_start",
            milestone_id=str(milestone_id),
            complexity=complexity.name,
            prompt_length=len(prompt),
            mcp_enabled=mcp_enabled,
        )

        # Update milestone status to in_progress
        milestone = await self.milestone_repo.get_by_id(milestone_id)
        if milestone:
            await self.milestone_repo.update(
                milestone_id,
                status=MilestoneStatus.IN_PROGRESS.value,
            )

        # Select model based on complexity
        model = self.router.select_model(
            complexity=complexity,
            preferred_model=preferred_model,
        )

        # Get system prompt for output format guidelines
        system_prompt = self.prompt_manager.render("worker", WorkerPrompts.SYSTEM_PROMPT)

        # Build messages list with system prompt
        messages = []
        messages.append(ChatMessage(role="system", content=system_prompt))
        if context_messages:
            messages.extend(context_messages)
        messages.append(ChatMessage(role="user", content=prompt))

        # Load MCP servers if enabled
        mcp_servers: list[McpServerConfig] = []
        tool_executor: McpToolExecutor | None = None

        if mcp_enabled:
            mcp_servers = await load_user_mcp_servers(
                mcp_server_repo=self.mcp_server_repo,
                user_id=user_id,
                agent_type="worker",
            )

            if mcp_servers:
                tool_executor = McpToolExecutor(
                    user_id=user_id,
                    session_id=session_id,
                    ws_manager=self.ws_manager,
                )
                # Register executor in ConnectionManager for WebSocket access
                if self.ws_manager:
                    self.ws_manager.register_mcp_executor(session_id, tool_executor)
                logger.info(
                    "worker_mcp_enabled",
                    milestone_id=str(milestone_id),
                    mcp_server_count=len(mcp_servers),
                )

        settings = get_agent_settings()
        request = LLMRequest(
            model=model.name,
            messages=messages,
            temperature=settings.worker_temperature,
            max_tokens=settings.worker_max_tokens,
            api_base=model.api_base,
            api_key=model.api_key,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "worker_output",
                    "strict": True,
                    "schema": WorkerOutput.model_json_schema(),
                },
            },
        )

        # TODO: Refactor to use stream_completion for real-time Live Output in frontend
        # Currently uses non-streaming chat_completion, so no LLM_CHUNK WebSocket events
        # are generated. To enable Live Output streaming:
        # 1. Use self.llm_client.stream_completion() instead
        # 2. Broadcast LLM_CHUNK events via ws_manager during streaming
        # 3. Accumulate chunks and return final response
        # See: web/src/components/monitoring/LiveDetailPanel.tsx (Live Output section)
        response = await self.llm_client.chat_completion(
            request=request,
            mcp_servers=mcp_servers,
            tool_executor=tool_executor,
        )

        # Calculate cost
        cost = self.router.calculate_cost(
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        logger.info(
            "worker_execution_complete",
            milestone_id=str(milestone_id),
            model=model.name,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_usd=float(cost),
        )

        return response

    async def retry_with_feedback(
        self,
        milestone_id: UUID,
        original_prompt: str,
        previous_output: str,
        qa_feedback: str,
        complexity: TaskComplexity,
        user_id: str,
        session_id: UUID,
    ) -> LLMResponse:
        """Retry milestone execution with QA feedback.

        Args:
            milestone_id: Milestone ID being retried
            original_prompt: Original execution prompt
            previous_output: Previous attempt output
            qa_feedback: Feedback from QA Agent
            complexity: Milestone complexity
            user_id: User ID for MCP tool ownership
            session_id: Session ID for MCP tool logging

        Returns:
            LLM response from retry attempt
        """
        logger.info(
            "worker_retry_start",
            milestone_id=str(milestone_id),
            feedback_length=len(qa_feedback),
        )

        # Build retry prompt with feedback
        retry_prompt = self.prompt_manager.render(
            "worker",
            WorkerPrompts.RETRY_PROMPT,
            previous_output=previous_output,
            qa_feedback=qa_feedback,
            original_prompt=original_prompt,
        )

        # Execute retry (reuse execute_milestone logic)
        response = await self.execute_milestone(
            milestone_id=milestone_id,
            prompt=retry_prompt,
            complexity=complexity,
            user_id=user_id,
            session_id=session_id,
        )

        logger.info(
            "worker_retry_complete",
            milestone_id=str(milestone_id),
        )

        return response
