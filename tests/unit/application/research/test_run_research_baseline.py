"""Tests for RunResearchBaseline use case."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.use_cases.research.run_research_baseline import RunResearchBaseline
from src.domain.entities import ResearchInventory, Task
from src.domain.ports.agent_port import AgentResult
from src.domain.value_objects import ResearchPreset, ResearchType, TaskStatus
from src.infrastructure.research import KnowledgeBaseStore


@pytest.fixture
def mock_agent() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def kb_store(tmp_path: Path) -> KnowledgeBaseStore:
    return KnowledgeBaseStore(tmp_path)


@pytest.fixture
def research_inventory() -> ResearchInventory:
    return ResearchInventory(
        id=uuid4(),
        task_id=uuid4(),
        queries=["query1", "query2", "query3"],
        required_topics=["topic1"],
        topic_synonyms={},
        sections=["intro"],
        research_type=ResearchType.TECHNICAL,
        preset=ResearchPreset.MINIMAL,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def task(research_inventory: ResearchInventory) -> Task:
    t = Task(
        id=research_inventory.task_id,
        description="Research patterns",
        goals=["Understand patterns"],
        sources=[],
        status=TaskStatus.RESEARCH_INVENTORY,
    )
    t.research_inventory = research_inventory
    return t


class TestRunResearchBaselineRun:
    @pytest.mark.asyncio
    async def test_transitions_to_baseline_status(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task, tmp_path: Path
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"baseline_results": [], "initial_sources_identified": []}',
            tools_used=[],
        )

        use_case = RunResearchBaseline(mock_agent, kb_store, tmp_path)
        await use_case.run(task)

        assert task.status == TaskStatus.RESEARCH_BASELINE

    @pytest.mark.asyncio
    async def test_returns_error_without_inventory(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, tmp_path: Path
    ) -> None:
        task = Task(
            id=uuid4(),
            description="Research patterns",
            goals=["Understand patterns"],
            sources=[],
            status=TaskStatus.RESEARCH_INVENTORY,
        )

        use_case = RunResearchBaseline(mock_agent, kb_store, tmp_path)
        result = await use_case.run(task)

        assert "error" in result
        mock_agent.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_baseline_data(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task, tmp_path: Path
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="""{
                "baseline_results": [
                    {"query": "query1", "results_count": 10, "top_sources": ["src1"], "notes": "Good results"}
                ],
                "initial_sources_identified": ["https://example.com/1"]
            }""",
            tools_used=[],
        )

        use_case = RunResearchBaseline(mock_agent, kb_store, tmp_path)
        result = await use_case.run(task)

        assert "task_id" in result
        assert "queries" in result
        assert "baseline_results" in result
        assert result["baseline_results"][0]["query"] == "query1"

    @pytest.mark.asyncio
    async def test_creates_baseline_directory(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task, tmp_path: Path
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"baseline_results": [], "initial_sources_identified": []}',
            tools_used=[],
        )

        use_case = RunResearchBaseline(mock_agent, kb_store, tmp_path)
        await use_case.run(task)

        baseline_dir = tmp_path / "knowledge_base" / "baseline"
        assert baseline_dir.exists()

    @pytest.mark.asyncio
    async def test_saves_baseline_json(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task, tmp_path: Path
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"baseline_results": [], "initial_sources_identified": []}',
            tools_used=[],
        )

        use_case = RunResearchBaseline(mock_agent, kb_store, tmp_path)
        await use_case.run(task)

        baseline_file = tmp_path / "knowledge_base" / "baseline" / "baseline.json"
        assert baseline_file.exists()

        data = json.loads(baseline_file.read_text())
        assert "task_id" in data
        assert "queries" in data
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_limits_queries_to_first_five(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, tmp_path: Path
    ) -> None:
        inventory = ResearchInventory(
            id=uuid4(),
            task_id=uuid4(),
            queries=["q1", "q2", "q3", "q4", "q5", "q6", "q7"],
            required_topics=["topic1"],
            topic_synonyms={},
            sections=["intro"],
            research_type=ResearchType.TECHNICAL,
            preset=ResearchPreset.MINIMAL,
            created_at=datetime.now(UTC),
        )
        task = Task(
            id=inventory.task_id,
            description="Research patterns",
            goals=["Understand patterns"],
            sources=[],
            status=TaskStatus.RESEARCH_INVENTORY,
        )
        task.research_inventory = inventory

        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"baseline_results": [], "initial_sources_identified": []}',
            tools_used=[],
        )

        use_case = RunResearchBaseline(mock_agent, kb_store, tmp_path)
        result = await use_case.run(task)

        assert len(result["queries"]) == 5

    @pytest.mark.asyncio
    async def test_returns_error_on_invalid_json(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task, tmp_path: Path
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="Not valid JSON at all",
            tools_used=[],
        )

        use_case = RunResearchBaseline(mock_agent, kb_store, tmp_path)
        result = await use_case.run(task)

        assert "error" in result

    @pytest.mark.asyncio
    async def test_uses_research_tools(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task, tmp_path: Path
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"baseline_results": [], "initial_sources_identified": []}',
            tools_used=[],
        )

        use_case = RunResearchBaseline(mock_agent, kb_store, tmp_path)
        await use_case.run(task)

        call_args = mock_agent.execute.call_args
        allowed_tools = call_args.kwargs.get("allowed_tools", [])
        assert "WebSearch" in allowed_tools
