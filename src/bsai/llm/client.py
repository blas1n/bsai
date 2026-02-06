"""LiteLLM client wrapper.

Async wrapper around LiteLLM with error handling and retries.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, cast

import litellm
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from bsai.api.config import get_agent_settings
from bsai.db.models.mcp_server_config import McpServerConfig
from bsai.llm.builtin_tools import (
    BUILTIN_TOOL_DEFINITIONS,
    BUILTIN_TOOL_NAMES,
    BuiltinToolExecutor,
)
from bsai.mcp.executor import McpToolCall, McpToolExecutor
from bsai.mcp.utils import load_tools_from_mcp_server

from .schemas import LLMRequest, LLMResponse, UsageInfo

logger = structlog.get_logger()


class LiteLLMClient:
    """Async LiteLLM client with automatic retry logic.

    LiteLLM uses API keys from environment variables:
    - OPENAI_API_KEY
    - ANTHROPIC_API_KEY
    - GOOGLE_API_KEY
    """

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
        builtin_tool_executor: BuiltinToolExecutor | None = None,
        max_tool_iterations: int | None = None,
    ) -> LLMResponse:
        """Call LLM with automatic retry (3 attempts).

        Supports both regular completion and tool calling via MCP servers.

        Args:
            request: LLM completion request
            mcp_servers: MCP servers for tool calling (pass empty list if none)
            tool_executor: Optional MCP tool executor for handling tool calls
            builtin_tool_executor: Optional executor for built-in tools (read_artifact, etc.)
            max_tool_iterations: Maximum tool calling iterations (uses settings default if None)

        Returns:
            LLM completion response

        Raises:
            Exception: If all retry attempts fail
        """
        use_mcp_tools = len(mcp_servers) > 0 and tool_executor is not None
        use_builtin_tools = builtin_tool_executor is not None
        use_tools = use_mcp_tools or use_builtin_tools
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

        # Build tools list (built-in + MCP)
        tool_to_server: dict[str, McpServerConfig] = {}
        all_tools: list[dict[str, Any]] = []

        # Add built-in tools if executor provided
        if use_builtin_tools:
            all_tools.extend(BUILTIN_TOOL_DEFINITIONS)
            logger.info(
                "llm_builtin_tools_added",
                tool_count=len(BUILTIN_TOOL_DEFINITIONS),
                tool_names=list(BUILTIN_TOOL_NAMES),
            )

        # Add MCP tools if servers provided
        if use_mcp_tools:
            mcp_tools, tool_to_server = await self._build_tools_from_mcp_servers(mcp_servers)
            all_tools.extend(mcp_tools)

        if all_tools:
            params["tools"] = all_tools
            logger.info(
                "llm_tools_added_to_params",
                tool_count=len(all_tools),
                tool_names=[t["function"]["name"] for t in all_tools],
            )
        else:
            # No tools available, disable tool mode
            use_tools = False
            if use_mcp_tools:
                logger.warning("llm_no_tools_available", mcp_server_count=len(mcp_servers))

        # Use settings default if max_tool_iterations not specified
        if max_tool_iterations is None:
            settings = get_agent_settings()
            max_tool_iterations = settings.max_tool_iterations

        # Execute with unified completion logic
        return await self._execute_completion(
            params=params,
            request=request,
            tool_to_server=tool_to_server,
            tool_executor=tool_executor if use_mcp_tools else None,
            builtin_tool_executor=builtin_tool_executor,
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
        tool_to_server: dict[str, McpServerConfig],
        tool_executor: McpToolExecutor | None,
        builtin_tool_executor: BuiltinToolExecutor | None,
        max_iterations: int,
    ) -> LLMResponse:
        """Execute LLM completion with optional tool calling loop.

        Unified method that handles both simple and tool-calling completions.

        Args:
            params: Pre-built request parameters (with or without tools)
            request: Original LLM request
            tool_to_server: Mapping from tool name to MCP server config
            tool_executor: Optional MCP tool executor for handling tool calls
            builtin_tool_executor: Optional executor for built-in tools
            max_iterations: Maximum iterations (1 for simple, 5 for tool mode)

        Returns:
            LLM completion response
        """
        # Completion loop (1 iteration for simple, multiple for tools)
        iteration = 0
        total_input_tokens = 0
        total_output_tokens = 0
        use_mcp_tools = len(tool_to_server) > 0 and tool_executor is not None
        use_builtin_tools = builtin_tool_executor is not None
        use_tools = use_mcp_tools or use_builtin_tools

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

                # Warn if response was truncated due to token limit
                if finish_reason == "length":
                    logger.warning(
                        "llm_response_truncated",
                        model=model_name,
                        content_length=len(content),
                        message="Response was cut off due to token limit",
                    )

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

                tool_content: str

                # Check if this is a built-in tool
                if tool_name in BUILTIN_TOOL_NAMES:
                    if builtin_tool_executor:
                        result = await builtin_tool_executor.execute(tool_name, tool_input)
                        tool_content = json.dumps(result)
                        logger.info(
                            "llm_builtin_tool_executed",
                            tool_name=tool_name,
                            success="error" not in result,
                        )
                    else:
                        tool_content = json.dumps(
                            {"error": f"Built-in tool executor not available: {tool_name}"}
                        )
                else:
                    # MCP tool - find server and execute
                    mcp_server = tool_to_server.get(tool_name)

                    if not mcp_server:
                        logger.warning(
                            "llm_tool_server_not_found",
                            tool_name=tool_name,
                        )
                        tool_content = json.dumps(
                            {"error": f"MCP server not found for tool: {tool_name}"}
                        )
                    elif not tool_executor:
                        tool_content = json.dumps(
                            {"error": f"MCP tool executor not available: {tool_name}"}
                        )
                    else:
                        # Execute MCP tool
                        mcp_tool_call = McpToolCall(
                            tool_name=tool_name,
                            tool_input=tool_input,
                            mcp_server=mcp_server,
                        )

                        mcp_result = await tool_executor.execute_tool(mcp_tool_call)

                        if mcp_result.success:
                            tool_content = json.dumps(mcp_result.output or {})
                        else:
                            tool_content = json.dumps(
                                {"error": mcp_result.error or "Unknown error"}
                            )

                        logger.info(
                            "llm_mcp_tool_executed",
                            tool_name=tool_name,
                            success=mcp_result.success,
                            execution_time_ms=mcp_result.execution_time_ms,
                        )

                params["messages"].append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_content,
                    }
                )

        # Max iterations reached (only possible in tool mode)
        logger.warning(
            "llm_chat_completion_max_iterations",
            max_iterations=max_iterations,
        )

        # Make one final call WITHOUT tools to force a text response
        # This ensures we get a proper structured response even after max tool iterations
        final_params = {
            "model": params["model"],
            "messages": params["messages"],
            "temperature": params.get("temperature", 0.7),
        }
        if params.get("response_format"):
            final_params["response_format"] = params["response_format"]

        logger.info("llm_final_response_after_max_iterations")
        final_response = cast(Any, await litellm.acompletion(**final_params))

        final_choice = final_response.choices[0]
        final_content: str = final_choice.message.content or ""
        final_model: str = final_response.model or request.model

        # Add final response tokens
        total_input_tokens += final_response.usage.prompt_tokens
        total_output_tokens += final_response.usage.completion_tokens

        usage = UsageInfo(
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            total_tokens=total_input_tokens + total_output_tokens,
        )

        return LLMResponse(
            content=final_content,
            usage=usage,
            model=final_model,
            finish_reason="max_iterations",
        )

    async def _build_tools_from_mcp_servers(
        self,
        mcp_servers: list[McpServerConfig],
        tool_schemas: dict[str, list[dict[str, Any]]] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, McpServerConfig]]:
        """Build LiteLLM tools array from MCP server configurations.

        Args:
            mcp_servers: List of MCP server configurations
            tool_schemas: Pre-loaded tool schemas (server_name -> tools).
                          If not provided, will load from servers directly.

        Returns:
            Tuple of (tool definitions for LiteLLM, tool_name -> server mapping)
        """
        tools = []
        tool_to_server: dict[str, McpServerConfig] = {}

        for server in mcp_servers:
            # Get tool schemas for this server
            server_tools: list[dict[str, Any]] = []

            if tool_schemas and server.name in tool_schemas:
                # Use pre-loaded schemas
                server_tools = tool_schemas[server.name]
            else:
                # Load tools from server dynamically
                server_tools = await load_tools_from_mcp_server(server)

            if not server_tools:
                logger.debug(
                    "llm_no_tools_for_server",
                    server_name=server.name,
                )
                continue

            # Add each tool from the server
            for tool in server_tools:
                tool_name = tool.get("name")
                if not tool_name:
                    logger.warning(
                        "llm_tool_missing_name",
                        server_name=server.name,
                        tool=tool,
                    )
                    continue
                # LiteLLM expects tools in OpenAI function calling format
                tool_def = {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": tool.get("description", ""),
                        "parameters": tool.get("inputSchema", {}),
                    },
                }
                tools.append(tool_def)
                tool_to_server[tool_name] = server

                logger.debug(
                    "llm_tool_registered",
                    tool_name=tool_name,
                    server_name=server.name,
                    transport=server.transport_type,
                )

        logger.info(
            "llm_tools_built",
            tool_count=len(tools),
            server_count=len(mcp_servers),
        )

        return tools, tool_to_server
