"""
Anthropic LLM Provider Implementation
"""

import os
from typing import AsyncIterator, Optional

import structlog
from anthropic import APIError, AsyncAnthropic, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agent_platform.core.llm.base import (
    ChatRequest,
    ChatResponse,
    LLMProvider,
    ModelInfo,
    UsageInfo,
)


logger = structlog.get_logger()


class AnthropicProvider(LLMProvider):
    """Anthropic Claude model provider"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "claude-3-opus-20240229",
    ) -> None:
        """
        Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            default_model: Default model to use

        Raises:
            ValueError: If no API key is provided
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Anthropic API key must be provided via api_key parameter or ANTHROPIC_API_KEY environment variable"
            )

        self.client = AsyncAnthropic(api_key=self.api_key)
        self.default_model = default_model

        logger.info(
            "anthropic_provider_initialized",
            default_model=default_model,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((RateLimitError, APIError)),
        reraise=True,
    )
    async def chat_completion(self, request: ChatRequest) -> ChatResponse:
        """
        Generate chat completion using Anthropic API.

        Args:
            request: Chat completion request

        Returns:
            Chat completion response

        Raises:
            RateLimitError: If rate limit is exceeded
            APIError: If API error occurs
        """
        logger.info(
            "anthropic_chat_completion_start",
            model=request.model,
            message_count=len(request.messages),
            temperature=request.temperature,
        )

        # Separate system message from other messages
        system_message = None
        messages = []

        for msg in request.messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                messages.append({"role": msg.role, "content": msg.content})

        # Build request parameters
        params = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens or 4096,  # Anthropic requires max_tokens
        }

        if system_message:
            params["system"] = system_message

        # Make API call
        response = await self.client.messages.create(**params)

        # Extract response data
        content = response.content[0].text if response.content else ""

        # Build usage info
        usage = UsageInfo(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
        )

        logger.info(
            "anthropic_chat_completion_success",
            model=response.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            stop_reason=response.stop_reason,
        )

        return ChatResponse(
            content=content,
            role="assistant",
            usage=usage,
            model=response.model,
            finish_reason=response.stop_reason or "unknown",
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((RateLimitError, APIError)),
        reraise=True,
    )
    async def stream_completion(self, request: ChatRequest) -> AsyncIterator[str]:
        """
        Stream chat completion using Anthropic API.

        Args:
            request: Chat completion request

        Yields:
            Text chunks from the completion
        """
        logger.info(
            "anthropic_stream_completion_start",
            model=request.model,
            message_count=len(request.messages),
        )

        # Separate system message from other messages
        system_message = None
        messages = []

        for msg in request.messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                messages.append({"role": msg.role, "content": msg.content})

        # Build request parameters
        params = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens or 4096,
        }

        if system_message:
            params["system"] = system_message

        # Make streaming API call
        chunk_count = 0
        async with self.client.messages.stream(**params) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        chunk_count += 1
                        yield event.delta.text

        logger.info(
            "anthropic_stream_completion_success",
            model=request.model,
            chunk_count=chunk_count,
        )

    def get_token_count(self, text: str) -> int:
        """
        Count tokens in text using Anthropic's count_tokens API.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        # Use Anthropic's count_tokens method
        return self.client.messages.count_tokens(
            messages=[{"role": "user", "content": text}],
            model=self.default_model,
        )

    def get_model_info(self) -> ModelInfo:
        """
        Get information about the default model.

        Returns:
            Model information
        """
        # Model context windows (as of 2024)
        context_windows = {
            "claude-3-opus-20240229": 200000,
            "claude-3-sonnet-20240229": 200000,
            "claude-3-haiku-20240307": 200000,
            "claude-2.1": 200000,
            "claude-2.0": 100000,
        }

        # Get context window for model (default to 200000)
        context_window = context_windows.get(self.default_model, 200000)

        return ModelInfo(
            provider="anthropic",
            model_name=self.default_model,
            context_window=context_window,
            supports_streaming=True,
        )
