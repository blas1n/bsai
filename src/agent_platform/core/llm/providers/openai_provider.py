"""
OpenAI LLM Provider Implementation
"""

import os
from typing import AsyncIterator, Optional

import structlog
import tiktoken
from openai import APIError, AsyncOpenAI, RateLimitError
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


class OpenAIProvider(LLMProvider):
    """OpenAI GPT model provider"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "gpt-4",
    ) -> None:
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            default_model: Default model to use

        Raises:
            ValueError: If no API key is provided
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key must be provided via api_key parameter or OPENAI_API_KEY environment variable"
            )

        self.client = AsyncOpenAI(api_key=self.api_key)
        self.default_model = default_model

        # Token encoding for counting
        try:
            self.encoding = tiktoken.encoding_for_model(default_model)
        except KeyError:
            # Fallback to cl100k_base encoding (used by gpt-4, gpt-3.5-turbo)
            self.encoding = tiktoken.get_encoding("cl100k_base")

        logger.info(
            "openai_provider_initialized",
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
        Generate chat completion using OpenAI API.

        Args:
            request: Chat completion request

        Returns:
            Chat completion response

        Raises:
            RateLimitError: If rate limit is exceeded
            APIError: If API error occurs
        """
        logger.info(
            "openai_chat_completion_start",
            model=request.model,
            message_count=len(request.messages),
            temperature=request.temperature,
        )

        # Convert messages to OpenAI format
        messages = [
            {"role": msg.role, "content": msg.content} for msg in request.messages
        ]

        # Build request parameters
        params = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
        }

        if request.max_tokens is not None:
            params["max_tokens"] = request.max_tokens

        # Make API call
        response = await self.client.chat.completions.create(**params)

        # Extract response data
        choice = response.choices[0]
        content = choice.message.content or ""

        # Build usage info
        usage = UsageInfo(
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
        )

        logger.info(
            "openai_chat_completion_success",
            model=response.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            finish_reason=choice.finish_reason,
        )

        return ChatResponse(
            content=content,
            role="assistant",
            usage=usage,
            model=response.model,
            finish_reason=choice.finish_reason,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((RateLimitError, APIError)),
        reraise=True,
    )
    async def stream_completion(self, request: ChatRequest) -> AsyncIterator[str]:
        """
        Stream chat completion using OpenAI API.

        Args:
            request: Chat completion request

        Yields:
            Text chunks from the completion
        """
        logger.info(
            "openai_stream_completion_start",
            model=request.model,
            message_count=len(request.messages),
        )

        # Convert messages to OpenAI format
        messages = [
            {"role": msg.role, "content": msg.content} for msg in request.messages
        ]

        # Build request parameters
        params = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "stream": True,
        }

        if request.max_tokens is not None:
            params["max_tokens"] = request.max_tokens

        # Make streaming API call
        stream = await self.client.chat.completions.create(**params)

        chunk_count = 0
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                chunk_count += 1
                yield content

        logger.info(
            "openai_stream_completion_success",
            model=request.model,
            chunk_count=chunk_count,
        )

    def get_token_count(self, text: str) -> int:
        """
        Count tokens in text using tiktoken.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        return len(self.encoding.encode(text))

    def get_model_info(self) -> ModelInfo:
        """
        Get information about the default model.

        Returns:
            Model information
        """
        # Model context windows (as of 2024)
        context_windows = {
            "gpt-4": 8192,
            "gpt-4-32k": 32768,
            "gpt-4-turbo": 128000,
            "gpt-4-turbo-preview": 128000,
            "gpt-3.5-turbo": 16385,
            "gpt-3.5-turbo-16k": 16385,
        }

        # Get context window for model (default to 8192)
        context_window = context_windows.get(self.default_model, 8192)

        return ModelInfo(
            provider="openai",
            model_name=self.default_model,
            context_window=context_window,
            supports_streaming=True,
        )
