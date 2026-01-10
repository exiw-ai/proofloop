"""Tests for ExecuteDiscovery use case."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.application.use_cases.research.execute_discovery import DiscoveryMetrics, ExecuteDiscovery
from src.domain.entities import Finding, ResearchInventory, Task
from src.domain.entities.source import FetchMeta, Source
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
        required_topics=["topic1", "topic2"],
        topic_synonyms={},
        sections=["intro"],
        research_type=ResearchType.TECHNICAL,
        preset=ResearchPreset.STANDARD,  # Use STANDARD for proper testing
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


class TestExecuteDiscoveryRun:
    @pytest.mark.asyncio
    async def test_transitions_to_discovery_status(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"fetched_pages": [], "findings": [], "notes": "No results"}',
            tools_used=[],
        )

        use_case = ExecuteDiscovery(mock_agent, kb_store)
        await use_case.run(task, max_iterations=1)

        assert task.status == TaskStatus.RESEARCH_DISCOVERY

    @pytest.mark.asyncio
    async def test_raises_without_inventory(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore
    ) -> None:
        task = Task(
            id=uuid4(),
            description="Research patterns",
            goals=["Understand patterns"],
            sources=[],
            status=TaskStatus.RESEARCH_INVENTORY,
        )

        use_case = ExecuteDiscovery(mock_agent, kb_store)
        with pytest.raises(ValueError, match="No research inventory"):
            await use_case.run(task)

    @pytest.mark.asyncio
    async def test_returns_metrics(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"fetched_pages": [], "findings": [], "notes": "Done"}',
            tools_used=[],
        )

        use_case = ExecuteDiscovery(mock_agent, kb_store)
        metrics = await use_case.run(task, max_iterations=1)

        assert isinstance(metrics, DiscoveryMetrics)
        assert metrics.iteration == 1

    @pytest.mark.asyncio
    async def test_stops_when_conditions_met(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task, tmp_path: Path
    ) -> None:
        # Pre-populate with enough sources and findings
        for i in range(35):  # More than min_sources for STANDARD preset (30)
            source = Source(
                id=uuid4(),
                source_key=f"source_{i}",
                title=f"Source {i}",
                url=f"https://example.com/{i}",
                canonical_url=f"https://example.com/{i}",
                retrieved_at=datetime.now(UTC),
                content_hash=f"hash{i}",
                source_type="web",
                raw_path=f"raw/{i}.html",
                text_path=f"text/{i}.txt",
                fetch_meta=FetchMeta(
                    http_status=200,
                    final_url=f"https://example.com/{i}",
                    mime_type="text/html",
                    size_bytes=100,
                    extract_method="html",
                ),
            )
            await kb_store.save_source(
                url=source.url,
                content=b"test content",
                source_type="web",
                title=source.title,
            )

        # Add findings that cover topics
        sources = await kb_store.list_sources()
        for source in sources[:5]:
            finding = Finding(
                id=uuid4(),
                source_id=source.id,
                source_key=source.source_key,
                excerpt_ref="",
                content="Test finding",
                finding_type="fact",
                confidence=0.8,
                topics=["topic1", "topic2"],  # Cover all required topics
            )
            await kb_store.save_finding(finding)

        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response='{"fetched_pages": [], "findings": [], "notes": "Done"}',
            tools_used=[],
        )

        use_case = ExecuteDiscovery(mock_agent, kb_store)
        metrics = await use_case.run(task, max_iterations=5)

        # Should stop early when conditions are met
        assert metrics.iteration == 1
        assert (
            "Done" in task.iterations[-1].decision_reason
            or "Met" in task.iterations[-1].decision_reason
        )


class TestProcessFetchedPagesAndFindings:
    @pytest.mark.asyncio
    async def test_processes_fetched_pages(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="""{
                "fetched_pages": [
                    {"url": "https://example.com/1", "title": "Page 1", "content_summary": "Content 1", "source_type": "web"},
                    {"url": "https://example.com/2", "title": "Page 2", "content_summary": "Content 2", "source_type": "web"}
                ],
                "findings": [],
                "notes": "Processed pages"
            }""",
            tools_used=[],
        )

        use_case = ExecuteDiscovery(mock_agent, kb_store)
        await use_case.run(task, max_iterations=1)

        sources = await kb_store.list_sources()
        assert len(sources) >= 2

    @pytest.mark.asyncio
    async def test_processes_findings_with_source(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task
    ) -> None:
        # First save a source
        source, _ = await kb_store.save_source(
            url="https://example.com/test",
            content=b"Test content",
            source_type="web",
            title="Test Source",
        )

        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="""{
                "fetched_pages": [],
                "findings": [
                    {
                        "source_url": "https://example.com/test",
                        "excerpt": "Interesting excerpt",
                        "content": "This is a key finding",
                        "finding_type": "fact",
                        "confidence": 0.9,
                        "topics": ["topic1"]
                    }
                ],
                "notes": "Processed findings"
            }""",
            tools_used=[],
        )

        use_case = ExecuteDiscovery(mock_agent, kb_store)
        await use_case.run(task, max_iterations=1)

        findings = await kb_store.list_findings()
        assert len(findings) >= 1

    @pytest.mark.asyncio
    async def test_skips_findings_without_matching_source(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="""{
                "fetched_pages": [],
                "findings": [
                    {
                        "source_url": "https://nonexistent.com/page",
                        "content": "This finding has no matching source",
                        "topics": ["topic1"]
                    }
                ],
                "notes": "Skipped finding"
            }""",
            tools_used=[],
        )

        use_case = ExecuteDiscovery(mock_agent, kb_store)
        await use_case.run(task, max_iterations=1)

        findings = await kb_store.list_findings()
        # No findings should be saved because source doesn't exist
        assert len(findings) == 0

    @pytest.mark.asyncio
    async def test_skips_pages_without_url(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="""{
                "fetched_pages": [
                    {"title": "No URL Page", "content_summary": "Content"},
                    {"url": "", "title": "Empty URL", "content_summary": "Content"}
                ],
                "findings": [],
                "notes": "Skipped pages without URL"
            }""",
            tools_used=[],
        )

        use_case = ExecuteDiscovery(mock_agent, kb_store)
        await use_case.run(task, max_iterations=1)

        sources = await kb_store.list_sources()
        # No sources should be saved because pages have no valid URL
        assert len(sources) == 0

    @pytest.mark.asyncio
    async def test_handles_error_in_json_parsing(
        self, mock_agent: AsyncMock, kb_store: KnowledgeBaseStore, task: Task
    ) -> None:
        # Return invalid JSON that will cause an error in processing
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="This is not valid JSON at all",
            tools_used=[],
        )

        use_case = ExecuteDiscovery(mock_agent, kb_store)
        # Should not raise - should catch error in try block and continue
        await use_case.run(task, max_iterations=1)

        # Check that error was recorded in iteration
        assert len(task.iterations) >= 1
        assert "Error" in task.iterations[0].changes[0]


class TestCalculateCoverage:
    def test_empty_topics_returns_full_coverage(self) -> None:
        use_case = ExecuteDiscovery(AsyncMock(), MagicMock())
        coverage = use_case._calculate_coverage([], [])
        assert coverage == 1.0

    def test_no_findings_returns_zero(self) -> None:
        use_case = ExecuteDiscovery(AsyncMock(), MagicMock())
        coverage = use_case._calculate_coverage([], ["topic1", "topic2"])
        assert coverage == 0.0

    def test_partial_coverage(self) -> None:
        finding = Finding(
            id=uuid4(),
            source_id=uuid4(),
            source_key="source1",
            excerpt_ref="",
            content="Test",
            finding_type="fact",
            confidence=0.8,
            topics=["topic1"],
        )
        use_case = ExecuteDiscovery(AsyncMock(), MagicMock())
        coverage = use_case._calculate_coverage([finding], ["topic1", "topic2"])
        assert coverage == 0.5

    def test_full_coverage(self) -> None:
        finding = Finding(
            id=uuid4(),
            source_id=uuid4(),
            source_key="source1",
            excerpt_ref="",
            content="Test",
            finding_type="fact",
            confidence=0.8,
            topics=["topic1", "topic2"],
        )
        use_case = ExecuteDiscovery(AsyncMock(), MagicMock())
        coverage = use_case._calculate_coverage([finding], ["topic1", "topic2"])
        assert coverage == 1.0


class TestGetUncoveredTopics:
    def test_returns_all_when_no_findings(self) -> None:
        use_case = ExecuteDiscovery(AsyncMock(), MagicMock())
        uncovered = use_case._get_uncovered_topics([], ["topic1", "topic2"])
        assert uncovered == ["topic1", "topic2"]

    def test_returns_empty_when_all_covered(self) -> None:
        finding = Finding(
            id=uuid4(),
            source_id=uuid4(),
            source_key="source1",
            excerpt_ref="",
            content="Test",
            finding_type="fact",
            confidence=0.8,
            topics=["topic1", "topic2"],
        )
        use_case = ExecuteDiscovery(AsyncMock(), MagicMock())
        uncovered = use_case._get_uncovered_topics([finding], ["topic1", "topic2"])
        assert uncovered == []

    def test_returns_uncovered_only(self) -> None:
        finding = Finding(
            id=uuid4(),
            source_id=uuid4(),
            source_key="source1",
            excerpt_ref="",
            content="Test",
            finding_type="fact",
            confidence=0.8,
            topics=["topic1"],
        )
        use_case = ExecuteDiscovery(AsyncMock(), MagicMock())
        uncovered = use_case._get_uncovered_topics([finding], ["topic1", "topic2"])
        assert uncovered == ["topic2"]
