"""LiteLLM client wrapper.

Async wrapper around LiteLLM with error handling and retries.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, cast

import litellm
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agent.mcp.executor import McpToolCall

from .schemas import LLMRequest, LLMResponse, UsageInfo

if TYPE_CHECKING:
    from agent.db.models.mcp_server_config import McpServerConfig
    from agent.mcp.executor import McpToolExecutor

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
        mcp_servers: list[McpServerConfig],
        tool_executor: McpToolExecutor | None = None,
        max_tool_iterations: int = 5,
    ) -> LLMResponse:
        """Call LLM with automatic retry (3 attempts).

        Supports both regular completion and tool calling via MCP servers.

        Args:
            request: LLM completion request
            mcp_servers: MCP servers for tool calling (pass empty list if none)
            tool_executor: Optional MCP tool executor for handling tool calls
            max_tool_iterations: Maximum tool calling iterations (default: 5)

        Returns:
            LLM completion response

        Raises:
            Exception: If all retry attempts fail
        """
        use_tools = len(mcp_servers) > 0 and tool_executor is not None
        logger.info(
            "llm_chat_completion_start",
            model=request.model,
            message_count=len(request.messages),
            temperature=request.temperature,
            use_tools=use_tools,
            mcp_server_count=len(mcp_servers),
        )

        # Convert Pydantic messages to dict format
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

        # Build request parameters
        params: dict[str, Any] = {
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

        if request.response_format:
            params["response_format"] = request.response_format

        # Add tools if MCP servers provided
        if use_tools:
            tools = self._build_tools_from_mcp_servers(mcp_servers)
            if tools:
                params["tools"] = tools
            else:
                # No tools available, disable tool mode
                use_tools = False
                logger.warning("llm_no_tools_available")

        # Execute with unified completion logic
        return await self._execute_completion(
            params=params,
            request=request,
            mcp_servers=mcp_servers,
            tool_executor=tool_executor if use_tools else None,
            max_iterations=max_tool_iterations if use_tools else 1,
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
        params: dict[str, Any] = {
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
        stream = cast(Any, await litellm.acompletion(**params))

        chunk_count = 0
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                chunk_count += 1
                yield content

        logger.info(
            "llm_stream_completion_success",
            model=request.model,
            chunk_count=chunk_count,
        )

    async def _execute_completion(
        self,
        params: dict[str, Any],
        request: LLMRequest,
        mcp_servers: list[McpServerConfig],
        tool_executor: McpToolExecutor | None,
        max_iterations: int,
    ) -> LLMResponse:
        """Execute LLM completion with optional tool calling loop.

        Unified method that handles both simple and tool-calling completions.

        Args:
            params: Pre-built request parameters (with or without tools)
            request: Original LLM request
            mcp_servers: List of enabled MCP servers for tool calling (empty if none)
            tool_executor: Optional MCP tool executor for handling tool calls
            max_iterations: Maximum iterations (1 for simple, 5 for tool mode)

        Returns:
            LLM completion response
        """
        # Completion loop (1 iteration for simple, multiple for tools)
        iteration = 0
        total_input_tokens = 0
        total_output_tokens = 0
        use_tools = len(mcp_servers) > 0 and tool_executor is not None

        while iteration < max_iterations:
            iteration += 1

            if use_tools:
                logger.info(
                    "llm_tool_calling_iteration",
                    iteration=iteration,
                    message_count=len(params["messages"]),
                )

            # Make API call through LiteLLM
            response = cast(Any, await litellm.acompletion(**params))

            # Extract response data
            choice = response.choices[0]
            finish_reason: str | None = choice.finish_reason

            # Accumulate usage
            response_usage = response.usage
            total_input_tokens += response_usage.prompt_tokens
            total_output_tokens += response_usage.completion_tokens

            # Check if tool calls present (only in tool mode)
            tool_calls = getattr(choice.message, "tool_calls", None) if use_tools else None

            if not tool_calls or finish_reason == "stop":
                # No more tool calls (or simple mode), return final response
                content: str = choice.message.content or ""
                model_name: str = response.model or request.model

                usage = UsageInfo(
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    total_tokens=total_input_tokens + total_output_tokens,
                )

                logger.info(
                    "llm_chat_completion_success",
                    model=model_name,
                    iterations=iteration,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    finish_reason=finish_reason,
                    tool_mode=use_tools,
                )

                return LLMResponse(
                    content=content,
                    usage=usage,
                    model=model_name,
                    finish_reason=finish_reason,
                )

            # Execute tool calls (only reaches here in tool mode with tool_calls)
            if not tool_executor:
                # Should never happen (use_tools guarantees tool_executor), but for type safety
                logger.error("llm_tool_executor_missing")
                break

            logger.info(
                "llm_executing_tool_calls",
                tool_call_count=len(tool_calls),
                iteration=iteration,
            )

            # Append assistant message with tool calls to history
            params["messages"].append(
                {
                    "role": "assistant",
                    "content": choice.message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )

            # Execute each tool call
            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                try:
                    tool_input = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    tool_input = {}

                # Find MCP server for this tool
                mcp_server = self._find_mcp_server_for_tool(mcp_servers, tool_name)

                if not mcp_server:
                    logger.warning(
                        "llm_tool_server_not_found",
                        tool_name=tool_name,
                    )
                    # Add error result
                    params["messages"].append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(
                                {"error": f"MCP server not found for tool: {tool_name}"}
                            ),
                        }
                    )
                    continue

                # Execute tool
                mcp_tool_call = McpToolCall(
                    tool_name=tool_name,
                    tool_input=tool_input,
                    mcp_server=mcp_server,
                )

                result = await tool_executor.execute_tool(mcp_tool_call)

                # Add tool result to messages
                if result.success:
                    tool_content = json.dumps(result.output or {})
                else:
                    tool_content = json.dumps({"error": result.error or "Unknown error"})

                params["messages"].append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_content,
                    }
                )

                logger.info(
                    "llm_tool_executed",
                    tool_name=tool_name,
                    success=result.success,
                    execution_time_ms=result.execution_time_ms,
                )

        # Max iterations reached (only possible in tool mode)
        logger.warning(
            "llm_chat_completion_max_iterations",
            max_iterations=max_iterations,
        )

        # Return last response even if max iterations reached
        content = params["messages"][-1].get("content", "")
        usage = UsageInfo(
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            total_tokens=total_input_tokens + total_output_tokens,
        )

        return LLMResponse(
            content=str(content),
            usage=usage,
            model=request.model,
            finish_reason="max_iterations",
        )

    def _build_tools_from_mcp_servers(
        self,
        mcp_servers: list[McpServerConfig],
    ) -> list[dict[str, Any]]:
        """Build LiteLLM tools array from MCP server configurations.

        Args:
            mcp_servers: List of MCP server configurations

        Returns:
            List of tool definitions for LiteLLM
        """
        tools = []

        for server in mcp_servers:
            if not server.available_tools:
                continue

            # Add each tool from the server
            for tool in server.available_tools:
                # LiteLLM expects tools in OpenAI function calling format
                tool_def = {
                    "type": "function",
                    "function": {
                        "name": tool.get("name"),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("inputSchema", {}),
                    },
                }
                tools.append(tool_def)

                logger.debug(
                    "llm_tool_registered",
                    tool_name=tool.get("name"),
                    server_name=server.name,
                    transport=server.transport_type,
                )

        logger.info(
            "llm_tools_built",
            tool_count=len(tools),
            server_count=len(mcp_servers),
        )

        return tools

    def _find_mcp_server_for_tool(
        self,
        mcp_servers: list[McpServerConfig],
        tool_name: str,
    ) -> McpServerConfig | None:
        """Find MCP server that provides a specific tool.

        Args:
            mcp_servers: List of MCP server configurations
            tool_name: Name of the tool to find

        Returns:
            MCP server config if found, None otherwise
        """
        for server in mcp_servers:
            if not server.available_tools:
                continue

            for tool in server.available_tools:
                if tool.get("name") == tool_name:
                    return server

        return None
