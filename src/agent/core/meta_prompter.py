"""Meta Prompter Agent for optimized prompt generation.

The Meta Prompter is responsible for:
1. Analyzing milestone requirements
2. Generating task-specific optimized prompts
3. Applying prompt engineering strategies
4. Persisting prompts for tracking and reuse
"""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.config import get_agent_settings
from agent.db.models.enums import TaskComplexity
from agent.db.repository.generated_prompt_repo import GeneratedPromptRepository
from agent.llm import ChatMessage, LiteLLMClient, LLMRequest, LLMRouter
from agent.prompts import MetaPrompterPrompts, PromptManager

logger = structlog.get_logger()


class MetaPrompterAgent:
    """Meta Prompter agent for generating optimized prompts.

    Uses a medium-complexity LLM to generate high-quality prompts
    for Worker agents, applying prompt engineering best practices.
    """

    def __init__(
        self,
        llm_client: LiteLLMClient,
        router: LLMRouter,
        prompt_manager: PromptManager,
        session: AsyncSession,
    ) -> None:
        """Initialize Meta Prompter agent.

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
        self.prompt_repo = GeneratedPromptRepository(session)

    async def generate_prompt(
        self,
        milestone_id: UUID,
        milestone_description: str,
        milestone_complexity: TaskComplexity,
        acceptance_criteria: str,
        context: str | None = None,
    ) -> str:
        """Generate optimized prompt for Worker agent.

        Args:
            milestone_id: Milestone ID for tracking
            milestone_description: What the Worker needs to accomplish
            milestone_complexity: Complexity level of the milestone
            acceptance_criteria: Success criteria
            context: Optional additional context

        Returns:
            Generated prompt for Worker

        Raises:
            ValueError: If LLM response is invalid
        """
        logger.info(
            "meta_prompter_start",
            milestone_id=str(milestone_id),
            complexity=milestone_complexity.name,
        )

        # Use MODERATE complexity for Meta Prompter (medium LLM)
        model = self.router.select_model(TaskComplexity.MODERATE)

        # Build meta prompt
        meta_prompt = self._build_meta_prompt(
            milestone_description,
            milestone_complexity,
            acceptance_criteria,
            context,
        )
        messages = [ChatMessage(role="user", content=meta_prompt)]

        # Call LLM
        settings = get_agent_settings()
        request = LLMRequest(
            model=model.name,
            messages=messages,
            temperature=settings.meta_prompter_temperature,
            api_base=model.api_base,
            api_key=model.api_key,
        )

        response = await self.llm_client.chat_completion(request, mcp_servers=[])
        generated_prompt = response.content.strip()

        # Persist to database
        await self._persist_prompt(
            milestone_id=milestone_id,
            generated_prompt=generated_prompt,
            strategy_used=self._get_strategy_name(milestone_complexity),
            model_used=model.name,
            token_count=response.usage.total_tokens,
        )

        logger.info(
            "meta_prompter_complete",
            milestone_id=str(milestone_id),
            prompt_length=len(generated_prompt),
            tokens=response.usage.total_tokens,
        )

        return generated_prompt

    def _build_meta_prompt(
        self,
        milestone_description: str,
        complexity: TaskComplexity,
        acceptance_criteria: str,
        context: str | None,
    ) -> str:
        """Build meta prompt for prompt generation.

        Args:
            milestone_description: Target milestone description
            complexity: Complexity level
            acceptance_criteria: Success criteria
            context: Optional context

        Returns:
            Meta prompt for LLM
        """
        # Get strategy from YAML
        strategies = self.prompt_manager.get_data("meta_prompter", MetaPrompterPrompts.STRATEGIES)
        strategy = strategies.get(complexity.name, strategies["MODERATE"])

        return self.prompt_manager.render(
            "meta_prompter",
            MetaPrompterPrompts.META_PROMPT,
            milestone_description=milestone_description,
            complexity=complexity.name,
            acceptance_criteria=acceptance_criteria,
            additional_context=context or "",
            strategy=strategy.strip(),
        )

    def _get_strategy_name(self, complexity: TaskComplexity) -> str:
        """Get strategy name for database storage.

        Args:
            complexity: Task complexity level

        Returns:
            Strategy name
        """
        strategy_names = {
            TaskComplexity.TRIVIAL: "direct",
            TaskComplexity.SIMPLE: "basic-decomposition",
            TaskComplexity.MODERATE: "chain-of-thought",
            TaskComplexity.COMPLEX: "tree-of-thought",
            TaskComplexity.CONTEXT_HEAVY: "structured-analysis",
        }

        return strategy_names.get(complexity, "chain-of-thought")

    async def _persist_prompt(
        self,
        milestone_id: UUID,
        generated_prompt: str,
        strategy_used: str,
        model_used: str,
        token_count: int,
    ) -> None:
        """Persist generated prompt to database.

        Args:
            milestone_id: Associated milestone ID
            generated_prompt: The generated prompt text
            strategy_used: Prompt strategy applied
            model_used: Model used for generation
            token_count: Total tokens used
        """
        await self.prompt_repo.create(
            milestone_id=milestone_id,
            generated_content=generated_prompt,
            strategy_used=strategy_used,
            model_used=model_used,
            token_count=token_count,
        )

        logger.debug(
            "prompt_persisted",
            milestone_id=str(milestone_id),
            strategy=strategy_used,
        )

    async def should_use_meta_prompter(
        self,
        complexity: TaskComplexity,
    ) -> bool:
        """Determine if Meta Prompter should be used for given complexity.

        Meta Prompter is only beneficial for MODERATE or higher complexity
        tasks where prompt optimization provides significant value.

        Args:
            complexity: Task complexity level

        Returns:
            True if Meta Prompter should be used
        """
        return complexity.value >= TaskComplexity.MODERATE.value
