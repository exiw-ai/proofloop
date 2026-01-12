import shutil

from src.domain.ports.agent_port import AgentPort
from src.domain.value_objects.agent_provider import AgentProvider


class ProviderNotConfiguredError(Exception):
    """Raised when an agent provider is not properly configured."""

    def __init__(self, provider: str, setup_instructions: str) -> None:
        self.provider = provider
        self.setup_instructions = setup_instructions
        super().__init__(f"{provider} is not configured. {setup_instructions}")


def validate_provider_setup(provider: AgentProvider) -> None:
    """Validate that the agent provider is properly set up.

    Args:
        provider: The agent provider to validate

    Raises:
        ProviderNotConfiguredError: If the provider CLI is not installed
    """
    match provider:
        case AgentProvider.CLAUDE:
            if not shutil.which("claude"):
                raise ProviderNotConfiguredError(
                    "Claude Code",
                    "Install and login: npm i -g @anthropic-ai/claude-code && claude login",
                )

        case AgentProvider.CODEX:
            if not shutil.which("codex"):
                raise ProviderNotConfiguredError(
                    "Codex",
                    "Install and login: npm i -g @openai/codex && codex",
                )

        case AgentProvider.OPENCODE:
            if not shutil.which("opencode"):
                raise ProviderNotConfiguredError(
                    "OpenCode",
                    "Install and setup: npm i -g opencode-ai@latest && opencode",
                )


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
