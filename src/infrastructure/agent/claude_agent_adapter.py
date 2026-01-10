import asyncio
import re
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any, cast

from claude_code_sdk import ClaudeCodeOptions, query
from loguru import logger

from src.domain.ports.agent_port import AgentMessage, AgentPort, AgentResult, MessageCallback
from src.domain.value_objects.mcp_types import MCPServerConfig

# Type alias for SDK MCP servers parameter
MCPServersDict = dict[str, Any]


def _parse_reset_time(message: str) -> datetime | None:
    """Parse reset time from rate limit message like 'resets 5pm
    (Asia/Nicosia)'."""
    # Match patterns like "5pm", "5:30pm", "17:00"
    match = re.search(r"resets?\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", message.lower())
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    period = match.group(3)

    # Convert to 24-hour format
    if period == "pm" and hour != 12:
        hour += 12
    elif period == "am" and hour == 12:
        hour = 0

    now = datetime.now()
    reset_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # If reset time is in the past, it's tomorrow
    if reset_time <= now:
        reset_time += timedelta(days=1)

    return reset_time


def _calculate_wait_seconds(reset_time: datetime | None) -> int:
    """Calculate seconds to wait until reset time, with min/max bounds."""
    if reset_time is None:
        return 60  # Default 1 minute if can't parse

    wait = (reset_time - datetime.now()).total_seconds()
    # Bounds: min 30 seconds, max 2 hours
    return max(30, min(int(wait) + 10, 7200))  # +10s buffer


