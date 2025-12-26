"""LiteLLM client wrapper.

Async wrapper around LiteLLM with error handling and retries.
"""

from collections.abc import AsyncIterator

import litellm
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .schemas import LLMRequest, LLMResponse, UsageInfo

logger = structlog.get_logger()


class LiteLLMClient:
    """Async LiteLLM client with automatic retry logic."""

    def __init__(self) -> None:
        """Initialize LiteLLM client.

        LiteLLM uses API keys from environment variables:
        - OPENAI_API_KEY
        - ANTHROPIC_API_KEY
        - GOOGLE_API_KEY
        """
        pass

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def chat_completion(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        """Call LLM with automatic retry (3 attempts).

        Args:
            request: LLM completion request

        Returns:
            LLM completion response

        Raises:
            Exception: If all retry attempts fail
        """
        logger.info(
            "llm_chat_completion_start",
            model=request.model,
            message_count=len(request.messages),
            temperature=request.temperature,
        )

        # Convert Pydantic messages to dict format
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

        # Build request parameters
        params: dict[str, object] = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
        }

        if request.max_tokens is not None:
            params["max_tokens"] = request.max_tokens

        if request.api_base is not None:
            params["api_base"] = request.api_base

        if request.api_key is not None:
            params["api_key"] = request.api_key

        # Make API call through LiteLLM
        response = await litellm.acompletion(**params)

        # Extract response data
        choice = response["choices"][0]
        content = choice["message"]["content"]
        finish_reason = choice.get("finish_reason")

        # Build usage info
        usage = UsageInfo(
            input_tokens=response["usage"]["prompt_tokens"],
            output_tokens=response["usage"]["completion_tokens"],
            total_tokens=response["usage"]["total_tokens"],
        )

        logger.info(
            "llm_chat_completion_success",
            model=response["model"],
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            finish_reason=finish_reason,
        )

        return LLMResponse(
            content=content,
            usage=usage,
            model=response["model"],
            finish_reason=finish_reason,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def stream_completion(
        self,
        request: LLMRequest,
    ) -> AsyncIterator[str]:
        """Stream LLM response for real-time output.

        Args:
            request: LLM completion request

        Yields:
            Text chunks from the completion

        Raises:
            Exception: If all retry attempts fail
        """
        logger.info(
            "llm_stream_completion_start",
            model=request.model,
            message_count=len(request.messages),
        )

        # Convert Pydantic messages to dict format
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

        # Build request parameters
        params: dict[str, object] = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "stream": True,
        }

        if request.max_tokens is not None:
            params["max_tokens"] = request.max_tokens

        if request.api_base is not None:
            params["api_base"] = request.api_base

        if request.api_key is not None:
            params["api_key"] = request.api_key

        # Make streaming API call through LiteLLM
        stream = await litellm.acompletion(**params)

        chunk_count = 0
        async for chunk in stream:
            if chunk["choices"] and chunk["choices"][0].get("delta", {}).get("content"):
                content = chunk["choices"][0]["delta"]["content"]
                chunk_count += 1
                yield content

        logger.info(
            "llm_stream_completion_success",
            model=request.model,
            chunk_count=chunk_count,
        )
