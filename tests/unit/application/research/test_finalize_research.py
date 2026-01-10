"""Tests for FinalizeResearch use case."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.application.use_cases.research.finalize_research import FinalizeResearch
from src.domain.entities import ResearchInventory, Task
from src.domain.value_objects import ResearchPreset, ResearchType, TaskStatus


@pytest.fixture
def mock_kb_store() -> AsyncMock:
    store = AsyncMock()
    store.list_sources.return_value = []
    store.list_findings.return_value = []
    return store


@pytest.fixture
def mock_report_store() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def task() -> Task:
    t = Task(
        id=uuid4(),
        description="Research authentication",
        goals=["Understand auth"],
        sources=[],
        status=TaskStatus.RESEARCH_CONDITIONS,
    )
    t.research_inventory = ResearchInventory(
        id=uuid4(),
        task_id=t.id,
        queries=["auth query"],
        required_topics=["security", "tokens"],
        topic_synonyms={},
        sections=["findings"],
        research_type=ResearchType.TECHNICAL,
        preset=ResearchPreset.STANDARD,
        created_at=datetime.now(UTC),
    )
    return t


class TestFinalizeResearchRun:
    @pytest.mark.asyncio
    async def test_all_conditions_passed(
        self, mock_kb_store: AsyncMock, mock_report_store: AsyncMock, task: Task, tmp_path: Path
    ) -> None:
        use_case = FinalizeResearch(mock_kb_store, mock_report_store, tmp_path)

        result = await use_case.run(
            task=task,
            conditions_results={"MIN_SOURCES": True, "COVERAGE_THRESHOLD": True},
        )

        assert result.status == TaskStatus.RESEARCH_FINALIZED
        assert task.status == TaskStatus.RESEARCH_FINALIZED
        assert result.error is None
        assert "MIN_SOURCES" in result.conditions_met
        assert "COVERAGE_THRESHOLD" in result.conditions_met
        assert result.conditions_failed == []

    @pytest.mark.asyncio
    async def test_some_conditions_failed(
        self, mock_kb_store: AsyncMock, mock_report_store: AsyncMock, task: Task, tmp_path: Path
    ) -> None:
        use_case = FinalizeResearch(mock_kb_store, mock_report_store, tmp_path)

        result = await use_case.run(
            task=task,
            conditions_results={"MIN_SOURCES": True, "COVERAGE_THRESHOLD": False},
        )

        assert result.status == TaskStatus.RESEARCH_FAILED
        assert task.status == TaskStatus.RESEARCH_FAILED
        assert result.error is not None
        assert "MIN_SOURCES" in result.conditions_met
        assert "COVERAGE_THRESHOLD" in result.conditions_failed

    @pytest.mark.asyncio
    async def test_metrics_include_counts(
        self, mock_kb_store: AsyncMock, mock_report_store: AsyncMock, task: Task, tmp_path: Path
    ) -> None:
        # Set up some sources and findings
        mock_kb_store.list_sources.return_value = [MagicMock(), MagicMock()]
        mock_kb_store.list_findings.return_value = [MagicMock(), MagicMock(), MagicMock()]

        use_case = FinalizeResearch(mock_kb_store, mock_report_store, tmp_path)

        result = await use_case.run(
            task=task,
            conditions_results={"MIN_SOURCES": True},
        )

        assert result.metrics["sources_count"] == 2.0
        assert result.metrics["findings_count"] == 3.0

    @pytest.mark.asyncio
    async def test_next_actions_on_success(
        self, mock_kb_store: AsyncMock, mock_report_store: AsyncMock, task: Task, tmp_path: Path
    ) -> None:
        use_case = FinalizeResearch(mock_kb_store, mock_report_store, tmp_path)

        result = await use_case.run(
            task=task,
            conditions_results={"MIN_SOURCES": True},
        )

        assert any("derive-code" in action for action in result.next_actions)
        assert any("reports" in action for action in result.next_actions)

    @pytest.mark.asyncio
    async def test_next_actions_on_failure(
        self, mock_kb_store: AsyncMock, mock_report_store: AsyncMock, task: Task, tmp_path: Path
    ) -> None:
        use_case = FinalizeResearch(mock_kb_store, mock_report_store, tmp_path)

        result = await use_case.run(
            task=task,
            conditions_results={
                "MIN_SOURCES": False,
                "COVERAGE_THRESHOLD": False,
                "CITATIONS_VALID": False,
            },
        )

        assert any("sources" in action.lower() for action in result.next_actions)
        assert any("coverage" in action.lower() for action in result.next_actions)
        assert any("citations" in action.lower() for action in result.next_actions)


class TestCalculateCoverage:
    @pytest.mark.asyncio
    async def test_empty_topics_returns_one(
        self, mock_kb_store: AsyncMock, mock_report_store: AsyncMock, tmp_path: Path
    ) -> None:
        use_case = FinalizeResearch(mock_kb_store, mock_report_store, tmp_path)

        coverage = use_case._calculate_coverage([], [])

        assert coverage == 1.0

    @pytest.mark.asyncio
    async def test_partial_coverage(
        self, mock_kb_store: AsyncMock, mock_report_store: AsyncMock, tmp_path: Path
    ) -> None:
        use_case = FinalizeResearch(mock_kb_store, mock_report_store, tmp_path)

        # Mock findings with topics
        finding1 = MagicMock()
        finding1.topics = ["security", "auth"]

        coverage = use_case._calculate_coverage(
            [finding1],
            ["security", "tokens", "performance"],
        )

        assert coverage == pytest.approx(1 / 3)  # Only "security" covered

    @pytest.mark.asyncio
    async def test_full_coverage(
        self, mock_kb_store: AsyncMock, mock_report_store: AsyncMock, tmp_path: Path
    ) -> None:
        use_case = FinalizeResearch(mock_kb_store, mock_report_store, tmp_path)

        finding1 = MagicMock()
        finding1.topics = ["security"]
        finding2 = MagicMock()
        finding2.topics = ["tokens"]

        coverage = use_case._calculate_coverage(
            [finding1, finding2],
            ["security", "tokens"],
        )

        assert coverage == 1.0
