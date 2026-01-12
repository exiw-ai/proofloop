from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable

from pydantic import BaseModel

from src.domain.value_objects.mcp_types import MCPServerConfig

# Callback for observing agent messages in real-time
MessageCallback = Callable[["AgentMessage"], None]


class SessionStallError(Exception):
    """Raised when an agent session stalls and is aborted.

    This indicates infrastructure failure (timeout), not agent logic
    error. Should be retried without counting toward stagnation.
    """


class AgentMessage(BaseModel):
    """A message from the agent during execution."""

    role: str  # "assistant" | "tool_use" | "tool_result" | "thought" | "status"
    content: str
    tool_name: str | None = None
    tool_input: dict[str, object] | None = None


class AgentInfo(BaseModel):
    """Information about the agent being used."""

    provider: str  # "claude" | "codex" | "opencode"
    model: str | None = None  # e.g., "claude-sonnet-4-20250514", "gpt-5.2-codex"
    model_provider: str | None = None  # e.g., "anthropic", "openai"


class AgentResult(BaseModel):
    """Result of agent execution."""

    messages: list[AgentMessage]
    final_response: str
    tools_used: list[str]
    agent_info: AgentInfo | None = None


class AgentPort(ABC):
    """Port for agent execution."""

    @abstractmethod
    async def execute(
        self,
        prompt: str,
        allowed_tools: list[str],
        cwd: str,
        on_message: MessageCallback | None = None,
        mcp_servers: dict[str, MCPServerConfig] | None = None,
    ) -> AgentResult:
        """Execute agent with given prompt and allowed tools.

        Args:
            prompt: The task prompt for the agent.
            allowed_tools: List of tool names the agent can use.
            cwd: Working directory for execution.
            on_message: Optional callback invoked for each message during execution.
            mcp_servers: Optional dict of MCP server configs to enable.
        """

    @abstractmethod
    def stream(
        self,
        prompt: str,
        allowed_tools: list[str],
        cwd: str,
        mcp_servers: dict[str, MCPServerConfig] | None = None,
    ) -> AsyncIterator[AgentMessage]:
        """Stream agent messages.

        Args:
            prompt: The task prompt for the agent.
            allowed_tools: List of tool names the agent can use.
            cwd: Working directory for execution.
            mcp_servers: Optional dict of MCP server configs to enable.
        """
