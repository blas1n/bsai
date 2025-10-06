"""
LiteLLM Fallback Provider Implementation

LiteLLM is a unified interface to 100+ LLMs, providing a fallback
option when specific providers are not available or to access
models not directly supported.
"""

from typing import AsyncIterator, Optional

import structlog
import tiktoken
from litellm import acompletion
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


class LiteLLMProvider(LLMProvider):
    """
    LiteLLM fallback provider for multi-vendor support.

    This provider uses LiteLLM to support 100+ LLM models from various
    providers including OpenAI, Anthropic, Google, Cohere, Replicate, etc.
    """

    def __init__(
        self,
        default_model: str = "gpt-3.5-turbo",
    ) -> None:
        """
        Initialize LiteLLM provider.

        Args:
            default_model: Default model to use (can be any LiteLLM-supported model)
        """
        self.default_model = default_model

        # Token encoding for counting (using OpenAI's as fallback)
        try:
            self.encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
        except KeyError:
            self.encoding = tiktoken.get_encoding("cl100k_base")

        logger.info(
            "litellm_provider_initialized",
            default_model=default_model,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def chat_completion(self, request: ChatRequest) -> ChatResponse:
        """
        Generate chat completion using LiteLLM.

        Args:
            request: Chat completion request

        Returns:
            Chat completion response

        Raises:
            Exception: If API error occurs
        """
        logger.info(
            "litellm_chat_completion_start",
            model=request.model,
            message_count=len(request.messages),
            temperature=request.temperature,
        )

        # Convert messages to LiteLLM format
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

        # Make API call through LiteLLM
        response = await acompletion(**params)

        # Extract response data
        choice = response["choices"][0]
        content = choice["message"]["content"]

        # Build usage info
        usage = UsageInfo(
            input_tokens=response["usage"]["prompt_tokens"],
            output_tokens=response["usage"]["completion_tokens"],
            total_tokens=response["usage"]["total_tokens"],
        )

        logger.info(
            "litellm_chat_completion_success",
            model=response["model"],
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            finish_reason=choice["finish_reason"],
        )

        return ChatResponse(
            content=content,
            role="assistant",
            usage=usage,
            model=response["model"],
            finish_reason=choice["finish_reason"],
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def stream_completion(self, request: ChatRequest) -> AsyncIterator[str]:
        """
        Stream chat completion using LiteLLM.

        Args:
            request: Chat completion request

        Yields:
            Text chunks from the completion
        """
        logger.info(
            "litellm_stream_completion_start",
            model=request.model,
            message_count=len(request.messages),
        )

        # Convert messages to LiteLLM format
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

        # Make streaming API call through LiteLLM
        stream = await acompletion(**params)

        chunk_count = 0
        async for chunk in stream:
            if chunk["choices"] and chunk["choices"][0].get("delta", {}).get("content"):
                content = chunk["choices"][0]["delta"]["content"]
                chunk_count += 1
                yield content

        logger.info(
            "litellm_stream_completion_success",
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
        # LiteLLM supports many models, context windows vary
        # Return conservative defaults
        return ModelInfo(
            provider="litellm",
            model_name="litellm-fallback",
            context_window=8192,  # Conservative default
            supports_streaming=True,
        )
