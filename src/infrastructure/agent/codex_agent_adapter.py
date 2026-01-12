import shutil
from collections.abc import AsyncIterator
from typing import Any

from codex_sdk import Codex, CodexOptions, ThreadOptions
from codex_sdk.events import (
    ItemCompletedEvent,
    ItemStartedEvent,
    ThreadEvent,
    TurnCompletedEvent,
    TurnFailedEvent,
)
from codex_sdk.items import (
    AgentMessageItem,
    CommandExecutionItem,
    McpToolCallItem,
    ReasoningItem,
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

# Track if rate limit notification was shown (show only once)
_rate_limit_notified = False


def _is_rate_limit_error(e: BaseException) -> bool:
    """Check if error is a rate limit error (retry infinitely)."""
    msg = str(e).lower()
    return "rate limit" in msg or "429" in msg or "usage limit" in msg or "limit" in msg


def _is_retryable_error(e: BaseException) -> bool:
    """Check if error is retryable (rate limit or transient)."""
    if _is_rate_limit_error(e):
        return True
    msg = str(e).lower()
    retryable_patterns = (
        "timeout",
        "connection",
        "500",  # Internal Server Error
        "502",  # Bad Gateway
        "503",  # Service Unavailable
        "504",  # Gateway Timeout
        "temporarily",
        "try again",
        "retry",
    )
    return any(pattern in msg for pattern in retryable_patterns)


def _log_retry(retry_state: Any) -> None:
    """Log retry attempt and notify user about rate limit (once)."""
    global _rate_limit_notified
    exc = retry_state.outcome.exception()
    logger.warning(f"[CODEX] Retry {retry_state.attempt_number}: {str(exc)[:100]}")

    if _is_rate_limit_error(exc) and not _rate_limit_notified:
        _rate_limit_notified = True
        console = Console()
        console.print("[dim]Rate limit hit. Waiting for API availability...[/dim]")


class CodexAgentAdapter(AgentPort):
    """Implementation of AgentPort using OpenAI Codex SDK.

    Uses python-codex-sdk for streaming execution.

    Security: Runs with sandbox_mode="workspace-write" which restricts
    file writes to the working directory only. Network access is enabled.
    All tool calls are auto-approved (approval_policy="never").
    """

    def __init__(self) -> None:
        # Find codex in PATH since SDK's vendored binary may not exist
        codex_path = shutil.which("codex")
        if not codex_path:
            raise RuntimeError(
                "Codex CLI not found in PATH. Install it via: npm install -g @openai/codex"
            )
        self._codex = Codex(CodexOptions(codex_path_override=codex_path))
        logger.info(f"[CODEX] Using binary at: {codex_path}")

    async def execute(
        self,
        prompt: str,
        allowed_tools: list[str],  # noqa: ARG002
        cwd: str,
        on_message: MessageCallback | None = None,
        mcp_servers: dict[str, MCPServerConfig] | None = None,  # noqa: ARG002
    ) -> AgentResult:
        """Execute Codex agent via SDK."""
        logger.debug(f"Executing Codex agent with prompt:\n{prompt}")
        return await self._execute_codex(prompt, cwd, on_message)

    @retry(
        retry=retry_if_exception(_is_retryable_error),
        stop=stop_after_attempt(100),
        wait=wait_exponential(multiplier=30, max=600),
        before_sleep=_log_retry,
    )
    async def _execute_codex(
        self,
        prompt: str,
        cwd: str,
        on_message: MessageCallback | None = None,
    ) -> AgentResult:
        """Execute codex using SDK with streaming."""
        messages: list[AgentMessage] = []
        final_response = ""
        tools_used: set[str] = set()
        agent_info = AgentInfo(provider="codex", model="codex-cli", model_provider="openai")
        logger.info("[CODEX] Model: codex-cli via openai")

        thread_options = ThreadOptions(
            working_directory=cwd,
            approval_policy="never",
            sandbox_mode="workspace-write",
            network_access_enabled=True,
            skip_git_repo_check=True,
        )
        thread = self._codex.start_thread(thread_options)

        logger.info(f"[CODEX] Running with working_directory={cwd}")

        streamed = await thread.run_streamed(prompt)

        async for event in streamed.events:
            self._process_event(event, messages, tools_used, on_message)

            match event:
                case TurnCompletedEvent():
                    break
                case TurnFailedEvent(error=err):
                    # Check for authentication errors
                    if "401" in err.message or "unauthorized" in err.message.lower():
                        raise RuntimeError(
                            "Codex is not authorized. Run 'codex' to login with your OpenAI account."
                        )
                    raise RuntimeError(f"Codex turn failed: {err.message}")

        if messages:
            final_response = messages[-1].content

        logger.info(f"[CODEX] Completed with {len(messages)} messages, tools: {list(tools_used)}")

        return AgentResult(
            messages=messages,
            final_response=final_response,
            tools_used=list(tools_used),
            agent_info=agent_info,
        )

    def _process_event(
        self,
        event: ThreadEvent,
        messages: list[AgentMessage],
        tools_used: set[str],
        on_message: MessageCallback | None,
    ) -> None:
        """Process a SDK event."""
        logger.debug(f"[CODEX EVENT] {event}")

        match event:
            case ItemStartedEvent(item=CommandExecutionItem(command=cmd)):
                msg = AgentMessage(
                    role="tool_use", content="", tool_name="Bash", tool_input={"command": cmd}
                )
                tools_used.add("Bash")
                messages.append(msg)
                if on_message:
                    on_message(msg)
            case ItemCompletedEvent(item=item):
                self._process_completed_item(item, messages, tools_used, on_message)

    def _process_completed_item(
        self,
        item: Any,
        messages: list[AgentMessage],
        tools_used: set[str],
        on_message: MessageCallback | None,
    ) -> None:
        """Process a completed item from Codex SDK."""
        match item:
            case ReasoningItem(text=text) if text and on_message:
                on_message(AgentMessage(role="thought", content=text))

            case AgentMessageItem(text=text) if text:
                msg = AgentMessage(role="assistant", content=text)
                messages.append(msg)
                if on_message:
                    on_message(msg)

            case CommandExecutionItem(aggregated_output=output, exit_code=code, status=status):
                if status == "failed" or (code is not None and code != 0):
                    logger.warning(f"[CODEX] Command failed (exit {code}): {output[:200]}")
                if len(output) > 500:
                    logger.debug(f"[CODEX] Output truncated from {len(output)} to 500 chars")
                truncated = output[:500] + "..." if len(output) > 500 else output
                msg = AgentMessage(role="tool", content=truncated)
                tools_used.add("Bash")
                messages.append(msg)
                if on_message:
                    on_message(msg)

            case McpToolCallItem(
                server=server, tool=tool, arguments=args, result=result, error=err
            ):
                tool_name = f"{server}:{tool}"
                msg = AgentMessage(
                    role="tool_use",
                    content="",
                    tool_name=tool_name,
                    tool_input=args if isinstance(args, dict) else {},
                )
                tools_used.add(tool_name)
                messages.append(msg)
                if on_message:
                    on_message(msg)

                if result:
                    result_msg = AgentMessage(role="tool", content=str(result.content)[:500])
                    messages.append(result_msg)
                    if on_message:
                        on_message(result_msg)
                elif err:
                    error_msg = AgentMessage(role="tool", content=f"Error: {err.message}")
                    messages.append(error_msg)
                    if on_message:
                        on_message(error_msg)

    async def stream(
        self,
        prompt: str,
        allowed_tools: list[str],  # noqa: ARG002
        cwd: str,
        mcp_servers: dict[str, MCPServerConfig] | None = None,  # noqa: ARG002
    ) -> AsyncIterator[AgentMessage]:
        """Stream agent messages in real-time."""
        thread_options = ThreadOptions(
            working_directory=cwd,
            approval_policy="never",
            sandbox_mode="workspace-write",
            network_access_enabled=True,
            skip_git_repo_check=True,
        )
        thread = self._codex.start_thread(thread_options)
        streamed = await thread.run_streamed(prompt)

        async for event in streamed.events:
            match event:
                case TurnCompletedEvent():
                    break
                case TurnFailedEvent(error=err):
                    # Check for authentication errors
                    if "401" in err.message or "unauthorized" in err.message.lower():
                        raise RuntimeError(
                            "Codex is not authorized. Run 'codex' to login with your OpenAI account."
                        )
                    raise RuntimeError(f"Codex turn failed: {err.message}")
                case ItemStartedEvent(item=CommandExecutionItem(command=cmd)):
                    yield AgentMessage(
                        role="tool_use", content="", tool_name="Bash", tool_input={"command": cmd}
                    )
                case ItemCompletedEvent(item=item):
                    match item:
                        case ReasoningItem(text=text) if text:
                            yield AgentMessage(role="thought", content=text)
                        case AgentMessageItem(text=text) if text:
                            yield AgentMessage(role="assistant", content=text)
                        case CommandExecutionItem(
                            aggregated_output=output, exit_code=code, status=status
                        ):
                            if status == "failed" or (code is not None and code != 0):
                                logger.warning(
                                    f"[CODEX] Command failed (exit {code}): {output[:200]}"
                                )
                            if len(output) > 500:
                                logger.debug(
                                    f"[CODEX] Output truncated from {len(output)} to 500 chars"
                                )
                            truncated = output[:500] + "..." if len(output) > 500 else output
                            yield AgentMessage(role="tool", content=truncated)
                        case McpToolCallItem(server=server, tool=tool) as mcp:
                            yield AgentMessage(
                                role="tool_use", content="", tool_name=f"{server}:{tool}"
                            )
                            if mcp.result:
                                yield AgentMessage(
                                    role="tool", content=str(mcp.result.content)[:500]
                                )
                            elif mcp.error:
                                yield AgentMessage(
                                    role="tool", content=f"Error: {mcp.error.message}"
                                )
