import asyncio
import shutil
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from src.domain.ports.agent_port import AgentMessage, AgentPort, AgentResult, MessageCallback
from src.domain.value_objects.mcp_types import MCPServerConfig


def _check_codex_installed() -> bool:
    """Check if codex CLI is installed."""
    return shutil.which("codex") is not None


class CodexAgentAdapter(AgentPort):
    """Implementation of AgentPort using OpenAI Codex via MCP protocol.

    Uses `codex mcp-server` for reliable communication through the
    standardized Model Context Protocol.
    """

    def __init__(self) -> None:
        if not _check_codex_installed():
            raise RuntimeError(
                "Codex CLI not found.\n"
                "Install: npm i -g @openai/codex\n"
                "Setup:   codex  # OAuth login with ChatGPT"
            )

    async def execute(
        self,
        prompt: str,
        allowed_tools: list[str],
        cwd: str,
        on_message: MessageCallback | None = None,
        mcp_servers: dict[str, MCPServerConfig] | None = None,  # noqa: ARG002
    ) -> AgentResult:
        """Execute Codex agent via MCP protocol."""
        logger.debug(f"Executing Codex agent with prompt:\n{prompt}")

        # Retry loop for transient errors
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                return await self._execute_mcp(prompt, allowed_tools, cwd, on_message)
            except Exception as e:
                error_msg = str(e).lower()

                if "rate limit" in error_msg or "limit" in error_msg:
                    wait_seconds = min(60 * attempt, 600)
                    logger.warning(
                        f"[CODEX] Rate limit hit. Waiting {wait_seconds}s. "
                        f"Attempt {attempt}/{max_retries}"
                    )
                    await asyncio.sleep(wait_seconds)
                    continue

                if "timeout" in error_msg or "connection" in error_msg:
                    wait_seconds = min(30 * attempt, 300)
                    logger.warning(
                        f"[CODEX] Transient error: {str(e)[:100]}. "
                        f"Waiting {wait_seconds}s. Attempt {attempt}/{max_retries}"
                    )
                    await asyncio.sleep(wait_seconds)
                    continue

                raise

        raise RuntimeError(f"Max retries ({max_retries}) exceeded")

    async def _execute_mcp(
        self,
        prompt: str,
        allowed_tools: list[str],  # noqa: ARG002
        cwd: str,
        on_message: MessageCallback | None = None,
    ) -> AgentResult:
        """Execute via MCP protocol using codex mcp-server."""
        messages: list[AgentMessage] = []
        final_response = ""
        tools_used: set[str] = set()

        # Configure MCP server parameters with auto-approve settings
        # Use -c to configure approval policy and sandbox to avoid elicitation
        server_params = StdioServerParameters(
            command="codex",
            args=[
                "mcp-server",
                "-c",
                'approval_policy="never"',
                "-c",
                'sandbox_policy="danger-full-access"',
            ],
            cwd=cwd,
        )

        logger.info("[CODEX] Starting MCP server...")

        async with stdio_client(server_params) as streams:
            read_stream, write_stream = streams

            async with ClientSession(read_stream, write_stream) as session:
                # Initialize MCP session
                await session.initialize()
                logger.info("[CODEX] MCP session initialized")

                # List available tools to verify connection
                tools_result = await session.list_tools()
                available_tools = [tool.name for tool in tools_result.tools]
                logger.debug(f"[CODEX] Available tools: {available_tools}")

                # Call the codex tool to start a session
                result = await session.call_tool(
                    "codex",
                    arguments={
                        "prompt": prompt,
                        "cwd": cwd,
                    },
                )

                # Parse the result
                if result.content:
                    for content_block in result.content:
                        if hasattr(content_block, "text"):
                            text = content_block.text
                            final_response = text

                            agent_msg = AgentMessage(
                                role="assistant",
                                content=text,
                            )
                            messages.append(agent_msg)

                            if on_message:
                                on_message(agent_msg)

                            # Extract tool usage from response if mentioned
                            for tool in ["Bash", "Read", "Write", "Edit"]:
                                if tool.lower() in text.lower():
                                    tools_used.add(tool)

                logger.info(f"[CODEX] Completed with {len(messages)} messages")

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
        """Stream agent messages.

        Note: MCP protocol doesn't support true streaming for tool results,
        so we execute and yield the final result.
        """
        result = await self.execute(
            prompt=prompt,
            allowed_tools=allowed_tools,
            cwd=cwd,
            on_message=None,
            mcp_servers=mcp_servers,
        )

        for message in result.messages:
            yield message

    def _summarize_tool_input(self, tool_input: dict[str, Any] | None) -> str:
        """Summarize tool input for logging."""
        if not tool_input:
            return ""
        if "command" in tool_input:
            cmd = str(tool_input["command"])[:50]
            return f'cmd="{cmd}..."' if len(str(tool_input["command"])) > 50 else f'cmd="{cmd}"'
        if "path" in tool_input:
            return f'path="{tool_input["path"]}"'
        for key, value in tool_input.items():
            val_str = str(value)[:40]
            return f'{key}="{val_str}..."' if len(str(value)) > 40 else f'{key}="{val_str}"'
        return ""
