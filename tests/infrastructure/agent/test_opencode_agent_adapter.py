from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from opencode_ai.types import StepFinishPart, StepStartPart, TextPart, ToolPart
from opencode_ai.types.tool_state_completed import ToolStateCompleted
from opencode_ai.types.tool_state_running import ToolStateRunning

from src.domain.ports.agent_port import AgentMessage
from src.infrastructure.agent.opencode_agent_adapter import OpenCodeAgentAdapter


class TestOpenCodeAgentAdapter:
    @pytest.fixture
    def mock_opencode_installed(self) -> Any:
        """Mock that opencode CLI is installed."""
        with patch(
            "src.infrastructure.agent.opencode_agent_adapter._check_opencode_installed",
            return_value=True,
        ):
            yield

    @pytest.fixture
    def adapter(self, mock_opencode_installed: Any) -> OpenCodeAgentAdapter:
        return OpenCodeAgentAdapter(port=4096)

    async def test_execute_returns_agent_result(self, adapter: OpenCodeAgentAdapter) -> None:
        """Test that execute returns a properly structured AgentResult."""
        mock_config = MagicMock()
        mock_config.model = "claude-sonnet-4-20250514"
        mock_config.provider = {"anthropic": {}}

        mock_session = MagicMock()
        mock_session.id = "test-session-123"

        mock_event_stream = AsyncMock()
        mock_event_stream.__aenter__ = AsyncMock(return_value=mock_event_stream)
        mock_event_stream.__aexit__ = AsyncMock(return_value=None)

        mock_text_part = MagicMock()
        mock_text_part.text = "Hello from OpenCode!"

        mock_message_event = MagicMock()
        mock_message_event.__class__.__name__ = "EventMessagePartUpdated"
        mock_message_event.properties = MagicMock()
        mock_message_event.properties.part = mock_text_part

        mock_idle_event = MagicMock()
        mock_idle_event.__class__.__name__ = "EventSessionIdle"

        async def mock_event_iterator() -> Any:
            yield mock_message_event
            yield mock_idle_event

        mock_event_stream.__aiter__ = lambda self: mock_event_iterator()

        mock_client = AsyncMock()
        mock_client.config.get = AsyncMock(return_value=mock_config)
        mock_client.session.create = AsyncMock(return_value=mock_session)
        mock_client.session.chat = AsyncMock(return_value=None)
        mock_client.event.list = AsyncMock(return_value=mock_event_stream)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        # Mock httpx client for session creation (bypasses SDK due to empty body bug)
        mock_http_response = MagicMock()
        mock_http_response.raise_for_status = MagicMock()
        mock_http_response.json = MagicMock(return_value={"id": "test-session-123"})

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_http_response)
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(adapter, "_ensure_server_running", new_callable=AsyncMock),
            patch.object(adapter, "_parse_part") as mock_parse_part,
            patch(
                "src.infrastructure.agent.opencode_agent_adapter.AsyncOpencode",
                return_value=mock_client,
            ),
            patch(
                "src.infrastructure.agent.opencode_agent_adapter.httpx.AsyncClient",
                return_value=mock_http_client,
            ),
            patch(
                "src.infrastructure.agent.opencode_agent_adapter.EventMessagePartUpdated",
                type(mock_message_event),
            ),
            patch(
                "src.infrastructure.agent.opencode_agent_adapter.EventSessionIdle",
                type(mock_idle_event),
            ),
        ):
            mock_parse_part.side_effect = [
                (AgentMessage(role="assistant", content="Hello from OpenCode!"), None),
                None,
            ]

            result = await adapter.execute(
                prompt="Say hello",
                allowed_tools=["Read"],
                cwd="/tmp",
            )

        assert result.final_response == "Hello from OpenCode!"
        assert result.agent_info is not None
        assert result.agent_info.provider == "opencode"
        assert result.agent_info.model == "claude-sonnet-4-20250514"

    async def test_health_check_returns_true_on_success(
        self, adapter: OpenCodeAgentAdapter
    ) -> None:
        """Test that _health_check returns True when server responds with
        200."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await adapter._health_check()

        assert result is True

    async def test_health_check_returns_false_on_error(self, adapter: OpenCodeAgentAdapter) -> None:
        """Test that _health_check returns False when server is unreachable."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await adapter._health_check()

        assert result is False

    async def test_health_check_returns_false_on_non_200(
        self, adapter: OpenCodeAgentAdapter
    ) -> None:
        """Test that _health_check returns False for non-200 status codes."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await adapter._health_check()

        assert result is False

    def test_parse_part_returns_assistant_message_for_text(
        self, adapter: OpenCodeAgentAdapter
    ) -> None:
        """Test that _parse_part correctly handles TextPart."""
        text_part = MagicMock(spec=TextPart)
        text_part.text = "Test message"

        result = adapter._parse_part(text_part)

        assert result is not None
        message, tool_name = result
        assert message.role == "assistant"
        assert message.content == "Test message"
        assert tool_name is None

    def test_parse_part_returns_none_for_empty_text(self, adapter: OpenCodeAgentAdapter) -> None:
        """Test that _parse_part returns None for empty TextPart."""
        text_part = MagicMock(spec=TextPart)
        text_part.text = ""

        result = adapter._parse_part(text_part)

        assert result is None

    def test_parse_part_returns_tool_use_for_tool_part(self, adapter: OpenCodeAgentAdapter) -> None:
        """Test that _parse_part correctly handles ToolPart in running
        state."""
        running_state = MagicMock(spec=ToolStateRunning)
        running_state.input = {"filePath": "test.py"}

        tool_part = MagicMock(spec=ToolPart)
        tool_part.tool = "read"
        tool_part.state = running_state

        result = adapter._parse_part(tool_part)

        assert result is not None
        message, tool_name = result
        assert message.role == "tool_use"
        # Tool name is converted to Proofloop format (capitalized)
        assert message.tool_name == "Read"
        # Params are converted from camelCase to snake_case
        assert message.tool_input == {"file_path": "test.py"}
        # Original tool name is preserved for tracking
        assert tool_name == "read"

    def test_parse_part_returns_tool_result_for_completed_tool(
        self, adapter: OpenCodeAgentAdapter
    ) -> None:
        """Test that _parse_part correctly handles ToolPart with completed
        state."""
        completed_state = MagicMock(spec=ToolStateCompleted)
        completed_state.output = "file contents here"

        tool_part = MagicMock(spec=ToolPart)
        tool_part.tool = "read"
        tool_part.state = completed_state

        result = adapter._parse_part(tool_part)

        assert result is not None
        message, tool_name = result
        assert message.role == "tool_result"
        assert message.content == "file contents here"
        assert tool_name is None

    def test_parse_part_returns_none_for_step_start_part(
        self, adapter: OpenCodeAgentAdapter
    ) -> None:
        """Test that _parse_part returns None for StepStartPart."""
        step_start = MagicMock(spec=StepStartPart)

        result = adapter._parse_part(step_start)

        assert result is None

    def test_parse_part_returns_none_for_step_finish_part(
        self, adapter: OpenCodeAgentAdapter
    ) -> None:
        """Test that _parse_part returns None for StepFinishPart."""
        step_finish = MagicMock(spec=StepFinishPart)

        result = adapter._parse_part(step_finish)

        assert result is None

    def test_adapter_raises_error_when_opencode_not_installed(self) -> None:
        """Test that adapter raises RuntimeError when opencode CLI is not
        found."""
        with patch(
            "src.infrastructure.agent.opencode_agent_adapter._check_opencode_installed",
            return_value=False,
        ):
            with pytest.raises(RuntimeError) as exc_info:
                OpenCodeAgentAdapter()

            assert "OpenCode CLI not found" in str(exc_info.value)

    async def test_cleanup_terminates_server_process(self, adapter: OpenCodeAgentAdapter) -> None:
        """Test that cleanup terminates the server process if running."""
        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.terminate = MagicMock()
        mock_process.wait = AsyncMock()

        adapter._server_process = mock_process

        await adapter.cleanup()

        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once()
        assert adapter._server_process is None

    async def test_cleanup_does_nothing_when_no_process(
        self, adapter: OpenCodeAgentAdapter
    ) -> None:
        """Test that cleanup does nothing when no server process exists."""
        adapter._server_process = None

        await adapter.cleanup()

        assert adapter._server_process is None

    def test_tool_name_mapping(self, adapter: OpenCodeAgentAdapter) -> None:
        """Test that tool name mapping works correctly."""
        from src.infrastructure.agent.opencode_agent_adapter import (
            OPENCODE_TO_PROOFLOOP_TOOLS,
            PROOFLOOP_TO_OPENCODE_TOOLS,
        )

        assert PROOFLOOP_TO_OPENCODE_TOOLS["Read"] == "read"
        assert PROOFLOOP_TO_OPENCODE_TOOLS["Edit"] == "edit"
        assert PROOFLOOP_TO_OPENCODE_TOOLS["Write"] == "write"
        assert PROOFLOOP_TO_OPENCODE_TOOLS["Bash"] == "bash"

        assert OPENCODE_TO_PROOFLOOP_TOOLS["read"] == "Read"
        assert OPENCODE_TO_PROOFLOOP_TOOLS["edit"] == "Edit"
        assert OPENCODE_TO_PROOFLOOP_TOOLS["write"] == "Write"
        assert OPENCODE_TO_PROOFLOOP_TOOLS["bash"] == "Bash"

    async def test_stream_yields_messages(self, adapter: OpenCodeAgentAdapter) -> None:
        """Test that stream yields messages from the event stream."""
        from opencode_ai.types.event_list_response import (
            EventMessagePartUpdated,
            EventSessionIdle,
        )

        mock_config = MagicMock()
        mock_config.model = "claude-sonnet-4-20250514"
        mock_config.provider = {"anthropic": {}}

        mock_session = MagicMock()
        mock_session.id = "test-session-123"

        mock_text_part_1 = MagicMock(spec=TextPart)
        mock_text_part_1.text = "Step 1"
        mock_text_part_2 = MagicMock(spec=TextPart)
        mock_text_part_2.text = "Step 2"

        # Create mock events using spec to ensure isinstance checks work
        mock_event_1 = MagicMock(spec=EventMessagePartUpdated)
        mock_event_1.properties = MagicMock()
        mock_event_1.properties.part = mock_text_part_1

        mock_event_2 = MagicMock(spec=EventMessagePartUpdated)
        mock_event_2.properties = MagicMock()
        mock_event_2.properties.part = mock_text_part_2

        mock_idle_event = MagicMock(spec=EventSessionIdle)

        mock_event_stream = AsyncMock()
        mock_event_stream.__aenter__ = AsyncMock(return_value=mock_event_stream)
        mock_event_stream.__aexit__ = AsyncMock(return_value=None)

        async def mock_event_iterator() -> Any:
            yield mock_event_1
            yield mock_event_2
            yield mock_idle_event

        mock_event_stream.__aiter__ = lambda self: mock_event_iterator()

        mock_client = AsyncMock()
        mock_client.config.get = AsyncMock(return_value=mock_config)
        mock_client.session.create = AsyncMock(return_value=mock_session)
        mock_client.session.chat = AsyncMock(return_value=None)
        mock_client.event.list = AsyncMock(return_value=mock_event_stream)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(adapter, "_ensure_server_running", new_callable=AsyncMock),
            patch.object(adapter, "_process_event") as mock_process_event,
            patch(
                "src.infrastructure.agent.opencode_agent_adapter.AsyncOpencode",
                return_value=mock_client,
            ),
        ):
            mock_process_event.side_effect = [
                (AgentMessage(role="assistant", content="Step 1"), None),
                (AgentMessage(role="assistant", content="Step 2"), None),
                None,  # For the idle event (returns None from _process_event)
            ]

            messages = []
            async for msg in adapter.stream(
                prompt="Do steps",
                allowed_tools=[],
                cwd="/tmp",
            ):
                messages.append(msg)

        assert len(messages) == 2
        assert messages[0].content == "Step 1"
        assert messages[1].content == "Step 2"

    async def test_wait_for_server_timeout(self, adapter: OpenCodeAgentAdapter) -> None:
        """Test that _wait_for_server raises RuntimeError on timeout."""
        with (
            patch.object(adapter, "_health_check", new_callable=AsyncMock) as mock_health,
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch(
                "src.infrastructure.agent.opencode_agent_adapter.SERVER_STARTUP_TIMEOUT",
                0.1,
            ),
        ):
            mock_health.return_value = False

            with pytest.raises(RuntimeError) as exc_info:
                await adapter._wait_for_server()

            assert "failed to start" in str(exc_info.value)
