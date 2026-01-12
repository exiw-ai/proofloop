from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.ports.agent_port import AgentMessage
from src.infrastructure.agent.codex_agent_adapter import CodexAgentAdapter


class TestCodexAgentAdapter:
    @pytest.fixture
    def mock_codex_installed(self) -> Any:
        """Mock that codex CLI is installed."""
        with patch("shutil.which", return_value="/usr/local/bin/codex"):
            yield

    @pytest.fixture
    def adapter(self, mock_codex_installed: Any) -> CodexAgentAdapter:
        """Create a CodexAgentAdapter with mocked SDK."""
        with patch("src.infrastructure.agent.codex_agent_adapter.Codex"):
            return CodexAgentAdapter()

    async def test_execute_returns_agent_result(self, adapter: CodexAgentAdapter) -> None:
        """Test that execute returns a properly structured AgentResult."""
        from codex_sdk.events import ItemCompletedEvent, TurnCompletedEvent
        from codex_sdk.items import AgentMessageItem

        mock_message_item = MagicMock(spec=AgentMessageItem)
        mock_message_item.text = "Hello from Codex!"

        mock_completed_event = MagicMock(spec=ItemCompletedEvent)
        mock_completed_event.item = mock_message_item

        mock_turn_completed = MagicMock(spec=TurnCompletedEvent)

        mock_streamed = MagicMock()

        async def mock_events() -> Any:
            yield mock_completed_event
            yield mock_turn_completed

        mock_streamed.events = mock_events()

        mock_thread = MagicMock()
        mock_thread.run_streamed = AsyncMock(return_value=mock_streamed)

        adapter._codex.start_thread = MagicMock(return_value=mock_thread)

        result = await adapter.execute(
            prompt="Say hello",
            allowed_tools=["Read"],
            cwd="/tmp",
        )

        assert result.final_response == "Hello from Codex!"
        assert len(result.messages) == 1
        assert result.messages[0].role == "assistant"
        assert result.messages[0].content == "Hello from Codex!"
        assert result.agent_info is not None
        assert result.agent_info.provider == "codex"
        assert result.agent_info.model == "codex-cli"
        assert result.agent_info.model_provider == "openai"

    async def test_execute_tracks_tools_used(self, adapter: CodexAgentAdapter) -> None:
        """Test that execute tracks tools used correctly."""
        from codex_sdk.events import (
            ItemCompletedEvent,
            ItemStartedEvent,
            TurnCompletedEvent,
        )
        from codex_sdk.items import AgentMessageItem, CommandExecutionItem

        mock_command_item = MagicMock(spec=CommandExecutionItem)
        mock_command_item.command = "ls -la"
        mock_command_item.aggregated_output = "file1.txt\nfile2.txt"

        mock_started_event = MagicMock(spec=ItemStartedEvent)
        mock_started_event.item = mock_command_item

        mock_completed_event = MagicMock(spec=ItemCompletedEvent)
        mock_completed_event.item = mock_command_item

        mock_message_item = MagicMock(spec=AgentMessageItem)
        mock_message_item.text = "Done"

        mock_message_completed = MagicMock(spec=ItemCompletedEvent)
        mock_message_completed.item = mock_message_item

        mock_turn_completed = MagicMock(spec=TurnCompletedEvent)

        mock_streamed = MagicMock()

        async def mock_events() -> Any:
            yield mock_started_event
            yield mock_completed_event
            yield mock_message_completed
            yield mock_turn_completed

        mock_streamed.events = mock_events()

        mock_thread = MagicMock()
        mock_thread.run_streamed = AsyncMock(return_value=mock_streamed)

        adapter._codex.start_thread = MagicMock(return_value=mock_thread)

        result = await adapter.execute(
            prompt="List files",
            allowed_tools=["Bash"],
            cwd="/tmp",
        )

        assert "Bash" in result.tools_used

    async def test_execute_handles_command_execution(self, adapter: CodexAgentAdapter) -> None:
        """Test that CommandExecutionItem is processed correctly."""
        from codex_sdk.events import ItemCompletedEvent, ItemStartedEvent, TurnCompletedEvent
        from codex_sdk.items import CommandExecutionItem

        mock_command_item = MagicMock(spec=CommandExecutionItem)
        mock_command_item.command = "echo hello"
        mock_command_item.aggregated_output = "hello"
        mock_command_item.exit_code = 0
        mock_command_item.status = "completed"

        mock_started = MagicMock(spec=ItemStartedEvent)
        mock_started.item = mock_command_item

        mock_completed = MagicMock(spec=ItemCompletedEvent)
        mock_completed.item = mock_command_item

        mock_turn_completed = MagicMock(spec=TurnCompletedEvent)

        mock_streamed = MagicMock()

        async def mock_events() -> Any:
            yield mock_started
            yield mock_completed
            yield mock_turn_completed

        mock_streamed.events = mock_events()

        mock_thread = MagicMock()
        mock_thread.run_streamed = AsyncMock(return_value=mock_streamed)

        adapter._codex.start_thread = MagicMock(return_value=mock_thread)

        result = await adapter.execute(
            prompt="Run echo",
            allowed_tools=["Bash"],
            cwd="/tmp",
        )

        assert len(result.messages) == 2
        assert result.messages[0].role == "tool_use"
        assert result.messages[0].tool_name == "Bash"
        assert result.messages[0].tool_input == {"command": "echo hello"}
        assert result.messages[1].role == "tool"
        assert result.messages[1].content == "hello"

    async def test_execute_handles_mcp_tool_call(self, adapter: CodexAgentAdapter) -> None:
        """Test that McpToolCallItem is processed correctly."""
        from codex_sdk.events import ItemCompletedEvent, TurnCompletedEvent
        from codex_sdk.items import McpToolCallItem

        mock_result = MagicMock()
        mock_result.content = "file contents here"

        mock_mcp_item = MagicMock(spec=McpToolCallItem)
        mock_mcp_item.server = "filesystem"
        mock_mcp_item.tool = "read_file"
        mock_mcp_item.arguments = {"path": "/tmp/test.txt"}
        mock_mcp_item.result = mock_result
        mock_mcp_item.error = None

        mock_completed = MagicMock(spec=ItemCompletedEvent)
        mock_completed.item = mock_mcp_item

        mock_turn_completed = MagicMock(spec=TurnCompletedEvent)

        mock_streamed = MagicMock()

        async def mock_events() -> Any:
            yield mock_completed
            yield mock_turn_completed

        mock_streamed.events = mock_events()

        mock_thread = MagicMock()
        mock_thread.run_streamed = AsyncMock(return_value=mock_streamed)

        adapter._codex.start_thread = MagicMock(return_value=mock_thread)

        result = await adapter.execute(
            prompt="Read file",
            allowed_tools=[],
            cwd="/tmp",
        )

        assert "filesystem:read_file" in result.tools_used
        assert len(result.messages) == 2
        assert result.messages[0].role == "tool_use"
        assert result.messages[0].tool_name == "filesystem:read_file"
        assert result.messages[1].role == "tool"
        assert result.messages[1].content == "file contents here"

    async def test_execute_handles_mcp_tool_error(self, adapter: CodexAgentAdapter) -> None:
        """Test that McpToolCallItem errors are processed correctly."""
        from codex_sdk.events import ItemCompletedEvent, TurnCompletedEvent
        from codex_sdk.items import McpToolCallItem

        mock_error = MagicMock()
        mock_error.message = "File not found"

        mock_mcp_item = MagicMock(spec=McpToolCallItem)
        mock_mcp_item.server = "filesystem"
        mock_mcp_item.tool = "read_file"
        mock_mcp_item.arguments = {"path": "/nonexistent"}
        mock_mcp_item.result = None
        mock_mcp_item.error = mock_error

        mock_completed = MagicMock(spec=ItemCompletedEvent)
        mock_completed.item = mock_mcp_item

        mock_turn_completed = MagicMock(spec=TurnCompletedEvent)

        mock_streamed = MagicMock()

        async def mock_events() -> Any:
            yield mock_completed
            yield mock_turn_completed

        mock_streamed.events = mock_events()

        mock_thread = MagicMock()
        mock_thread.run_streamed = AsyncMock(return_value=mock_streamed)

        adapter._codex.start_thread = MagicMock(return_value=mock_thread)

        result = await adapter.execute(
            prompt="Read file",
            allowed_tools=[],
            cwd="/tmp",
        )

        assert len(result.messages) == 2
        assert result.messages[1].role == "tool"
        assert "Error: File not found" in result.messages[1].content

    async def test_execute_handles_reasoning_item(self, adapter: CodexAgentAdapter) -> None:
        """Test that ReasoningItem is processed correctly."""
        from codex_sdk.events import ItemCompletedEvent, TurnCompletedEvent
        from codex_sdk.items import AgentMessageItem, ReasoningItem

        mock_reasoning = MagicMock(spec=ReasoningItem)
        mock_reasoning.text = "I should think about this..."

        mock_reasoning_event = MagicMock(spec=ItemCompletedEvent)
        mock_reasoning_event.item = mock_reasoning

        mock_message = MagicMock(spec=AgentMessageItem)
        mock_message.text = "Here is my answer"

        mock_message_event = MagicMock(spec=ItemCompletedEvent)
        mock_message_event.item = mock_message

        mock_turn_completed = MagicMock(spec=TurnCompletedEvent)

        messages_received: list[AgentMessage] = []

        def on_message(msg: AgentMessage) -> None:
            messages_received.append(msg)

        mock_streamed = MagicMock()

        async def mock_events() -> Any:
            yield mock_reasoning_event
            yield mock_message_event
            yield mock_turn_completed

        mock_streamed.events = mock_events()

        mock_thread = MagicMock()
        mock_thread.run_streamed = AsyncMock(return_value=mock_streamed)

        adapter._codex.start_thread = MagicMock(return_value=mock_thread)

        result = await adapter.execute(
            prompt="Think and answer",
            allowed_tools=[],
            cwd="/tmp",
            on_message=on_message,
        )

        assert result.final_response == "Here is my answer"
        assert len(result.messages) == 1
        thought_messages = [m for m in messages_received if m.role == "thought"]
        assert len(thought_messages) == 1
        assert thought_messages[0].content == "I should think about this..."

    async def test_execute_raises_on_turn_failed(self, adapter: CodexAgentAdapter) -> None:
        """Test that TurnFailedEvent raises RuntimeError."""
        from codex_sdk.events import TurnFailedEvent

        mock_error = MagicMock()
        mock_error.message = "Something went wrong"

        mock_turn_failed = MagicMock(spec=TurnFailedEvent)
        mock_turn_failed.error = mock_error

        mock_streamed = MagicMock()

        async def mock_events() -> Any:
            yield mock_turn_failed

        mock_streamed.events = mock_events()

        mock_thread = MagicMock()
        mock_thread.run_streamed = AsyncMock(return_value=mock_streamed)

        adapter._codex.start_thread = MagicMock(return_value=mock_thread)

        with pytest.raises(RuntimeError) as exc_info:
            await adapter.execute(
                prompt="Fail",
                allowed_tools=[],
                cwd="/tmp",
            )

        assert "Something went wrong" in str(exc_info.value)

    async def test_execute_retries_on_rate_limit(self, adapter: CodexAgentAdapter) -> None:
        """Test that execute retries on rate limit errors."""
        from codex_sdk.events import ItemCompletedEvent, TurnCompletedEvent
        from codex_sdk.items import AgentMessageItem

        call_count = 0

        async def mock_run_streamed(prompt: str) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Rate limit exceeded")

            mock_item = MagicMock(spec=AgentMessageItem)
            mock_item.text = "Success after retry"

            mock_completed = MagicMock(spec=ItemCompletedEvent)
            mock_completed.item = mock_item

            mock_turn = MagicMock(spec=TurnCompletedEvent)

            mock_streamed = MagicMock()

            async def events() -> Any:
                yield mock_completed
                yield mock_turn

            mock_streamed.events = events()
            return mock_streamed

        mock_thread = MagicMock()
        mock_thread.run_streamed = mock_run_streamed

        adapter._codex.start_thread = MagicMock(return_value=mock_thread)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await adapter.execute(
                prompt="Test",
                allowed_tools=[],
                cwd="/tmp",
            )

        assert call_count == 2
        assert result.final_response == "Success after retry"

    async def test_execute_retries_on_connection_error(self, adapter: CodexAgentAdapter) -> None:
        """Test that execute retries on connection errors."""
        from codex_sdk.events import ItemCompletedEvent, TurnCompletedEvent
        from codex_sdk.items import AgentMessageItem

        call_count = 0

        async def mock_run_streamed(prompt: str) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Connection timeout")

            mock_item = MagicMock(spec=AgentMessageItem)
            mock_item.text = "Success"

            mock_completed = MagicMock(spec=ItemCompletedEvent)
            mock_completed.item = mock_item

            mock_turn = MagicMock(spec=TurnCompletedEvent)

            mock_streamed = MagicMock()

            async def events() -> Any:
                yield mock_completed
                yield mock_turn

            mock_streamed.events = events()
            return mock_streamed

        mock_thread = MagicMock()
        mock_thread.run_streamed = mock_run_streamed

        adapter._codex.start_thread = MagicMock(return_value=mock_thread)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await adapter.execute(
                prompt="Test",
                allowed_tools=[],
                cwd="/tmp",
            )

        assert call_count == 2
        assert result.final_response == "Success"

    async def test_execute_raises_after_max_retries(self, adapter: CodexAgentAdapter) -> None:
        """Test that execute raises after max retries exceeded."""
        from tenacity import RetryError

        async def mock_run_streamed(prompt: str) -> Any:
            raise Exception("Rate limit exceeded")

        mock_thread = MagicMock()
        mock_thread.run_streamed = mock_run_streamed

        adapter._codex.start_thread = MagicMock(return_value=mock_thread)

        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(RetryError),
        ):
            await adapter.execute(
                prompt="Test",
                allowed_tools=[],
                cwd="/tmp",
            )

    async def test_execute_does_not_retry_non_retryable_errors(
        self, adapter: CodexAgentAdapter
    ) -> None:
        """Test that execute does not retry non-retryable errors."""
        call_count = 0

        async def mock_run_streamed(prompt: str) -> Any:
            nonlocal call_count
            call_count += 1
            raise Exception("Invalid API key")

        mock_thread = MagicMock()
        mock_thread.run_streamed = mock_run_streamed

        adapter._codex.start_thread = MagicMock(return_value=mock_thread)

        with pytest.raises(Exception) as exc_info:
            await adapter.execute(
                prompt="Test",
                allowed_tools=[],
                cwd="/tmp",
            )

        assert call_count == 1
        assert "Invalid API key" in str(exc_info.value)

    async def test_stream_yields_messages(self, adapter: CodexAgentAdapter) -> None:
        """Test that stream yields messages from execute."""
        from codex_sdk.events import ItemCompletedEvent, TurnCompletedEvent
        from codex_sdk.items import AgentMessageItem

        mock_item1 = MagicMock(spec=AgentMessageItem)
        mock_item1.text = "Step 1"

        mock_item2 = MagicMock(spec=AgentMessageItem)
        mock_item2.text = "Step 2"

        mock_event1 = MagicMock(spec=ItemCompletedEvent)
        mock_event1.item = mock_item1

        mock_event2 = MagicMock(spec=ItemCompletedEvent)
        mock_event2.item = mock_item2

        mock_turn = MagicMock(spec=TurnCompletedEvent)

        mock_streamed = MagicMock()

        async def mock_events() -> Any:
            yield mock_event1
            yield mock_event2
            yield mock_turn

        mock_streamed.events = mock_events()

        mock_thread = MagicMock()
        mock_thread.run_streamed = AsyncMock(return_value=mock_streamed)

        adapter._codex.start_thread = MagicMock(return_value=mock_thread)

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

    async def test_execute_truncates_long_command_output(self, adapter: CodexAgentAdapter) -> None:
        """Test that long command output is truncated."""
        from codex_sdk.events import ItemCompletedEvent, TurnCompletedEvent
        from codex_sdk.items import CommandExecutionItem

        long_output = "x" * 1000

        mock_command_item = MagicMock(spec=CommandExecutionItem)
        mock_command_item.command = "cat big_file"
        mock_command_item.aggregated_output = long_output
        mock_command_item.exit_code = 0
        mock_command_item.status = "completed"

        mock_completed = MagicMock(spec=ItemCompletedEvent)
        mock_completed.item = mock_command_item

        mock_turn = MagicMock(spec=TurnCompletedEvent)

        mock_streamed = MagicMock()

        async def mock_events() -> Any:
            yield mock_completed
            yield mock_turn

        mock_streamed.events = mock_events()

        mock_thread = MagicMock()
        mock_thread.run_streamed = AsyncMock(return_value=mock_streamed)

        adapter._codex.start_thread = MagicMock(return_value=mock_thread)

        result = await adapter.execute(
            prompt="Cat file",
            allowed_tools=["Bash"],
            cwd="/tmp",
        )

        tool_message = result.messages[0]
        assert len(tool_message.content) == 503
        assert tool_message.content.endswith("...")

    async def test_execute_invokes_callback(self, adapter: CodexAgentAdapter) -> None:
        """Test that on_message callback is invoked for each message."""
        from codex_sdk.events import ItemCompletedEvent, TurnCompletedEvent
        from codex_sdk.items import AgentMessageItem

        mock_item = MagicMock(spec=AgentMessageItem)
        mock_item.text = "Hello"

        mock_event = MagicMock(spec=ItemCompletedEvent)
        mock_event.item = mock_item

        mock_turn = MagicMock(spec=TurnCompletedEvent)

        mock_streamed = MagicMock()

        async def mock_events() -> Any:
            yield mock_event
            yield mock_turn

        mock_streamed.events = mock_events()

        mock_thread = MagicMock()
        mock_thread.run_streamed = AsyncMock(return_value=mock_streamed)

        adapter._codex.start_thread = MagicMock(return_value=mock_thread)

        received_messages: list[AgentMessage] = []

        def callback(msg: AgentMessage) -> None:
            received_messages.append(msg)

        await adapter.execute(
            prompt="Hello",
            allowed_tools=[],
            cwd="/tmp",
            on_message=callback,
        )

        assert len(received_messages) == 1
        assert received_messages[0].content == "Hello"
        assert received_messages[0].role == "assistant"

    async def test_execute_handles_empty_message(self, adapter: CodexAgentAdapter) -> None:
        """Test that empty AgentMessageItem text is handled."""
        from codex_sdk.events import ItemCompletedEvent, TurnCompletedEvent
        from codex_sdk.items import AgentMessageItem

        mock_empty_item = MagicMock(spec=AgentMessageItem)
        mock_empty_item.text = ""

        mock_item = MagicMock(spec=AgentMessageItem)
        mock_item.text = "Real message"

        mock_empty_event = MagicMock(spec=ItemCompletedEvent)
        mock_empty_event.item = mock_empty_item

        mock_event = MagicMock(spec=ItemCompletedEvent)
        mock_event.item = mock_item

        mock_turn = MagicMock(spec=TurnCompletedEvent)

        mock_streamed = MagicMock()

        async def mock_events() -> Any:
            yield mock_empty_event
            yield mock_event
            yield mock_turn

        mock_streamed.events = mock_events()

        mock_thread = MagicMock()
        mock_thread.run_streamed = AsyncMock(return_value=mock_streamed)

        adapter._codex.start_thread = MagicMock(return_value=mock_thread)

        result = await adapter.execute(
            prompt="Test",
            allowed_tools=[],
            cwd="/tmp",
        )

        assert len(result.messages) == 1
        assert result.messages[0].content == "Real message"

    def test_process_event_ignores_unknown_item_types(self, adapter: CodexAgentAdapter) -> None:
        """Test that _process_completed_item ignores unknown item types."""
        messages: list[AgentMessage] = []
        tools_used: set[str] = set()

        unknown_item = MagicMock()
        unknown_item.__class__.__name__ = "UnknownItem"

        adapter._process_completed_item(unknown_item, messages, tools_used, None)

        assert len(messages) == 0
        assert len(tools_used) == 0
