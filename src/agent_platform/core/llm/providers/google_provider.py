"""
Google Gemini LLM Provider Implementation
"""

import os
from typing import AsyncIterator, Optional

import google.generativeai as genai
import structlog
from google.api_core.exceptions import GoogleAPIError, ResourceExhausted
from google.generativeai import GenerativeModel
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


class GoogleProvider(LLMProvider):
    """Google Gemini model provider"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "gemini-pro",
    ) -> None:
        """
        Initialize Google Gemini provider.

        Args:
            api_key: Google API key (defaults to GOOGLE_API_KEY env var)
            default_model: Default model to use

        Raises:
            ValueError: If no API key is provided
        """
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Google API key must be provided via api_key parameter or GOOGLE_API_KEY environment variable"
            )

        # Configure the API
        genai.configure(api_key=self.api_key)

        self.default_model = default_model
        self.model = GenerativeModel(default_model)

        logger.info(
            "google_provider_initialized",
            default_model=default_model,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ResourceExhausted, GoogleAPIError)),
        reraise=True,
    )
    async def chat_completion(self, request: ChatRequest) -> ChatResponse:
        """
        Generate chat completion using Google Gemini API.

        Args:
            request: Chat completion request

        Returns:
            Chat completion response

        Raises:
            ResourceExhausted: If rate limit is exceeded
            GoogleAPIError: If API error occurs
        """
        logger.info(
            "google_chat_completion_start",
            model=request.model,
            message_count=len(request.messages),
            temperature=request.temperature,
        )

        # Convert messages to Gemini format
        # Gemini uses a different format - combine all messages into content
        contents = []
        for msg in request.messages:
            if msg.role == "system":
                # Prepend system message to first user message
                contents.append(f"System: {msg.content}\n")
            elif msg.role == "user":
                contents.append(f"User: {msg.content}")
            elif msg.role == "assistant":
                contents.append(f"Assistant: {msg.content}")

        combined_content = "\n".join(contents)

        # Build generation config
        generation_config = {
            "temperature": request.temperature,
        }

        if request.max_tokens:
            generation_config["max_output_tokens"] = request.max_tokens

        # Make API call
        response = await self.model.generate_content_async(
            combined_content,
            generation_config=generation_config,
        )

        # Extract response data
        content = response.text

        # Build usage info
        usage = UsageInfo(
            input_tokens=response.usage_metadata.prompt_token_count,
            output_tokens=response.usage_metadata.candidates_token_count,
            total_tokens=response.usage_metadata.total_token_count,
        )

        logger.info(
            "google_chat_completion_success",
            model=request.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )

        return ChatResponse(
            content=content,
            role="assistant",
            usage=usage,
            model=request.model,
            finish_reason="stop",
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ResourceExhausted, GoogleAPIError)),
        reraise=True,
    )
    async def stream_completion(self, request: ChatRequest) -> AsyncIterator[str]:
        """
        Stream chat completion using Google Gemini API.

        Args:
            request: Chat completion request

        Yields:
            Text chunks from the completion
        """
        logger.info(
            "google_stream_completion_start",
            model=request.model,
            message_count=len(request.messages),
        )

        # Convert messages to Gemini format
        contents = []
        for msg in request.messages:
            if msg.role == "system":
                contents.append(f"System: {msg.content}\n")
            elif msg.role == "user":
                contents.append(f"User: {msg.content}")
            elif msg.role == "assistant":
                contents.append(f"Assistant: {msg.content}")

        combined_content = "\n".join(contents)

        # Build generation config
        generation_config = {
            "temperature": request.temperature,
        }

        if request.max_tokens:
            generation_config["max_output_tokens"] = request.max_tokens

        # Make streaming API call
        response = await self.model.generate_content_async(
            combined_content,
            generation_config=generation_config,
            stream=True,
        )

        chunk_count = 0
        async for chunk in response:
            if hasattr(chunk, "text") and chunk.text:
                chunk_count += 1
                yield chunk.text

        logger.info(
            "google_stream_completion_success",
            model=request.model,
            chunk_count=chunk_count,
        )

    def get_token_count(self, text: str) -> int:
        """
        Count tokens in text using Gemini's count_tokens API.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        result = self.model.count_tokens(text)
        return result.total_tokens

    def get_model_info(self) -> ModelInfo:
        """
        Get information about the default model.

        Returns:
            Model information
        """
        # Model context windows (as of 2024)
        context_windows = {
            "gemini-pro": 32768,
            "gemini-pro-vision": 16384,
            "gemini-ultra": 32768,
            "gemini-1.5-pro": 1048576,  # 1M tokens
            "gemini-1.5-flash": 1048576,
        }

        # Get context window for model (default to 32768)
        context_window = context_windows.get(self.default_model, 32768)

        return ModelInfo(
            provider="google",
            model_name=self.default_model,
            context_window=context_window,
            supports_streaming=True,
        )