class ClaudeAgentAdapter(AgentPort):
    """Implementation of AgentPort using Claude Agent SDK.

    Uses the claude-code-sdk query() function for executing prompts and
    streaming agent messages.
    """

    async def execute(
        self,
        prompt: str,
        allowed_tools: list[str],
        cwd: str,
        on_message: MessageCallback | None = None,
        mcp_servers: dict[str, MCPServerConfig] | None = None,
    ) -> AgentResult:
        """Execute Claude agent with prompt and return complete result."""
        # Convert MCP configs to SDK format
        sdk_mcp_servers: MCPServersDict = {}
        if mcp_servers:
            for name, config in mcp_servers.items():
                sdk_mcp_servers[name] = config.to_sdk_config()

        options = ClaudeCodeOptions(
            allowed_tools=allowed_tools,
            cwd=cwd,
            mcp_servers=cast(Any, sdk_mcp_servers) if sdk_mcp_servers else {},
        )

        logger.debug(f"Executing agent with prompt:\n{prompt}")

        # Retry loop for rate limits
        max_retries = 10
        for attempt in range(1, max_retries + 1):
            try:
                return await self._execute_query(prompt, options, on_message)
            except Exception as e:
                error_msg = str(e).lower()

                # Check if it's a rate limit error
                if "hit your limit" in error_msg or "rate limit" in error_msg:
                    reset_time = _parse_reset_time(str(e))
                    wait_seconds = _calculate_wait_seconds(reset_time)

                    if reset_time:
                        logger.warning(
                            f"[AGENT] Rate limit hit. Waiting until {reset_time.strftime('%H:%M')} "
                            f"({wait_seconds}s). Attempt {attempt}/{max_retries}"
                        )
                    else:
                        logger.warning(
                            f"[AGENT] Rate limit hit. Waiting {wait_seconds}s. "
                            f"Attempt {attempt}/{max_retries}"
                        )

                    await asyncio.sleep(wait_seconds)
                    continue

                # For other errors, retry with shorter delay
                if "exit code: 1" in error_msg or "temporarily unavailable" in error_msg:
                    wait_seconds = min(30 * attempt, 300)  # 30s, 60s... up to 5min
                    logger.warning(
                        f"[AGENT] Temporary error: {str(e)[:100]}. "
                        f"Waiting {wait_seconds}s. Attempt {attempt}/{max_retries}"
                    )
                    await asyncio.sleep(wait_seconds)
                    continue

                # Non-retryable error
                raise

        raise RuntimeError(f"Max retries ({max_retries}) exceeded")

    async def _execute_query(
        self,
        prompt: str,
        options: ClaudeCodeOptions,
        on_message: MessageCallback | None = None,
    ) -> AgentResult:
        """Execute single query attempt."""
        messages: list[AgentMessage] = []
        final_response = ""
        tools_used: set[str] = set()

        async for message in query(prompt=prompt, options=options):
            agent_msg = self._convert_message(message)
            if agent_msg is not None:
                messages.append(agent_msg)

                # Invoke callback for real-time display
                if on_message:
                    on_message(agent_msg)

                if agent_msg.tool_name:
                    tools_used.add(agent_msg.tool_name)
                    # Log tool calls at INFO level for visibility without --verbose
                    logger.info(
                        f"[TOOL] {agent_msg.tool_name}: "
                        f"{self._summarize_tool_input(agent_msg.tool_input)}"
                    )
                if agent_msg.role == "assistant" and agent_msg.content:
                    final_response = agent_msg.content
                    # Only log if no callback to avoid duplication
                    if not on_message:
                        logger.debug(f"[AGENT] Response: {agent_msg.content[:300]}...")

            # Check for ResultMessage using duck typing
            if hasattr(message, "result") and hasattr(message, "num_turns"):
                logger.info(
                    f"[AGENT] Completed: turns={getattr(message, 'num_turns', 0)}, "
                    f"duration={getattr(message, 'duration_ms', 0)}ms"
                )

        return AgentResult(
            messages=messages,
            final_response=final_response,
            tools_used=list(tools_used),
        )

    async def stream(
        self,
        prompt: str,
        allowed_tools: list[str],
        cwd: str,
        mcp_servers: dict[str, MCPServerConfig] | None = None,
    ) -> AsyncIterator[AgentMessage]:
        """Stream agent messages for real-time display."""
        # Convert MCP configs to SDK format
        sdk_mcp_servers: MCPServersDict = {}
        if mcp_servers:
            for name, config in mcp_servers.items():
                sdk_mcp_servers[name] = config.to_sdk_config()

        options = ClaudeCodeOptions(
            allowed_tools=allowed_tools,
            cwd=cwd,
            mcp_servers=cast(Any, sdk_mcp_servers) if sdk_mcp_servers else {},
        )

        logger.debug(f"Streaming agent with prompt: {prompt[:100]}...")

        async for message in query(prompt=prompt, options=options):
            agent_msg = self._convert_message(message)
            if agent_msg is not None:
                yield agent_msg

    def _convert_message(self, msg: object) -> AgentMessage | None:
        """Convert SDK message to domain AgentMessage."""
        # Check for AssistantMessage (has content attribute with list of blocks)
        if hasattr(msg, "content") and hasattr(msg, "model"):
            return self._convert_assistant_message(msg)
        # Check for ResultMessage (has result, num_turns, duration_ms)
        if hasattr(msg, "result") and hasattr(msg, "num_turns"):
            return self._convert_result_message(msg)
        # SystemMessage and UserMessage are typically not needed for our use case
        return None

    def _convert_assistant_message(self, msg: object) -> AgentMessage | None:
        """Convert AssistantMessage with content blocks to AgentMessage."""
        content_blocks = getattr(msg, "content", [])
        for block in content_blocks:
            # TextBlock: has 'text' attribute
            if hasattr(block, "text") and not hasattr(block, "name"):
                return AgentMessage(
                    role="assistant",
                    content=getattr(block, "text", ""),
                )
            # ToolUseBlock: has 'name' and 'input' attributes
            if hasattr(block, "name") and hasattr(block, "input"):
                return AgentMessage(
                    role="tool_use",
                    content="",
                    tool_name=getattr(block, "name", ""),
                    tool_input=getattr(block, "input", {}),
                )
            # ToolResultBlock: has 'tool_use_id' attribute
            if hasattr(block, "tool_use_id"):
                block_content = getattr(block, "content", None)
                content = ""
                if block_content:
                    content = (
                        block_content if isinstance(block_content, str) else str(block_content)
                    )
                return AgentMessage(
                    role="tool_result",
                    content=content,
                )
        return None

    def _convert_result_message(self, msg: object) -> AgentMessage:
        """Convert ResultMessage to AgentMessage."""
        return AgentMessage(
            role="assistant",
            content=getattr(msg, "result", "") or "",
        )

    def _summarize_tool_input(self, tool_input: dict[str, Any] | None) -> str:
        """Summarize tool input for logging."""
        if not tool_input:
            return ""
        if "query" in tool_input:
            query = str(tool_input["query"])[:60]
            return (
                f'query="{query}..."' if len(str(tool_input["query"])) > 60 else f'query="{query}"'
            )
        if "url" in tool_input:
            return f'url="{tool_input["url"]}"'
        if "pattern" in tool_input:
            return f'pattern="{tool_input["pattern"]}"'
        if "file_path" in tool_input:
            return f'file="{tool_input["file_path"]}"'
        if "command" in tool_input:
            cmd = str(tool_input["command"])[:50]
            return f'cmd="{cmd}..."' if len(str(tool_input["command"])) > 50 else f'cmd="{cmd}"'
        # Fallback: show first key-value
        for key, value in tool_input.items():
            val_str = str(value)[:40]
            return f'{key}="{val_str}..."' if len(str(value)) > 40 else f'{key}="{val_str}"'
        return ""
