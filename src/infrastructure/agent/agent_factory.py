from src.domain.ports.agent_port import AgentPort
from src.domain.value_objects.agent_provider import AgentProvider


def create_agent(provider: AgentProvider) -> AgentPort:
    """Create an agent adapter for the specified provider.

    Args:
        provider: The agent provider to use (claude, codex, opencode)

    Returns:
        An AgentPort implementation for the specified provider

    Raises:
        ValueError: If the provider is not supported
        RuntimeError: If the required CLI tool is not installed
    """
    match provider:
        case AgentProvider.CLAUDE:
            from src.infrastructure.agent.claude_agent_adapter import ClaudeAgentAdapter

            return ClaudeAgentAdapter()

        case AgentProvider.CODEX:
            from src.infrastructure.agent.codex_agent_adapter import CodexAgentAdapter

            return CodexAgentAdapter()

        case AgentProvider.OPENCODE:
            from src.infrastructure.agent.opencode_agent_adapter import OpenCodeAgentAdapter

            return OpenCodeAgentAdapter()

        case _:
            raise ValueError(f"Unsupported agent provider: {provider}")
