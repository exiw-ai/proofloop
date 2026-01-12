"""Tests for SelectSources use case."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.use_cases.research.select_sources import (
    RESEARCH_TYPE_SOURCES,
    SelectSources,
)
from src.domain.entities import Task
from src.domain.ports.agent_port import AgentResult
from src.domain.value_objects import ResearchType, TaskStatus


@pytest.fixture
def mock_agent() -> AsyncMock:
    agent = AsyncMock()
    return agent


@pytest.fixture
def task() -> Task:
    return Task(
        id=uuid4(),
        description="Research best practices for authentication",
        goals=["Understand auth patterns", "Compare options"],
        sources=[],
        status=TaskStatus.RESEARCH_INTAKE,
    )


class TestResearchTypeSources:
    def test_academic_includes_arxiv(self) -> None:
        sources = RESEARCH_TYPE_SOURCES[ResearchType.ACADEMIC]
        assert "arxiv" in sources
        assert "semantic_scholar" in sources

    def test_market_includes_web(self) -> None:
        sources = RESEARCH_TYPE_SOURCES[ResearchType.MARKET]
        assert "web" in sources
        assert "github" in sources

    def test_technical_includes_github(self) -> None:
        sources = RESEARCH_TYPE_SOURCES[ResearchType.TECHNICAL]
        assert "github" in sources
        assert "web" in sources

    def test_general_includes_all_major(self) -> None:
        sources = RESEARCH_TYPE_SOURCES[ResearchType.GENERAL]
        assert "web" in sources
        assert "arxiv" in sources
        assert "github" in sources


class TestSelectSourcesRun:
    @pytest.mark.asyncio
    async def test_returns_sources_from_agent(self, mock_agent: AsyncMock, task: Task) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"source_types": ["arxiv", "web"], "strategy": "Academic first", "reasoning": "Focus on papers"}',
            tools_used=[],
        )

        use_case = SelectSources(mock_agent)
        result = await use_case.run(task, ResearchType.ACADEMIC)

        assert result.source_types == ["arxiv", "web"]
        assert result.strategy == "Academic first"
        assert result.reasoning == "Focus on papers"

    @pytest.mark.asyncio
    async def test_transitions_task_status(self, mock_agent: AsyncMock, task: Task) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"source_types": ["web"], "strategy": "", "reasoning": ""}',
            tools_used=[],
        )

        use_case = SelectSources(mock_agent)
        await use_case.run(task, ResearchType.GENERAL)

        assert task.status == TaskStatus.RESEARCH_SOURCE_SELECTION

    @pytest.mark.asyncio
    async def test_fallback_on_invalid_json(self, mock_agent: AsyncMock, task: Task) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="This is not valid JSON",
            tools_used=[],
        )

        use_case = SelectSources(mock_agent)
        result = await use_case.run(task, ResearchType.ACADEMIC)

        # Should use default sources for ACADEMIC
        assert result.source_types == RESEARCH_TYPE_SOURCES[ResearchType.ACADEMIC]
        assert "Default" in result.strategy

    @pytest.mark.asyncio
    async def test_fallback_on_missing_fields(self, mock_agent: AsyncMock, task: Task) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"unrelated": "data"}',
            tools_used=[],
        )

        use_case = SelectSources(mock_agent)
        result = await use_case.run(task, ResearchType.MARKET)

        # Should use default sources for MARKET
        assert result.source_types == RESEARCH_TYPE_SOURCES[ResearchType.MARKET]

    @pytest.mark.asyncio
    async def test_uses_research_tools(self, mock_agent: AsyncMock, task: Task) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"source_types": ["web"], "strategy": "", "reasoning": ""}',
            tools_used=[],
        )

        use_case = SelectSources(mock_agent)
        await use_case.run(task, ResearchType.GENERAL)

        # Verify the agent was called with research tools
        call_args = mock_agent.execute.call_args
        assert "WebSearch" in call_args.kwargs.get("allowed_tools", [])
