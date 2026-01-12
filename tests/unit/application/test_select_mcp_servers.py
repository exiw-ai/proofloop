"""Tests for SelectMCPServers use case."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.use_cases.select_mcp_servers import MCPSuggestion, SelectMCPServers
from src.domain.entities.budget import Budget
from src.domain.entities.task import Task
from src.domain.ports.agent_port import AgentResult
from src.domain.value_objects.mcp_types import (
    MCPInstallSource,
    MCPServerRegistry,
    MCPServerTemplate,
    MCPServerType,
)


@pytest.fixture
def sample_registry() -> MCPServerRegistry:
    """Create a sample MCP registry."""
    registry = MCPServerRegistry()
    registry.register(
        MCPServerTemplate(
            name="playwright",
            description="Browser automation for testing",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            category="browser",
        )
    )
    registry.register(
        MCPServerTemplate(
            name="github",
            description="GitHub API access",
            type=MCPServerType.STDIO,
            install_source=MCPInstallSource.NPM,
            category="api",
            required_credentials=["GITHUB_TOKEN"],
        )
    )
    return registry


@pytest.fixture
def sample_task() -> Task:
    """Create a sample task."""
    return Task(
        id=uuid4(),
        description="Add end-to-end tests for the login page",
        goals=["Create playwright tests", "Test login flow"],
        sources=["/tmp/project"],
        budget=Budget(max_iterations=10),
    )


@pytest.fixture
def mock_agent() -> AsyncMock:
    """Create a mock agent."""
    agent = AsyncMock()
    return agent


class TestMCPSuggestion:
    """Tests for MCPSuggestion class."""

    def test_create_suggestion(self) -> None:
        """Test creating an MCP suggestion."""
        suggestion = MCPSuggestion(
            server_name="playwright",
            reason="Browser testing needed",
            confidence=0.9,
        )

        assert suggestion.server_name == "playwright"
        assert suggestion.reason == "Browser testing needed"
        assert suggestion.confidence == 0.9
        assert suggestion.template is None

    def test_create_suggestion_with_template(self, sample_registry: MCPServerRegistry) -> None:
        """Test creating a suggestion with template."""
        template = sample_registry.get("playwright")
        suggestion = MCPSuggestion(
            server_name="playwright",
            reason="Browser testing needed",
            confidence=0.9,
            template=template,
        )

        assert suggestion.template is not None
        assert suggestion.template.name == "playwright"

    def test_default_confidence(self) -> None:
        """Test default confidence value."""
        suggestion = MCPSuggestion(
            server_name="test",
            reason="Test reason",
        )

        assert suggestion.confidence == 0.5


class TestSelectMCPServers:
    """Tests for SelectMCPServers use case."""

    @pytest.mark.asyncio
    async def test_analyze_returns_suggestions(
        self,
        mock_agent: AsyncMock,
        sample_registry: MCPServerRegistry,
        sample_task: Task,
    ) -> None:
        """Test analyzing task returns suggestions."""
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='```json\n[{"name": "playwright", "reason": "Browser testing", "confidence": 0.9}]\n```',
            tools_used=["Read"],
        )

        use_case = SelectMCPServers(mock_agent, sample_registry)
        suggestions = await use_case.analyze_and_suggest(sample_task)

        assert len(suggestions) == 1
        assert suggestions[0].server_name == "playwright"
        assert suggestions[0].confidence == 0.9

    @pytest.mark.asyncio
    async def test_analyze_with_multiple_suggestions(
        self,
        mock_agent: AsyncMock,
        sample_registry: MCPServerRegistry,
        sample_task: Task,
    ) -> None:
        """Test analyzing task with multiple suggestions."""
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="""```json
[
    {"name": "playwright", "reason": "Browser testing", "confidence": 0.9},
    {"name": "github", "reason": "GitHub access needed", "confidence": 0.7}
]
```""",
            tools_used=["Read"],
        )

        use_case = SelectMCPServers(mock_agent, sample_registry)
        suggestions = await use_case.analyze_and_suggest(sample_task)

        assert len(suggestions) == 2
        assert suggestions[0].server_name == "playwright"
        assert suggestions[1].server_name == "github"

    @pytest.mark.asyncio
    async def test_analyze_empty_suggestions(
        self,
        mock_agent: AsyncMock,
        sample_registry: MCPServerRegistry,
        sample_task: Task,
    ) -> None:
        """Test analyzing task with no suggestions."""
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="```json\n[]\n```",
            tools_used=["Read"],
        )

        use_case = SelectMCPServers(mock_agent, sample_registry)
        suggestions = await use_case.analyze_and_suggest(sample_task)

        assert len(suggestions) == 0

    @pytest.mark.asyncio
    async def test_analyze_invalid_json(
        self,
        mock_agent: AsyncMock,
        sample_registry: MCPServerRegistry,
        sample_task: Task,
    ) -> None:
        """Test handling invalid JSON response."""
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="This is not JSON",
            tools_used=["Read"],
        )

        use_case = SelectMCPServers(mock_agent, sample_registry)
        suggestions = await use_case.analyze_and_suggest(sample_task)

        assert len(suggestions) == 0

    @pytest.mark.asyncio
    async def test_analyze_unknown_server(
        self,
        mock_agent: AsyncMock,
        sample_registry: MCPServerRegistry,
        sample_task: Task,
    ) -> None:
        """Test handling suggestions for unknown servers."""
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='```json\n[{"name": "unknown-server", "reason": "Test", "confidence": 0.8}]\n```',
            tools_used=["Read"],
        )

        use_case = SelectMCPServers(mock_agent, sample_registry)
        suggestions = await use_case.analyze_and_suggest(sample_task)

        # Unknown server should be filtered out
        assert len(suggestions) == 0

    @pytest.mark.asyncio
    async def test_analyze_mixed_known_unknown(
        self,
        mock_agent: AsyncMock,
        sample_registry: MCPServerRegistry,
        sample_task: Task,
    ) -> None:
        """Test handling mix of known and unknown servers."""
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="""```json
[
    {"name": "playwright", "reason": "Known server", "confidence": 0.9},
    {"name": "unknown", "reason": "Unknown server", "confidence": 0.8}
]
```""",
            tools_used=["Read"],
        )

        use_case = SelectMCPServers(mock_agent, sample_registry)
        suggestions = await use_case.analyze_and_suggest(sample_task)

        # Only known server should be returned
        assert len(suggestions) == 1
        assert suggestions[0].server_name == "playwright"

    def test_get_template(
        self,
        mock_agent: AsyncMock,
        sample_registry: MCPServerRegistry,
    ) -> None:
        """Test getting template by name."""
        use_case = SelectMCPServers(mock_agent, sample_registry)

        template = use_case.get_template("playwright")
        assert template is not None
        assert template.name == "playwright"

        unknown = use_case.get_template("unknown")
        assert unknown is None

    def test_list_available(
        self,
        mock_agent: AsyncMock,
        sample_registry: MCPServerRegistry,
    ) -> None:
        """Test listing all available templates."""
        use_case = SelectMCPServers(mock_agent, sample_registry)

        templates = use_case.list_available()
        assert len(templates) == 2

    def test_list_by_category(
        self,
        mock_agent: AsyncMock,
        sample_registry: MCPServerRegistry,
    ) -> None:
        """Test listing templates by category."""
        use_case = SelectMCPServers(mock_agent, sample_registry)

        browser_templates = use_case.list_by_category("browser")
        assert len(browser_templates) == 1
        assert browser_templates[0].name == "playwright"

        api_templates = use_case.list_by_category("api")
        assert len(api_templates) == 1
        assert api_templates[0].name == "github"

        unknown_templates = use_case.list_by_category("unknown")
        assert len(unknown_templates) == 0
