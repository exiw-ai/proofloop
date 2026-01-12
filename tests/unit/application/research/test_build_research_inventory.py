"""Tests for BuildResearchInventory use case."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.use_cases.research.build_research_inventory import BuildResearchInventory
from src.domain.entities import Task
from src.domain.ports.agent_port import AgentResult
from src.domain.value_objects import ResearchPreset, ResearchType, TaskStatus


@pytest.fixture
def mock_agent() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def task() -> Task:
    return Task(
        id=uuid4(),
        description="Research authentication best practices",
        goals=["Understand patterns"],
        sources=[],
        status=TaskStatus.RESEARCH_SOURCE_SELECTION,
    )


class TestBuildResearchInventoryRun:
    @pytest.mark.asyncio
    async def test_returns_inventory_from_agent(self, mock_agent: AsyncMock, task: Task) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="""{
                "queries": ["auth best practices", "oauth vs jwt"],
                "required_topics": ["security", "tokens"],
                "topic_synonyms": {"security": ["auth", "authz"]},
                "sections": ["intro", "findings"]
            }""",
            tools_used=[],
        )

        use_case = BuildResearchInventory(mock_agent)
        inventory = await use_case.run(
            task=task,
            research_type=ResearchType.TECHNICAL,
            preset=ResearchPreset.STANDARD,
            source_types=["web", "github"],
        )

        assert inventory.queries == ["auth best practices", "oauth vs jwt"]
        assert inventory.required_topics == ["security", "tokens"]
        assert inventory.topic_synonyms == {"security": ["auth", "authz"]}
        assert inventory.sections == ["intro", "findings"]
        assert inventory.task_id == task.id

    @pytest.mark.asyncio
    async def test_transitions_task_status(self, mock_agent: AsyncMock, task: Task) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"queries": [], "required_topics": [], "topic_synonyms": {}, "sections": []}',
            tools_used=[],
        )

        use_case = BuildResearchInventory(mock_agent)
        await use_case.run(
            task=task,
            research_type=ResearchType.GENERAL,
            preset=ResearchPreset.MINIMAL,
            source_types=["web"],
        )

        assert task.status == TaskStatus.RESEARCH_INVENTORY

    @pytest.mark.asyncio
    async def test_sets_task_research_inventory(self, mock_agent: AsyncMock, task: Task) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"queries": ["q1"], "required_topics": ["t1"], "topic_synonyms": {}, "sections": []}',
            tools_used=[],
        )

        use_case = BuildResearchInventory(mock_agent)
        inventory = await use_case.run(
            task=task,
            research_type=ResearchType.TECHNICAL,
            preset=ResearchPreset.STANDARD,
            source_types=["web"],
        )

        assert task.research_inventory == inventory

    @pytest.mark.asyncio
    async def test_fallback_on_invalid_json(self, mock_agent: AsyncMock, task: Task) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="Not valid JSON at all",
            tools_used=[],
        )

        use_case = BuildResearchInventory(mock_agent)
        inventory = await use_case.run(
            task=task,
            research_type=ResearchType.ACADEMIC,
            preset=ResearchPreset.THOROUGH,
            source_types=["arxiv"],
        )

        # Should create minimal inventory with task description as query
        assert inventory.queries == [task.description]
        assert inventory.required_topics == []
        assert "executive_summary" in inventory.sections

    @pytest.mark.asyncio
    async def test_preserves_research_type_and_preset(
        self, mock_agent: AsyncMock, task: Task
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"queries": [], "required_topics": [], "topic_synonyms": {}, "sections": []}',
            tools_used=[],
        )

        use_case = BuildResearchInventory(mock_agent)
        inventory = await use_case.run(
            task=task,
            research_type=ResearchType.MARKET,
            preset=ResearchPreset.EXHAUSTIVE,
            source_types=["web"],
        )

        assert inventory.research_type == ResearchType.MARKET
        assert inventory.preset == ResearchPreset.EXHAUSTIVE
