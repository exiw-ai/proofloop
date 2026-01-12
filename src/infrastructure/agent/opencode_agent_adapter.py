import asyncio
import contextlib
import json
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
from loguru import logger
from opencode_ai import AsyncOpencode
from opencode_ai.types import (
    Part,
    StepFinishPart,
    StepStartPart,
    TextPart,
    ToolPart,
)
from opencode_ai.types.event_list_response import (
    EventListResponse,
    EventMessagePartUpdated,
    EventSessionIdle,
)
from opencode_ai.types.tool_state_completed import ToolStateCompleted
from rich.console import Console
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.domain.ports.agent_port import (
    AgentInfo,
    AgentMessage,
    AgentPort,
    AgentResult,
    MessageCallback,
    SessionStallError,
)
from src.domain.value_objects.mcp_types import MCPServerConfig

# =============================================================================
# Constants
# =============================================================================

PROOFLOOP_TO_OPENCODE_TOOLS: dict[str, str] = {
    "Read": "read",
    "Edit": "edit",
    "Write": "write",
    "Bash": "bash",
    "Glob": "glob",
    "Grep": "grep",
}

OPENCODE_TO_PROOFLOOP_TOOLS: dict[str, str] = {v: k for k, v in PROOFLOOP_TO_OPENCODE_TOOLS.items()}

# OpenCode uses camelCase params, Proofloop uses snake_case
OPENCODE_PARAM_MAP: dict[str, str] = {
    "filePath": "file_path",
    "fileName": "file_name",
}


def _normalize_tool_input(tool_input: dict[str, object]) -> dict[str, object]:
    """Convert OpenCode camelCase params to snake_case."""
    return {OPENCODE_PARAM_MAP.get(k, k): v for k, v in tool_input.items()}


DEFAULT_PORT = 4096
SERVER_STARTUP_TIMEOUT = 30
REQUEST_TIMEOUT = 600.0
SESSION_STALL_TIMEOUT = 60.0  # Abort session if no events for this long


# Track if rate limit notification was shown (show only once)
_rate_limit_notified = False


def _is_rate_limit_error(e: BaseException) -> bool:
    """Check if error is a rate limit error (retry infinitely)."""
    msg = str(e).lower()
    return "rate limit" in msg or "429" in msg or "usage limit" in msg


def _is_retryable_error(e: BaseException) -> bool:
    """Check if error is retryable."""
    if _is_rate_limit_error(e):
        return True
    msg = str(e).lower()
    return (
        "500" in msg
        or "502" in msg
        or "503" in msg
        or "504" in msg
        or "timeout" in msg
        or "connection" in msg
    )


def _log_retry(retry_state: Any) -> None:
    """Log retry attempt and notify user about rate limit (once)."""
    global _rate_limit_notified
    exc = retry_state.outcome.exception()
    logger.warning(f"[OPENCODE] Retry {retry_state.attempt_number}: {str(exc)[:100]}")

    if _is_rate_limit_error(exc) and not _rate_limit_notified:
        _rate_limit_notified = True
        console = Console()
        console.print("[dim]Rate limit hit. Waiting for API availability...[/dim]")


def _check_opencode_installed() -> bool:
    """Check if opencode CLI is installed."""
    return shutil.which("opencode") is not None


