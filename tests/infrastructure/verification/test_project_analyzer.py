from unittest.mock import AsyncMock

import pytest

from src.domain.ports.agent_port import AgentPort, AgentResult
from src.infrastructure.verification.project_analyzer import ProjectAnalyzer


class TestProjectAnalyzer:
    @pytest.fixture
    def mock_agent(self) -> AsyncMock:
        return AsyncMock(spec=AgentPort)

    @pytest.fixture
    def analyzer(self, mock_agent: AsyncMock) -> ProjectAnalyzer:
        return ProjectAnalyzer(agent=mock_agent)

    async def test_analyze_project_parses_json_response(
        self, analyzer: ProjectAnalyzer, mock_agent: AsyncMock
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="""{
                "structure": {"root_files": ["pyproject.toml"], "src_dirs": ["src"], "test_dirs": ["tests"]},
                "commands": {"test": "pytest", "lint": "ruff check ."},
                "conventions": ["Use pytest for tests"],
                "frameworks": ["pytest", "pydantic"]
            }""",
            tools_used=["Read", "Glob"],
        )

        result = await analyzer.analyze_project("/tmp/project")

        assert result.structure == {
            "root_files": ["pyproject.toml"],
            "src_dirs": ["src"],
            "test_dirs": ["tests"],
        }
        assert result.commands == {"test": "pytest", "lint": "ruff check ."}
        assert result.conventions == ["Use pytest for tests"]
        assert result.frameworks == ["pytest", "pydantic"]

    async def test_analyze_project_calls_agent_with_correct_params(
        self, analyzer: ProjectAnalyzer, mock_agent: AsyncMock
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="{}",
            tools_used=[],
        )

        await analyzer.analyze_project("/tmp/my-project")

        mock_agent.execute.assert_called_once()
        call_args = mock_agent.execute.call_args
        assert call_args.kwargs["cwd"] == "/tmp/my-project"
        assert set(call_args.kwargs["allowed_tools"]) == {"Read", "Glob", "Grep", "Bash"}
        assert "/tmp/my-project" in call_args.kwargs["prompt"]

    async def test_analyze_project_handles_markdown_code_blocks(
        self, analyzer: ProjectAnalyzer, mock_agent: AsyncMock
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="""```json
{
    "structure": {},
    "commands": {"test": "pytest"},
    "conventions": [],
    "frameworks": []
}
```""",
            tools_used=[],
        )

        result = await analyzer.analyze_project("/tmp/project")

        assert result.commands == {"test": "pytest"}

    async def test_analyze_project_handles_json_with_extra_text(
        self, analyzer: ProjectAnalyzer, mock_agent: AsyncMock
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="""Here is the analysis:
{
    "structure": {},
    "commands": {"lint": "ruff check ."},
    "conventions": [],
    "frameworks": []
}
That's all!""",
            tools_used=[],
        )

        result = await analyzer.analyze_project("/tmp/project")

        assert result.commands == {"lint": "ruff check ."}

    async def test_analyze_project_returns_empty_on_invalid_json(
        self, analyzer: ProjectAnalyzer, mock_agent: AsyncMock
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="This is not valid JSON at all",
            tools_used=[],
        )

        result = await analyzer.analyze_project("/tmp/project")

        assert result.structure == {}
        assert result.commands == {}
        assert result.conventions == []
        assert result.frameworks == []

    async def test_analyze_project_handles_partial_response(
        self, analyzer: ProjectAnalyzer, mock_agent: AsyncMock
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="""{
                "commands": {"test": "npm test"}
            }""",
            tools_used=[],
        )

        result = await analyzer.analyze_project("/tmp/project")

        assert result.commands == {"test": "npm test"}
        assert result.structure == {}
        assert result.conventions == []
        assert result.frameworks == []

    async def test_analyze_project_handles_empty_response(
        self, analyzer: ProjectAnalyzer, mock_agent: AsyncMock
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="",
            tools_used=[],
        )

        result = await analyzer.analyze_project("/tmp/project")

        assert result.structure == {}
        assert result.commands == {}
        assert result.conventions == []
        assert result.frameworks == []
