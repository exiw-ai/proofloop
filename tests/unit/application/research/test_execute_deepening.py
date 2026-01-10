"""Tests for ExecuteDeepening use case."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.use_cases.research.execute_deepening import (
    DeepeningResult,
    ExecuteDeepening,
)
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
        queries=["test query"],
        required_topics=["topic1"],
        topic_synonyms={},
        sections=["intro"],
        research_type=ResearchType.TECHNICAL,
        preset=ResearchPreset.MINIMAL,  # 1 synthesis pass
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def task(research_inventory: ResearchInventory) -> Task:
    t = Task(
        id=research_inventory.task_id,
        description="Research patterns",
        goals=["Understand patterns"],
        sources=[],
        status=TaskStatus.RESEARCH_DISCOVERY,
    )
    t.research_inventory = research_inventory
    return t


class TestExecuteDeepeningRun:
    @pytest.mark.asyncio
    async def test_transitions_to_deepening_status(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task, tmp_path: Path
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"themes": [], "gaps": [], "trends": [], "suggested_queries": [], "synthesis_notes": ""}',
            tools_used=[],
        )

        use_case = ExecuteDeepening(mock_agent, kb_store, tmp_path)
        await use_case.run(task)

        assert task.status == TaskStatus.RESEARCH_DEEPENING

    @pytest.mark.asyncio
    async def test_raises_without_inventory(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, tmp_path: Path
    ) -> None:
        task = Task(
            id=uuid4(),
            description="Research patterns",
            goals=["Understand patterns"],
            sources=[],
            status=TaskStatus.RESEARCH_DISCOVERY,
        )

        use_case = ExecuteDeepening(mock_agent, kb_store, tmp_path)
        with pytest.raises(ValueError, match="No research inventory"):
            await use_case.run(task)

    @pytest.mark.asyncio
    async def test_returns_deepening_result(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task, tmp_path: Path
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="""{
                "themes": [{"name": "Auth", "description": "Authentication", "supporting_findings": []}],
                "gaps": [{"topic": "Security", "description": "Missing security"}],
                "trends": [{"name": "OAuth", "description": "Growing", "evidence": []}],
                "suggested_queries": [],
                "synthesis_notes": "Pass 1 complete"
            }""",
            tools_used=[],
        )

        use_case = ExecuteDeepening(mock_agent, kb_store, tmp_path)
        result = await use_case.run(task)

        assert isinstance(result, DeepeningResult)
        assert result.synthesis_passes == 1  # MINIMAL preset
        assert result.themes_identified == 1
        assert result.gaps_identified == 1
        assert result.trends_identified == 1

    @pytest.mark.asyncio
    async def test_creates_synthesis_directory(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task, tmp_path: Path
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"themes": [], "gaps": [], "trends": [], "suggested_queries": [], "synthesis_notes": ""}',
            tools_used=[],
        )

        use_case = ExecuteDeepening(mock_agent, kb_store, tmp_path)
        await use_case.run(task)

        synthesis_dir = tmp_path / "knowledge_base" / "synthesis"
        assert synthesis_dir.exists()

    @pytest.mark.asyncio
    async def test_saves_synthesis_log(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task, tmp_path: Path
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"themes": [], "gaps": [], "trends": [], "suggested_queries": [], "synthesis_notes": ""}',
            tools_used=[],
        )

        use_case = ExecuteDeepening(mock_agent, kb_store, tmp_path)
        await use_case.run(task)

        synthesis_log = tmp_path / "knowledge_base" / "synthesis" / "synthesis_log.json"
        assert synthesis_log.exists()

    @pytest.mark.asyncio
    async def test_saves_pass_results(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task, tmp_path: Path
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"themes": [], "gaps": [], "trends": [], "suggested_queries": [], "synthesis_notes": ""}',
            tools_used=[],
        )

        use_case = ExecuteDeepening(mock_agent, kb_store, tmp_path)
        await use_case.run(task)

        pass_file = tmp_path / "knowledge_base" / "synthesis" / "pass_1.json"
        assert pass_file.exists()

    @pytest.mark.asyncio
    async def test_adds_iteration_on_success(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task, tmp_path: Path
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"themes": [{"name": "T1", "description": "", "supporting_findings": []}], "gaps": [], "trends": [], "suggested_queries": [], "synthesis_notes": ""}',
            tools_used=[],
        )

        use_case = ExecuteDeepening(mock_agent, kb_store, tmp_path)
        await use_case.run(task)

        assert len(task.iterations) == 1
        assert "1 themes" in task.iterations[0].changes[0]

    @pytest.mark.asyncio
    async def test_handles_invalid_json_response(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task, tmp_path: Path
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="Not valid JSON",
            tools_used=[],
        )

        use_case = ExecuteDeepening(mock_agent, kb_store, tmp_path)
        result = await use_case.run(task)

        # Should complete without crashing
        assert result.synthesis_passes == 1  # Still counted as a pass

    @pytest.mark.asyncio
    async def test_multiple_synthesis_passes(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, tmp_path: Path
    ) -> None:
        # Use THOROUGH preset which requires 2 passes
        inventory = ResearchInventory(
            id=uuid4(),
            task_id=uuid4(),
            queries=["test"],
            required_topics=["topic1"],
            topic_synonyms={},
            sections=["intro"],
            research_type=ResearchType.TECHNICAL,
            preset=ResearchPreset.THOROUGH,
            created_at=datetime.now(UTC),
        )
        task = Task(
            id=inventory.task_id,
            description="Research patterns",
            goals=["Understand patterns"],
            sources=[],
            status=TaskStatus.RESEARCH_DISCOVERY,
        )
        task.research_inventory = inventory

        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"themes": [], "gaps": [], "trends": [], "suggested_queries": [], "synthesis_notes": ""}',
            tools_used=[],
        )

        use_case = ExecuteDeepening(mock_agent, kb_store, tmp_path)
        result = await use_case.run(task)

        assert result.synthesis_passes == 2
        assert mock_agent.execute.call_count == 2
