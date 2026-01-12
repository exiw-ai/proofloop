from collections.abc import AsyncIterator
from typing import Any, cast

from claude_code_sdk import (
    AssistantMessage,
    ClaudeCodeOptions,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    query,
)
from loguru import logger
from rich.console import Console
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.domain.ports.agent_port import (
    AgentInfo,
    AgentMessage,
    AgentPort,
    AgentResult,
    MessageCallback,
)
from src.domain.value_objects.mcp_types import MCPServerConfig

MCPServersDict = dict[str, Any]

# Track if rate limit notification was shown (show only once)
_rate_limit_notified = False


def _is_rate_limit_error(e: BaseException) -> bool:
    """Check if error is a rate limit error (retry infinitely)."""
    msg = str(e).lower()
    return "hit your limit" in msg or "rate limit" in msg or "429" in msg or "usage limit" in msg


def _is_retryable_error(e: BaseException) -> bool:
    """Check if error is retryable (rate limit or transient)."""
    if _is_rate_limit_error(e):
        return True
    msg = str(e).lower()
    return "exit code: 1" in msg or "temporarily unavailable" in msg


def _log_retry(retry_state: Any) -> None:
    """Log retry attempt and notify user about rate limit (once)."""
    global _rate_limit_notified
    exc = retry_state.outcome.exception()
    logger.warning(f"[CLAUDE] Retry {retry_state.attempt_number}: {str(exc)[:100]}")

    if _is_rate_limit_error(exc) and not _rate_limit_notified:
        _rate_limit_notified = True
        console = Console()
        console.print("[dim]Rate limit hit. Waiting for API availability...[/dim]")


class ClaudeAgentAdapter(AgentPort):
    """Implementation of AgentPort using Claude Agent SDK.

    Uses the claude-code-sdk query() function for executing prompts and
    streaming agent messages.
    """

    @staticmethod
    def _build_options(
        allowed_tools: list[str],
        cwd: str,
        mcp_servers: dict[str, MCPServerConfig] | None,
    ) -> ClaudeCodeOptions:
        """Build SDK options with MCP servers configuration."""
        sdk_mcp_servers: MCPServersDict = {}
        if mcp_servers:
            sdk_mcp_servers = {name: cfg.to_sdk_config() for name, cfg in mcp_servers.items()}

        return ClaudeCodeOptions(
            allowed_tools=allowed_tools,
            cwd=cwd,
            mcp_servers=cast(Any, sdk_mcp_servers) if sdk_mcp_servers else {},
        )

    async def execute(
        self,
        prompt: str,
        allowed_tools: list[str],
        cwd: str,
        on_message: MessageCallback | None = None,
        mcp_servers: dict[str, MCPServerConfig] | None = None,
    ) -> AgentResult:
        """Execute Claude agent with prompt and return complete result."""
        options = self._build_options(allowed_tools, cwd, mcp_servers)
        logger.debug(f"Executing agent with prompt:\n{prompt}")
        return await self._execute_query(prompt, options, on_message)

    @retry(
        retry=retry_if_exception(_is_retryable_error),
        stop=stop_after_attempt(100),
        wait=wait_exponential(multiplier=30, max=600),
        before_sleep=_log_retry,
    )
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
        agent_info: AgentInfo | None = None

        async for message in query(prompt=prompt, options=options):
            # Capture model info from first AssistantMessage
            if isinstance(message, AssistantMessage) and agent_info is None:
                agent_info = AgentInfo(
                    provider="claude",
                    model=message.model,
                    model_provider="anthropic",
                )
                logger.info(f"[CLAUDE] Model: {agent_info.model}")

            agent_msgs = self._convert_message(message)
            for agent_msg in agent_msgs:
                messages.append(agent_msg)

                if on_message:
                    on_message(agent_msg)

                if agent_msg.tool_name:
                    tools_used.add(agent_msg.tool_name)
                    logger.info(
                        f"[TOOL] {agent_msg.tool_name}: "
                        f"{self._summarize_tool_input(agent_msg.tool_input)}"
                    )
                if agent_msg.role == "assistant" and agent_msg.content:
                    final_response = agent_msg.content
                    if not on_message:
                        logger.debug(f"[AGENT] Response: {agent_msg.content[:300]}...")

            # Check for ResultMessage
            if isinstance(message, ResultMessage):
                logger.info(
                    f"[AGENT] Completed: turns={message.num_turns}, "
                    f"duration={message.duration_ms}ms"
                )

        return AgentResult(
            messages=messages,
            final_response=final_response,
            tools_used=list(tools_used),
            agent_info=agent_info,
        )

    async def stream(
        self,
        prompt: str,
        allowed_tools: list[str],
        cwd: str,
        mcp_servers: dict[str, MCPServerConfig] | None = None,
    ) -> AsyncIterator[AgentMessage]:
        """Stream agent messages for real-time display."""
        options = self._build_options(allowed_tools, cwd, mcp_servers)
        logger.debug(f"Streaming agent with prompt: {prompt[:100]}...")

        async for message in query(prompt=prompt, options=options):
            for agent_msg in self._convert_message(message):
                yield agent_msg

    def _convert_message(self, msg: object) -> list[AgentMessage]:
        """Convert SDK message to domain AgentMessages."""
        match msg:
            case AssistantMessage():
                return self._convert_assistant_message(msg)
            case ResultMessage(result=result):
                return [AgentMessage(role="assistant", content=result or "")]
            case _:
                return []

    def _convert_assistant_message(self, msg: AssistantMessage) -> list[AgentMessage]:
        """Convert AssistantMessage with content blocks to AgentMessages."""
        messages: list[AgentMessage] = []

        logger.debug(f"[SDK] AssistantMessage blocks={len(msg.content)}")
        for i, block in enumerate(msg.content):
            logger.debug(f"[SDK BLOCK {i}] {block}")

        for block in msg.content:
            match block:
                case ThinkingBlock(thinking=text) if text:
                    messages.append(AgentMessage(role="thought", content=text))
                case ToolUseBlock(name=name, input=inp):
                    messages.append(
                        AgentMessage(role="tool_use", content="", tool_name=name, tool_input=inp)
                    )
                case ToolResultBlock(content=content):
                    messages.append(
                        AgentMessage(
                            role="tool_result",
                            content=content if isinstance(content, str) else str(content),
                        )
                    )
                case TextBlock(text=text):
                    messages.append(AgentMessage(role="assistant", content=text))

        return messages

    _SUMMARY_KEYS = ["query", "url", "pattern", "file_path", "command"]

    def _summarize_tool_input(self, tool_input: dict[str, Any] | None) -> str:
        """Summarize tool input for logging."""
        if not tool_input:
            return ""

        for key in self._SUMMARY_KEYS:
            if key in tool_input:
                val = str(tool_input[key])[:50]
                suffix = "..." if len(str(tool_input[key])) > 50 else ""
                display_key = "file" if key == "file_path" else ("cmd" if key == "command" else key)
                return f'{display_key}="{val}{suffix}"'

        # Fallback: first key-value
        if tool_input:
            key, val = next(iter(tool_input.items()))
            val_str = str(val)[:40]
            suffix = "..." if len(str(val)) > 40 else ""
            return f'{key}="{val_str}{suffix}"'
        return ""
