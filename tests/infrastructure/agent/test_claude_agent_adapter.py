from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest

from src.infrastructure.agent.claude_agent_adapter import ClaudeAgentAdapter


@dataclass
class MockTextBlock:
    text: str


@dataclass
class MockToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class MockToolResultBlock:
    tool_use_id: str
    content: str | list[dict[str, Any]] | None = None
    is_error: bool | None = None


@dataclass
class MockAssistantMessage:
    content: list[Any]
    model: str = "claude-opus-4-5-20251101"


@dataclass
class MockResultMessage:
    subtype: str
    duration_ms: int
    duration_api_ms: int
    is_error: bool
    num_turns: int
    session_id: str
    result: str | None = None


@dataclass
class MockSystemMessage:
    subtype: str
    data: dict[str, Any]


class TestClaudeAgentAdapter:
    @pytest.fixture
    def adapter(self) -> ClaudeAgentAdapter:
        return ClaudeAgentAdapter()

    async def test_execute_returns_agent_result(self, adapter: ClaudeAgentAdapter) -> None:
        mock_messages = [
            MockAssistantMessage(content=[MockTextBlock(text="Hello!")]),
            MockResultMessage(
                subtype="success",
                duration_ms=1000,
                duration_api_ms=800,
                is_error=False,
                num_turns=1,
                session_id="test-session",
                result="Hello!",
            ),
        ]

        async def mock_query(*_args: Any, **_kwargs: Any) -> Any:
            for msg in mock_messages:
                yield msg

        with patch("src.infrastructure.agent.claude_agent_adapter.query", mock_query):
            result = await adapter.execute(
                prompt="Say hello",
                allowed_tools=["Read"],
                cwd="/tmp",
            )

        assert result.final_response == "Hello!"
        assert len(result.messages) == 2
        assert result.messages[0].role == "assistant"
        assert result.messages[0].content == "Hello!"

    async def test_execute_tracks_tools_used(self, adapter: ClaudeAgentAdapter) -> None:
        mock_messages = [
            MockAssistantMessage(
                content=[MockToolUseBlock(id="1", name="Read", input={"file": "test.py"})]
            ),
            MockAssistantMessage(
                content=[MockToolResultBlock(tool_use_id="1", content="file content")]
            ),
            MockAssistantMessage(
                content=[MockToolUseBlock(id="2", name="Write", input={"file": "out.py"})]
            ),
            MockAssistantMessage(content=[MockTextBlock(text="Done")]),
            MockResultMessage(
                subtype="success",
                duration_ms=2000,
                duration_api_ms=1800,
                is_error=False,
                num_turns=2,
                session_id="test-session",
                result="Done",
            ),
        ]

        async def mock_query(*_args: Any, **_kwargs: Any) -> Any:
            for msg in mock_messages:
                yield msg

        with patch("src.infrastructure.agent.claude_agent_adapter.query", mock_query):
            result = await adapter.execute(
                prompt="Read and write",
                allowed_tools=["Read", "Write"],
                cwd="/tmp",
            )

        assert set(result.tools_used) == {"Read", "Write"}

    async def test_stream_yields_messages(self, adapter: ClaudeAgentAdapter) -> None:
        mock_messages = [
            MockAssistantMessage(content=[MockTextBlock(text="Step 1")]),
            MockAssistantMessage(content=[MockTextBlock(text="Step 2")]),
        ]

        async def mock_query(*_args: Any, **_kwargs: Any) -> Any:
            for msg in mock_messages:
                yield msg

        with patch("src.infrastructure.agent.claude_agent_adapter.query", mock_query):
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

    async def test_convert_tool_use_message(self, adapter: ClaudeAgentAdapter) -> None:
        mock_messages = [
            MockAssistantMessage(
                content=[
                    MockToolUseBlock(
                        id="tool-1",
                        name="Bash",
                        input={"command": "ls -la"},
                    )
                ]
            ),
        ]

        async def mock_query(*_args: Any, **_kwargs: Any) -> Any:
            for msg in mock_messages:
                yield msg

        with patch("src.infrastructure.agent.claude_agent_adapter.query", mock_query):
            messages = []
            async for msg in adapter.stream(
                prompt="Run command",
                allowed_tools=["Bash"],
                cwd="/tmp",
            ):
                messages.append(msg)

        assert len(messages) == 1
        assert messages[0].role == "tool_use"
        assert messages[0].tool_name == "Bash"
        assert messages[0].tool_input == {"command": "ls -la"}

    async def test_convert_tool_result_message(self, adapter: ClaudeAgentAdapter) -> None:
        mock_messages = [
            MockAssistantMessage(
                content=[
                    MockToolResultBlock(
                        tool_use_id="tool-1",
                        content="command output",
                    )
                ]
            ),
        ]

        async def mock_query(*_args: Any, **_kwargs: Any) -> Any:
            for msg in mock_messages:
                yield msg

        with patch("src.infrastructure.agent.claude_agent_adapter.query", mock_query):
            messages = []
            async for msg in adapter.stream(
                prompt="Get result",
                allowed_tools=[],
                cwd="/tmp",
            ):
                messages.append(msg)

        assert len(messages) == 1
        assert messages[0].role == "tool_result"
        assert messages[0].content == "command output"

    async def test_ignores_system_messages(self, adapter: ClaudeAgentAdapter) -> None:
        mock_messages = [
            MockSystemMessage(subtype="init", data={"tools": ["Read"]}),
            MockAssistantMessage(content=[MockTextBlock(text="Hello")]),
        ]

        async def mock_query(*_args: Any, **_kwargs: Any) -> Any:
            for msg in mock_messages:
                yield msg

        with patch("src.infrastructure.agent.claude_agent_adapter.query", mock_query):
            messages = []
            async for msg in adapter.stream(
                prompt="Hello",
                allowed_tools=[],
                cwd="/tmp",
            ):
                messages.append(msg)

        # System message should be filtered out
        assert len(messages) == 1
        assert messages[0].content == "Hello"

    async def test_handles_empty_content_blocks(self, adapter: ClaudeAgentAdapter) -> None:
        mock_messages = [
            MockAssistantMessage(content=[]),
            MockAssistantMessage(content=[MockTextBlock(text="Final")]),
        ]

        async def mock_query(*_args: Any, **_kwargs: Any) -> Any:
            for msg in mock_messages:
                yield msg

        with patch("src.infrastructure.agent.claude_agent_adapter.query", mock_query):
            messages = []
            async for msg in adapter.stream(
                prompt="Test",
                allowed_tools=[],
                cwd="/tmp",
            ):
                messages.append(msg)

        # Empty content block message should be filtered out
        assert len(messages) == 1
        assert messages[0].content == "Final"
