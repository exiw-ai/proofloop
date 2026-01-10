import asyncio
import json
import shutil
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
from loguru import logger

from src.domain.ports.agent_port import AgentMessage, AgentPort, AgentResult, MessageCallback
from src.domain.value_objects.mcp_types import MCPServerConfig

# Tool name mapping from Proofloop names to OpenCode names
PROOFLOOP_TO_OPENCODE_TOOLS: dict[str, str] = {
    "Read": "read",
    "Edit": "edit",
    "Write": "write",
    "Bash": "bash",
    "Glob": "glob",
    "Grep": "grep",
}

# Reverse mapping
OPENCODE_TO_PROOFLOOP_TOOLS: dict[str, str] = {v: k for k, v in PROOFLOOP_TO_OPENCODE_TOOLS.items()}

DEFAULT_PORT = 4096
SERVER_STARTUP_TIMEOUT = 30


def _check_opencode_installed() -> bool:
    """Check if opencode CLI is installed."""
    return shutil.which("opencode") is not None


class OpenCodeAgentAdapter(AgentPort):
    """Implementation of AgentPort using OpenCode HTTP API.

    Starts an OpenCode server in the background and communicates via
    HTTP API. Uses SSE for streaming responses.
    """

    def __init__(self, port: int = DEFAULT_PORT) -> None:
        if not _check_opencode_installed():
            raise RuntimeError(
                "OpenCode CLI not found.\n"
                "Install: npm i -g opencode-ai@latest\n"
                "Setup:   opencode  # Configure provider"
            )
        self._port = port
        self._base_url = f"http://localhost:{port}"
        self._server_process: asyncio.subprocess.Process | None = None
        self._session_id: str | None = None

    async def _ensure_server_running(self, cwd: str) -> None:
        """Ensure OpenCode server is running, start if needed."""
        # Check if server is already responding
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self._base_url}/global/health", timeout=2)
                if response.status_code == 200:
                    logger.debug("[OPENCODE] Server already running")
                    return
            except httpx.RequestError:
                pass

        # Start server
        logger.info(f"[OPENCODE] Starting server on port {self._port}...")
        self._server_process = await asyncio.create_subprocess_exec(
            "opencode",
            "serve",
            "--port",
            str(self._port),
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait for server to be ready
        start_time = asyncio.get_event_loop().time()
        async with httpx.AsyncClient() as client:
            while asyncio.get_event_loop().time() - start_time < SERVER_STARTUP_TIMEOUT:
                try:
                    response = await client.get(f"{self._base_url}/global/health", timeout=2)
                    if response.status_code == 200:
                        logger.info("[OPENCODE] Server is ready")
                        return
                except httpx.RequestError:
                    await asyncio.sleep(0.5)

        raise RuntimeError(f"OpenCode server failed to start within {SERVER_STARTUP_TIMEOUT}s")

    async def _create_session(self) -> str:
        """Create a new chat session and return its ID."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/session",
                json={"agent": "build"},  # Use build agent for full access
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            session_id = data.get("id") or str(uuid4())
            return str(session_id)

    async def execute(
        self,
        prompt: str,
        allowed_tools: list[str],
        cwd: str,
        on_message: MessageCallback | None = None,
        mcp_servers: dict[str, MCPServerConfig] | None = None,
    ) -> AgentResult:
        """Execute OpenCode agent with prompt and return complete result."""
        logger.debug(f"Executing OpenCode agent with prompt:\n{prompt}")

        # Map tool names
        opencode_tools = [PROOFLOOP_TO_OPENCODE_TOOLS.get(tool, tool) for tool in allowed_tools]

        # Retry loop
        max_retries = 10
        for attempt in range(1, max_retries + 1):
            try:
                await self._ensure_server_running(cwd)

                # Create session if needed
                if not self._session_id:
                    self._session_id = await self._create_session()

                return await self._execute_request(
                    prompt, opencode_tools, cwd, on_message, mcp_servers
                )

            except Exception as e:
                error_msg = str(e).lower()

                if "rate limit" in error_msg or "429" in error_msg:
                    wait_seconds = min(60 * attempt, 600)
                    logger.warning(
                        f"[OPENCODE] Rate limit hit. Waiting {wait_seconds}s. "
                        f"Attempt {attempt}/{max_retries}"
                    )
                    await asyncio.sleep(wait_seconds)
                    continue

                if "timeout" in error_msg or "connection" in error_msg:
                    wait_seconds = min(30 * attempt, 300)
                    logger.warning(
                        f"[OPENCODE] Transient error: {str(e)[:100]}. "
                        f"Waiting {wait_seconds}s. Attempt {attempt}/{max_retries}"
                    )
                    # Reset server on connection errors
                    self._session_id = None
                    await asyncio.sleep(wait_seconds)
                    continue

                raise

        raise RuntimeError(f"Max retries ({max_retries}) exceeded")

    async def _execute_request(
        self,
        prompt: str,
        tools: list[str],  # noqa: ARG002
        cwd: str,  # noqa: ARG002
        on_message: MessageCallback | None,
        mcp_servers: dict[str, MCPServerConfig] | None,  # noqa: ARG002
    ) -> AgentResult:
        """Execute a single request to OpenCode server."""
        messages: list[AgentMessage] = []
        final_response = ""
        tools_used: set[str] = set()

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
            # Send message - OpenCode handles tools internally
            response = await client.post(
                f"{self._base_url}/session/{self._session_id}/message",
                json={
                    "parts": [{"type": "text", "text": prompt}],
                },
            )
            response.raise_for_status()
            data = response.json()

            # Parse response - OpenCode uses 'parts' array
            parts = data.get("parts", [])
            for part in parts:
                agent_msg = self._parse_message(part)
                if agent_msg:
                    messages.append(agent_msg)

                    if on_message:
                        on_message(agent_msg)

                    if agent_msg.tool_name:
                        proofloop_name = OPENCODE_TO_PROOFLOOP_TOOLS.get(
                            agent_msg.tool_name, agent_msg.tool_name
                        )
                        tools_used.add(proofloop_name)
                        logger.info(
                            f"[TOOL] {proofloop_name}: "
                            f"{self._summarize_tool_input(agent_msg.tool_input)}"
                        )

                    if agent_msg.role == "assistant" and agent_msg.content:
                        final_response = agent_msg.content

        return AgentResult(
            messages=messages,
            final_response=final_response,
            tools_used=list(tools_used),
        )

    def _parse_message(self, msg: dict[str, Any]) -> AgentMessage | None:
        """Parse OpenCode message into AgentMessage."""
        msg_type = msg.get("type", msg.get("role", ""))

        if msg_type in ("assistant", "text"):
            content = msg.get("content", msg.get("text", ""))
            if isinstance(content, list):
                # Extract text from content blocks
                texts = [
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                content = "\n".join(texts)
            return AgentMessage(
                role="assistant",
                content=content,
            )

        elif msg_type in ("tool_use", "tool_call"):
            return AgentMessage(
                role="tool_use",
                content="",
                tool_name=msg.get("name", msg.get("tool", "")),
                tool_input=msg.get("input", msg.get("arguments", {})),
            )

        elif msg_type == "tool_result":
            content = msg.get("content", msg.get("output", ""))
            if isinstance(content, list):
                content = str(content)
            return AgentMessage(
                role="tool_result",
                content=content,
            )

        return None

    async def stream(
        self,
        prompt: str,
        allowed_tools: list[str],
        cwd: str,
        mcp_servers: dict[str, MCPServerConfig] | None = None,  # noqa: ARG002
    ) -> AsyncIterator[AgentMessage]:
        """Stream agent messages using SSE.

        OpenCode supports Server-Sent Events for real-time streaming.
        """
        opencode_tools = [PROOFLOOP_TO_OPENCODE_TOOLS.get(tool, tool) for tool in allowed_tools]

        await self._ensure_server_running(cwd)

        if not self._session_id:
            self._session_id = await self._create_session()

        logger.debug(f"Streaming OpenCode agent with prompt: {prompt[:100]}...")

        async with (
            httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client,
            client.stream(
                "POST",
                f"{self._base_url}/session/{self._session_id}/message/stream",
                json={
                    "parts": [{"type": "text", "text": prompt}],
                    "tools": opencode_tools,
                },
            ) as response,
        ):
            response.raise_for_status()

            buffer = ""
            async for chunk in response.aiter_text():
                buffer += chunk

                # Parse SSE events
                while "\n\n" in buffer:
                    event_text, buffer = buffer.split("\n\n", 1)
                    event_text = event_text.strip()

                    if not event_text:
                        continue

                    # Parse SSE format: "data: {...}"
                    for line in event_text.split("\n"):
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                agent_msg = self._parse_message(data)
                                if agent_msg:
                                    yield agent_msg
                            except json.JSONDecodeError:
                                logger.warning(f"[OPENCODE] Failed to parse SSE: {line[:100]}")

    async def cleanup(self) -> None:
        """Stop the OpenCode server if we started it."""
        if self._server_process and self._server_process.returncode is None:
            logger.info("[OPENCODE] Stopping server...")
            self._server_process.terminate()
            try:
                await asyncio.wait_for(self._server_process.wait(), timeout=5)
            except TimeoutError:
                self._server_process.kill()
            self._server_process = None

    def _summarize_tool_input(self, tool_input: dict[str, Any] | None) -> str:
        """Summarize tool input for logging."""
        if not tool_input:
            return ""
        if "query" in tool_input:
            query = str(tool_input["query"])[:60]
            return (
                f'query="{query}..."' if len(str(tool_input["query"])) > 60 else f'query="{query}"'
            )
        if "path" in tool_input:
            return f'path="{tool_input["path"]}"'
        if "file" in tool_input:
            return f'file="{tool_input["file"]}"'
        if "command" in tool_input:
            cmd = str(tool_input["command"])[:50]
            return f'cmd="{cmd}..."' if len(str(tool_input["command"])) > 50 else f'cmd="{cmd}"'
        for key, value in tool_input.items():
            val_str = str(value)[:40]
            return f'{key}="{val_str}..."' if len(str(value)) > 40 else f'{key}="{val_str}"'
        return ""
