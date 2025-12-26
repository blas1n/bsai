"""Model registry for dynamic LLM pricing.

Loads model pricing from LiteLLM API and custom models from database.
"""

from decimal import Decimal

import litellm
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.db.repository.custom_llm_model_repo import CustomLLMModelRepository

from .models import LLMModel

logger = structlog.get_logger()


class ModelRegistry:
    """Unified registry for LiteLLM and custom models."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        """Initialize model registry.

        Args:
            session: Optional database session for loading custom models
        """
        self._litellm_models: dict[str, LLMModel] = {}
        self._custom_models: dict[str, LLMModel] = {}
        self.session = session

    async def initialize(self) -> None:
        """Load models from database.

        This should be called once during application startup.
        """
        # Load custom models from DB if session provided
        if self.session:
            await self._load_custom_models()

        logger.info(
            "model_registry_initialized",
            custom_count=len(self._custom_models),
        )

    def load_from_litellm(self, model_name: str) -> LLMModel:
        """Load a model from LiteLLM API on-demand.

        Args:
            model_name: Model name to load

        Returns:
            LLM model with pricing from LiteLLM

        Raises:
            ValueError: If model cannot be loaded from LiteLLM
        """
        # Check cache first
        if model_name in self._litellm_models:
            return self._litellm_models[model_name]

        try:
            info = litellm.get_model_info(model_name)

            # Type checking for litellm response
            context_window_raw = info.get("max_input_tokens", 4096)
            context_window: int = context_window_raw if context_window_raw is not None else 4096

            supports_streaming: bool = bool(info.get("supports_streaming", True))

            model = LLMModel(
                name=model_name,
                provider=str(info["litellm_provider"]),
                input_price_per_1k=Decimal(str(info["input_cost_per_token"] * 1000)),
                output_price_per_1k=Decimal(str(info["output_cost_per_token"] * 1000)),
                context_window=context_window,
                supports_streaming=supports_streaming,
            )

            # Cache for future use
            self._litellm_models[model_name] = model

            logger.debug(
                "litellm_model_loaded",
                model=model_name,
                provider=info["litellm_provider"],
                input_price=model.input_price_per_1k,
            )

            return model

        except Exception as e:
            raise ValueError(f"Failed to load model '{model_name}' from LiteLLM: {e}") from e

    async def _load_custom_models(self) -> None:
        """Load user-defined models from custom_llm_models table."""
        if self.session is None:
            return

        repo = CustomLLMModelRepository(self.session)
        custom_models = await repo.get_all_active()

        for db_model in custom_models:
            self._custom_models[db_model.name] = LLMModel(
                name=db_model.name,
                provider=db_model.provider,
                input_price_per_1k=db_model.input_price_per_1k,
                output_price_per_1k=db_model.output_price_per_1k,
                context_window=db_model.context_window,
                supports_streaming=db_model.supports_streaming,
                api_base=db_model.api_base,
                api_key=db_model.api_key,
            )

            logger.debug(
                "custom_model_loaded",
                model=db_model.name,
                provider=db_model.provider,
                api_base=db_model.api_base,
            )

    def get(self, model_name: str) -> LLMModel | None:
        """Get model by name.

        Args:
            model_name: Model name to retrieve

        Returns:
            LLM model if found, None otherwise

        Note:
            Custom models take precedence. If not found in custom or cache,
            attempts to load from LiteLLM on-demand.
        """
        # Check custom models first
        if model_name in self._custom_models:
            return self._custom_models[model_name]

        # Check LiteLLM cache
        if model_name in self._litellm_models:
            return self._litellm_models[model_name]

        # Try to load from LiteLLM on-demand
        try:
            return self.load_from_litellm(model_name)
        except ValueError:
            # Model not available in LiteLLM
            return None

    def get_all(self) -> dict[str, LLMModel]:
        """Get all available models.

        Returns:
            Dictionary of all models (custom + LiteLLM)
        """
        return {**self._litellm_models, **self._custom_models}

    async def add_custom_model(
        self,
        name: str,
        provider: str,
        input_price_per_1k: Decimal,
        output_price_per_1k: Decimal,
        context_window: int,
        supports_streaming: bool = True,
        api_base: str | None = None,
        api_key: str | None = None,
    ) -> None:
        """Add custom model and persist to database.

        Args:
            name: Model name
            provider: Provider name (e.g., "openai", "anthropic", "custom")
            input_price_per_1k: Input token price per 1000 tokens (USD)
            output_price_per_1k: Output token price per 1000 tokens (USD)
            context_window: Maximum context window size
            supports_streaming: Whether model supports streaming
            api_base: Optional custom API base URL (for self-hosted models)
            api_key: Optional custom API key (for self-hosted models)

        Raises:
            ValueError: If session is not provided
        """
        if self.session is None:
            raise ValueError("Cannot add custom model without database session")

        # Create model instance
        model = LLMModel(
            name=name,
            provider=provider,
            input_price_per_1k=input_price_per_1k,
            output_price_per_1k=output_price_per_1k,
            context_window=context_window,
            supports_streaming=supports_streaming,
            api_base=api_base,
            api_key=api_key,
        )

        # Add to in-memory registry
        self._custom_models[name] = model

        # Persist to database
        repo = CustomLLMModelRepository(self.session)
        await repo.create(
            name=name,
            provider=provider,
            input_price_per_1k=input_price_per_1k,
            output_price_per_1k=output_price_per_1k,
            context_window=context_window,
            supports_streaming=supports_streaming,
            api_base=api_base,
            api_key=api_key,
        )

        logger.info(
            "custom_model_added",
            model=name,
            provider=provider,
            input_price=input_price_per_1k,
            api_base=api_base,
        )

    async def remove_custom_model(self, name: str) -> bool:
        """Remove custom model from registry and database.

        Args:
            name: Model name to remove

        Returns:
            True if model was removed, False if not found

        Raises:
            ValueError: If session is not provided
        """
        if self.session is None:
            raise ValueError("Cannot remove custom model without database session")

        # Remove from in-memory registry
        if name not in self._custom_models:
            return False

        del self._custom_models[name]

        # Remove from database
        repo = CustomLLMModelRepository(self.session)
        db_model = await repo.get_by_name(name)
        if db_model:
            await repo.delete(db_model.id)

        logger.info("custom_model_removed", model=name)
        return True