class OpenCodeAgentAdapter(AgentPort):
    """AgentPort implementation using OpenCode SDK.

    OpenCode runs as a local HTTP server that proxies requests to
    various LLM providers (OpenAI, Anthropic, etc.). Each session is
    tied to a specific project directory.
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
        self._server_cwd: str | None = None
        self._created_config: Path | None = None  # Track if we created opencode.json

    @staticmethod
    def _extract_provider_id(config: Any) -> str | None:
        """Extract provider ID from config, or None to use OpenCode default."""
        if config.provider:
            return next(iter(config.provider), None)
        return None

    # -------------------------------------------------------------------------
    # Server Management
    # -------------------------------------------------------------------------

    async def _ensure_server_running(self, cwd: str) -> None:
        """Ensure OpenCode server is running with correct working directory."""
        # Create opencode.json with workspace restrictions if it doesn't exist
        config_path = Path(cwd) / "opencode.json"
        if not config_path.exists():
            config = {"permission": {"external_directory": "deny"}}
            config_path.write_text(json.dumps(config, indent=2))
            self._created_config = config_path
            logger.info(f"[OPENCODE] Created workspace config: {config_path}")

        if await self._health_check():
            if self._server_cwd == cwd:
                logger.debug("[OPENCODE] Server already running with correct CWD")
                return
            logger.info("[OPENCODE] Server running with wrong CWD, restarting...")
            await self.cleanup()

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

        await self._wait_for_server()
        self._server_cwd = cwd
        logger.info("[OPENCODE] Server is ready")

    async def _health_check(self) -> bool:
        """Check if server is responding."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self._base_url}/global/health", timeout=2)
                return bool(response.status_code == 200)
        except httpx.RequestError:
            return False

    async def _wait_for_server(self) -> None:
        """Wait for server to become ready."""
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < SERVER_STARTUP_TIMEOUT:
            if await self._health_check():
                return
            await asyncio.sleep(0.5)
        raise RuntimeError(f"OpenCode server failed to start within {SERVER_STARTUP_TIMEOUT}s")

    async def cleanup(self) -> None:
        """Stop the OpenCode server and clean up created config."""
        # Remove opencode.json if we created it
        if self._created_config and self._created_config.exists():
            self._created_config.unlink()
            logger.info(f"[OPENCODE] Removed workspace config: {self._created_config}")
            self._created_config = None

        if self._server_process and self._server_process.returncode is None:
            logger.info("[OPENCODE] Stopping server...")
            self._server_process.terminate()
            try:
                await asyncio.wait_for(self._server_process.wait(), timeout=5)
            except TimeoutError:
                self._server_process.kill()
            self._server_process = None
        self._server_cwd = None

    async def _abort_session(self, session_id: str) -> bool:
        """Abort a stuck session via HTTP API."""
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=5) as http:
                resp = await http.post(f"/session/{session_id}/abort")
                if resp.status_code == 200:
                    logger.warning(f"[OPENCODE] Aborted stuck session {session_id}")
                    return True
        except Exception as e:
            logger.debug(f"[OPENCODE] Failed to abort session: {e}")
        return False

    # -------------------------------------------------------------------------
    # Message Execution (rewritten using SDK)
    # -------------------------------------------------------------------------

    async def execute(
        self,
        prompt: str,
        allowed_tools: list[str],  # noqa: ARG002
        cwd: str,
        on_message: MessageCallback | None = None,
        mcp_servers: dict[str, MCPServerConfig] | None = None,  # noqa: ARG002
    ) -> AgentResult:
        """Execute prompt and return complete result using SDK."""
        logger.debug(f"Executing OpenCode agent with prompt:\n{prompt}")
        await self._ensure_server_running(cwd)
        return await self._execute_with_sdk(prompt, on_message)

    @retry(
        retry=retry_if_exception(_is_retryable_error),
        stop=stop_after_attempt(100),
        wait=wait_exponential(multiplier=30, max=600),
        before_sleep=_log_retry,
    )
    async def _execute_with_sdk(
        self,
        prompt: str,
        on_message: MessageCallback | None,
    ) -> AgentResult:
        """Execute using SDK client with SSE event streaming."""
        messages: list[AgentMessage] = []
        final_response = ""
        tools_used: set[str] = set()
        agent_info: AgentInfo | None = None
        completion_event = asyncio.Event()

        async with AsyncOpencode(
            base_url=self._base_url,
            timeout=REQUEST_TIMEOUT,
        ) as client:
            # Get config - use OpenCode's configured model/provider
            config = await client.config.get()
            model_id = config.model
            provider_id = self._extract_provider_id(config)

            # If not set in config, fetch defaults from /config/providers
            if not model_id or not provider_id:
                async with httpx.AsyncClient(base_url=self._base_url, timeout=30) as http:
                    resp = await http.get("/config/providers")
                    if resp.status_code == 200:
                        providers_data = resp.json()
                        defaults = providers_data.get("default", {})
                        if not provider_id and defaults:
                            provider_id = next(iter(defaults.keys()), None)
                        if not model_id and provider_id and defaults:
                            model_id = defaults.get(provider_id)

            # Fallback to hardcoded defaults if still not set
            model_id = model_id or "claude-sonnet-4-20250514"
            provider_id = provider_id or "anthropic"

            agent_info = AgentInfo(
                provider="opencode",
                model=model_id,
                model_provider=provider_id,
            )
            logger.info(f"[OPENCODE] Using model: {model_id} via {provider_id}")

            # Create session - use httpx directly due to SDK bug with empty body
            async with httpx.AsyncClient(base_url=self._base_url, timeout=30) as http:
                resp = await http.post("/session", json={})
                resp.raise_for_status()
                session_data = resp.json()
                session_id = session_data["id"]
            logger.info(f"[OPENCODE] Session created: {session_id}")

            # Track last event time for stall detection
            last_event_time = asyncio.get_event_loop().time()

            async def process_events() -> None:
                """Process SSE events from the event stream.

                OpenCode SSE sends cumulative text updates (full message
                so far), not deltas. We track the last assistant message
                index and replace it instead of appending, to avoid
                massive duplication.
                """
                nonlocal final_response, last_event_time
                last_assistant_idx: int | None = None

                try:
                    event_stream = await client.event.list()
                    async with event_stream:
                        async for event in event_stream:
                            last_event_time = asyncio.get_event_loop().time()
                            result = self._process_event(event)
                            if result:
                                agent_msg, tool_name = result

                                # Handle TextPart streaming: replace last assistant msg
                                if agent_msg.role == "assistant":
                                    # Check if this is a cumulative update or a new message
                                    is_cumulative = False
                                    if last_assistant_idx is not None and agent_msg.content:
                                        prev = messages[last_assistant_idx].content or ""
                                        curr = agent_msg.content
                                        is_cumulative = curr.startswith(prev)

                                    if last_assistant_idx is not None and is_cumulative:
                                        # Cumulative update - replace
                                        messages[last_assistant_idx] = agent_msg
                                    else:
                                        # New message - emit previous if exists
                                        if last_assistant_idx is not None and on_message:
                                            on_message(messages[last_assistant_idx])
                                        # Append new message and track
                                        messages.append(agent_msg)
                                        last_assistant_idx = len(messages) - 1

                                    # Update final response
                                    if agent_msg.content:
                                        final_response = agent_msg.content
                                else:
                                    # Non-assistant messages: reset tracking, append normally
                                    last_assistant_idx = None
                                    messages.append(agent_msg)

                                    if on_message:
                                        on_message(agent_msg)

                                    if tool_name:
                                        tools_used.add(
                                            OPENCODE_TO_PROOFLOOP_TOOLS.get(tool_name, tool_name)
                                        )

                            # Check for session idle (completion)
                            match event:
                                case EventSessionIdle():
                                    # Emit final assistant message on completion
                                    if last_assistant_idx is not None and on_message:
                                        on_message(messages[last_assistant_idx])
                                    completion_event.set()
                                    return

                            if completion_event.is_set():
                                return

                except Exception as e:
                    logger.warning(f"[OPENCODE] SSE error: {e}")

            # Track if session was aborted due to stall
            session_aborted = False
            abort_reason = ""

            async def stall_watchdog() -> None:
                """Watch for stalled sessions and abort if no events
                received."""
                nonlocal session_aborted, abort_reason
                while not completion_event.is_set():
                    await asyncio.sleep(5)  # Check every 5 seconds
                    elapsed = asyncio.get_event_loop().time() - last_event_time
                    if elapsed > SESSION_STALL_TIMEOUT:
                        abort_reason = f"Session {session_id} stalled ({elapsed:.0f}s no events)"
                        logger.warning(f"[OPENCODE] {abort_reason}, aborting")
                        await self._abort_session(session_id)
                        session_aborted = True
                        completion_event.set()
                        return

            # Start event listener and stall watchdog tasks
            event_task = asyncio.create_task(process_events())
            watchdog_task = asyncio.create_task(stall_watchdog())

            # Small delay to ensure SSE connection is established
            await asyncio.sleep(0.1)

            # Send message using SDK - model_id and provider_id are required
            try:
                await client.session.chat(
                    session_id,
                    model_id=model_id,
                    provider_id=provider_id,
                    parts=[{"type": "text", "text": prompt}],
                    timeout=REQUEST_TIMEOUT,
                )
            except Exception as e:
                logger.warning(f"[OPENCODE] Chat request error (events may still arrive): {e}")

            # Wait for completion with timeout
            try:
                await asyncio.wait_for(completion_event.wait(), timeout=REQUEST_TIMEOUT)
            except TimeoutError:
                logger.warning("[OPENCODE] Event wait timeout")
            finally:
                event_task.cancel()
                watchdog_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await event_task
                with contextlib.suppress(asyncio.CancelledError):
                    await watchdog_task

        # Raise exception if session was aborted - caller should retry
        if session_aborted:
            raise SessionStallError(abort_reason)

        # Detect misconfigured OpenCode - echoes prompt back instead of responding
        if final_response and final_response.strip() == prompt.strip():
            raise RuntimeError(
                "OpenCode is not configured properly.\n"
                "Run 'opencode' to configure your API provider and credentials."
            )

        return AgentResult(
            messages=messages,
            final_response=final_response,
            tools_used=list(tools_used),
            agent_info=agent_info,
        )

    # -------------------------------------------------------------------------
    # Event Processing
    # -------------------------------------------------------------------------

    def _process_event(self, event: EventListResponse) -> tuple[AgentMessage, str | None] | None:
        """Process SDK event into AgentMessage.

        Returns tuple of (AgentMessage, tool_name) or None if event
        should be ignored.
        """
        match event:
            case EventMessagePartUpdated(properties=props):
                return self._parse_part(props.part)
            case _:
                return None

    def _parse_part(self, part: Part) -> tuple[AgentMessage, str | None] | None:
        """Parse SDK Part type into AgentMessage.

        Returns tuple of (AgentMessage, tool_name) or None if part
        should be ignored.
        """
        match part:
            case StepStartPart() | StepFinishPart():
                return None

            case TextPart(text=text) if text:
                return AgentMessage(role="assistant", content=text), None

            case ToolPart(tool=tool_name, state=ToolStateCompleted(output=output)):
                return AgentMessage(role="tool_result", content=output), None

            case ToolPart(tool=tool_name, state=state):
                inp = getattr(state, "input", None)
                if inp and isinstance(inp, dict):
                    # Convert to Proofloop naming conventions
                    proofloop_name = OPENCODE_TO_PROOFLOOP_TOOLS.get(tool_name, tool_name)
                    normalized_input = _normalize_tool_input(inp)
                    return AgentMessage(
                        role="tool_use",
                        content="",
                        tool_name=proofloop_name,
                        tool_input=normalized_input,
                    ), tool_name
                return None

            case _:
                return None

    # -------------------------------------------------------------------------
    # Streaming
    # -------------------------------------------------------------------------

    async def stream(
        self,
        prompt: str,
        allowed_tools: list[str],  # noqa: ARG002
        cwd: str,
        mcp_servers: dict[str, MCPServerConfig] | None = None,  # noqa: ARG002
    ) -> AsyncIterator[AgentMessage]:
        """Stream agent messages using SDK event stream.

        OpenCode SSE sends cumulative text updates (full message so
        far), not deltas. We buffer assistant messages and only yield on
        completion or when a non-assistant event arrives.
        """
        await self._ensure_server_running(cwd)

        logger.debug(f"Streaming OpenCode agent with prompt: {prompt[:100]}...")

        async with AsyncOpencode(
            base_url=self._base_url,
            timeout=REQUEST_TIMEOUT,
        ) as client:
            # Get config - use OpenCode's configured model/provider
            config = await client.config.get()
            model_id = config.model
            provider_id = self._extract_provider_id(config)

            # If not set in config, fetch defaults from /config/providers
            if not model_id or not provider_id:
                async with httpx.AsyncClient(base_url=self._base_url, timeout=30) as http:
                    resp = await http.get("/config/providers")
                    if resp.status_code == 200:
                        providers_data = resp.json()
                        defaults = providers_data.get("default", {})
                        if not provider_id and defaults:
                            provider_id = next(iter(defaults.keys()), None)
                        if not model_id and provider_id and defaults:
                            model_id = defaults.get(provider_id)

            # Fallback to hardcoded defaults if still not set
            model_id = model_id or "claude-sonnet-4-20250514"
            provider_id = provider_id or "anthropic"

            # Create session
            session = await client.session.create()
            session_id = session.id

            # Start event stream before sending message
            event_stream = await client.event.list()
            async with event_stream:
                # Send message in background
                chat_task = asyncio.create_task(
                    client.session.chat(
                        session_id,
                        model_id=model_id,
                        provider_id=provider_id,
                        parts=[{"type": "text", "text": prompt}],
                        timeout=REQUEST_TIMEOUT,
                    )
                )

                # Buffer for streaming assistant text
                pending_assistant_msg: AgentMessage | None = None

                # Process events
                try:
                    async for event in event_stream:
                        match event:
                            case EventSessionIdle():
                                # Yield any pending assistant message on completion
                                if pending_assistant_msg:
                                    yield pending_assistant_msg
                                break
                            case _:
                                if result := self._process_event(event):
                                    agent_msg = result[0]

                                    if agent_msg.role == "assistant":
                                        # Check if this is a cumulative update or a new message
                                        # Cumulative: new text starts with previous text
                                        if pending_assistant_msg and agent_msg.content:
                                            prev = pending_assistant_msg.content or ""
                                            curr = agent_msg.content
                                            is_cumulative = curr.startswith(prev)

                                            if not is_cumulative:
                                                # New message - flush previous first
                                                yield pending_assistant_msg
                                        # Buffer current message
                                        pending_assistant_msg = agent_msg
                                    else:
                                        # Flush pending assistant message first
                                        if pending_assistant_msg:
                                            yield pending_assistant_msg
                                            pending_assistant_msg = None
                                        # Yield non-assistant message immediately
                                        yield agent_msg
                finally:
                    chat_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await chat_task
