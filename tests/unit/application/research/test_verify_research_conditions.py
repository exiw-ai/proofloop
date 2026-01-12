"""Tests for VerifyResearchConditions use case."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.application.use_cases.research.verify_research_conditions import (
    VerifyResearchConditions,
)
from src.domain.entities import Finding, ResearchInventory, Task
from src.domain.value_objects import ResearchPreset, ResearchType, TaskStatus
from src.infrastructure.research import (
    KnowledgeBaseStore,
    ReportPackStore,
    VerificationEvidenceStore,
)


@pytest.fixture
def kb_store(tmp_path: Path) -> KnowledgeBaseStore:
    return KnowledgeBaseStore(tmp_path)


@pytest.fixture
def report_store(tmp_path: Path) -> ReportPackStore:
    return ReportPackStore(tmp_path / "reports")


@pytest.fixture
def evidence_store(tmp_path: Path) -> VerificationEvidenceStore:
    return VerificationEvidenceStore(tmp_path)


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
        preset=ResearchPreset.STANDARD,  # Use STANDARD for coverage tests
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def task(research_inventory: ResearchInventory) -> Task:
    t = Task(
        id=research_inventory.task_id,
        description="Research patterns",
        goals=["Understand patterns"],
        sources=[],
        status=TaskStatus.RESEARCH_DEEPENING,
    )
    t.research_inventory = research_inventory
    return t


class TestVerifyResearchConditionsRun:
    @pytest.mark.asyncio
    async def test_transitions_to_conditions_status(
        self,
        kb_store: KnowledgeBaseStore,
        report_store: ReportPackStore,
        evidence_store: VerificationEvidenceStore,
        task: Task,
    ) -> None:
        use_case = VerifyResearchConditions(kb_store, report_store, evidence_store)
        await use_case.run(task)

        assert task.status == TaskStatus.RESEARCH_CONDITIONS

    @pytest.mark.asyncio
    async def test_returns_error_without_inventory(
        self,
        kb_store: KnowledgeBaseStore,
        report_store: ReportPackStore,
        evidence_store: VerificationEvidenceStore,
    ) -> None:
        task = Task(
            id=uuid4(),
            description="Research patterns",
            goals=["Understand patterns"],
            sources=[],
            status=TaskStatus.RESEARCH_DEEPENING,
        )

        use_case = VerifyResearchConditions(kb_store, report_store, evidence_store)
        result = await use_case.run(task)

        assert "error" in result

    @pytest.mark.asyncio
    async def test_checks_min_sources_fail(
        self,
        kb_store: KnowledgeBaseStore,
        report_store: ReportPackStore,
        evidence_store: VerificationEvidenceStore,
        task: Task,
    ) -> None:
        # No sources added - should fail MIN_SOURCES
        use_case = VerifyResearchConditions(kb_store, report_store, evidence_store)
        result = await use_case.run(task)

        assert result["MIN_SOURCES"] is False

    @pytest.mark.asyncio
    async def test_checks_min_sources_pass(
        self,
        kb_store: KnowledgeBaseStore,
        report_store: ReportPackStore,
        evidence_store: VerificationEvidenceStore,
        task: Task,
    ) -> None:
        # Add enough sources for STANDARD preset (30)
        for i in range(35):
            await kb_store.save_source(
                url=f"https://example.com/{i}",
                content=b"test content",
                source_type="web",
                title=f"Source {i}",
            )

        use_case = VerifyResearchConditions(kb_store, report_store, evidence_store)
        result = await use_case.run(task)

        assert result["MIN_SOURCES"] is True

    @pytest.mark.asyncio
    async def test_checks_coverage_fail(
        self,
        kb_store: KnowledgeBaseStore,
        report_store: ReportPackStore,
        evidence_store: VerificationEvidenceStore,
        task: Task,
    ) -> None:
        # No findings - should fail COVERAGE_THRESHOLD
        use_case = VerifyResearchConditions(kb_store, report_store, evidence_store)
        result = await use_case.run(task)

        assert result["COVERAGE_THRESHOLD"] is False

    @pytest.mark.asyncio
    async def test_checks_coverage_pass(
        self,
        kb_store: KnowledgeBaseStore,
        report_store: ReportPackStore,
        evidence_store: VerificationEvidenceStore,
        task: Task,
    ) -> None:
        # Add findings that cover required topics
        source, _ = await kb_store.save_source(
            url="https://example.com/1",
            content=b"test content",
            source_type="web",
            title="Source 1",
        )

        for topic in task.research_inventory.required_topics:
            finding = Finding(
                id=uuid4(),
                source_id=source.id,
                source_key=source.source_key,
                excerpt_ref="",
                content=f"Finding about {topic}",
                finding_type="fact",
                confidence=0.8,
                topics=[topic],
            )
            await kb_store.save_finding(finding)

        use_case = VerifyResearchConditions(kb_store, report_store, evidence_store)
        result = await use_case.run(task)

        assert result["COVERAGE_THRESHOLD"] is True

    @pytest.mark.asyncio
    async def test_checks_synthesis_passes_fail(
        self,
        kb_store: KnowledgeBaseStore,
        report_store: ReportPackStore,
        evidence_store: VerificationEvidenceStore,
        task: Task,
    ) -> None:
        # No synthesis log - should fail SYNTHESIS_PASSES
        use_case = VerifyResearchConditions(kb_store, report_store, evidence_store)
        result = await use_case.run(task)

        assert result["SYNTHESIS_PASSES"] is False

    @pytest.mark.asyncio
    async def test_checks_synthesis_passes_pass(
        self,
        kb_store: KnowledgeBaseStore,
        report_store: ReportPackStore,
        evidence_store: VerificationEvidenceStore,
        task: Task,
    ) -> None:
        # Create synthesis log using kb_store
        kb_store.save_synthesis_log({"passed": True, "completed_passes": 1})

        use_case = VerifyResearchConditions(kb_store, report_store, evidence_store)
        result = await use_case.run(task)

        assert result["SYNTHESIS_PASSES"] is True

    @pytest.mark.asyncio
    async def test_checks_report_artifacts_fail(
        self,
        kb_store: KnowledgeBaseStore,
        report_store: ReportPackStore,
        evidence_store: VerificationEvidenceStore,
        task: Task,
    ) -> None:
        # No report manifest - should fail REPORT_ARTIFACTS_PRESENT
        use_case = VerifyResearchConditions(kb_store, report_store, evidence_store)
        result = await use_case.run(task)

        assert result["REPORT_ARTIFACTS_PRESENT"] is False

    @pytest.mark.asyncio
    async def test_creates_evidence_directory(
        self,
        kb_store: KnowledgeBaseStore,
        report_store: ReportPackStore,
        evidence_store: VerificationEvidenceStore,
        task: Task,
        tmp_path: Path,
    ) -> None:
        use_case = VerifyResearchConditions(kb_store, report_store, evidence_store)
        await use_case.run(task)

        evidence_dir = tmp_path / "evidence" / "conditions"
        assert evidence_dir.exists()

    @pytest.mark.asyncio
    async def test_saves_sources_evidence(
        self,
        kb_store: KnowledgeBaseStore,
        report_store: ReportPackStore,
        evidence_store: VerificationEvidenceStore,
        task: Task,
        tmp_path: Path,
    ) -> None:
        use_case = VerifyResearchConditions(kb_store, report_store, evidence_store)
        await use_case.run(task)

        evidence_file = tmp_path / "evidence" / "conditions" / "min_sources" / "sources_count.json"
        assert evidence_file.exists()

    @pytest.mark.asyncio
    async def test_saves_coverage_evidence(
        self,
        kb_store: KnowledgeBaseStore,
        report_store: ReportPackStore,
        evidence_store: VerificationEvidenceStore,
        task: Task,
        tmp_path: Path,
    ) -> None:
        use_case = VerifyResearchConditions(kb_store, report_store, evidence_store)
        await use_case.run(task)

        evidence_file = tmp_path / "evidence" / "conditions" / "coverage" / "coverage_report.json"
        assert evidence_file.exists()

    @pytest.mark.asyncio
    async def test_saves_artifacts_evidence(
        self,
        kb_store: KnowledgeBaseStore,
        report_store: ReportPackStore,
        evidence_store: VerificationEvidenceStore,
        task: Task,
        tmp_path: Path,
    ) -> None:
        use_case = VerifyResearchConditions(kb_store, report_store, evidence_store)
        await use_case.run(task)

        evidence_file = (
            tmp_path
            / "evidence"
            / "conditions"
            / "report_artifacts"
            / "report_artifacts_present.json"
        )
        assert evidence_file.exists()


class TestCountByType:
    def test_counts_single_type(self) -> None:
        source = MagicMock()
        source.source_type = "web"

        use_case = VerifyResearchConditions(MagicMock(), MagicMock(), MagicMock())
        counts = use_case._count_by_type([source, source])

        assert counts == {"web": 2}

    def test_counts_multiple_types(self) -> None:
        web_source = MagicMock()
        web_source.source_type = "web"
        arxiv_source = MagicMock()
        arxiv_source.source_type = "arxiv"

        use_case = VerifyResearchConditions(MagicMock(), MagicMock(), MagicMock())
        counts = use_case._count_by_type([web_source, arxiv_source, web_source])

        assert counts == {"web": 2, "arxiv": 1}


class TestCalculateCoverage:
    def test_empty_topics_returns_full_coverage(self) -> None:
        use_case = VerifyResearchConditions(MagicMock(), MagicMock(), MagicMock())
        coverage = use_case._calculate_coverage([], [])
        assert coverage == 1.0

    def test_no_findings_returns_zero(self) -> None:
        use_case = VerifyResearchConditions(MagicMock(), MagicMock(), MagicMock())
        coverage = use_case._calculate_coverage([], ["topic1"])
        assert coverage == 0.0

    def test_partial_coverage(self) -> None:
        finding = MagicMock()
        finding.topics = ["topic1"]

        use_case = VerifyResearchConditions(MagicMock(), MagicMock(), MagicMock())
        coverage = use_case._calculate_coverage([finding], ["topic1", "topic2"])
        assert coverage == 0.5


class TestGetCoveredTopics:
    def test_returns_covered(self) -> None:
        finding = MagicMock()
        finding.topics = ["Topic1"]

        use_case = VerifyResearchConditions(MagicMock(), MagicMock(), MagicMock())
        covered = use_case._get_covered_topics([finding], ["Topic1", "Topic2"])
        assert "Topic1" in covered

    def test_returns_empty_when_none_covered(self) -> None:
        finding = MagicMock()
        finding.topics = ["Other"]

        use_case = VerifyResearchConditions(MagicMock(), MagicMock(), MagicMock())
        covered = use_case._get_covered_topics([finding], ["Topic1"])
        assert covered == []


class TestGetUncoveredTopics:
    def test_returns_uncovered(self) -> None:
        finding = MagicMock()
        finding.topics = ["topic1"]

        use_case = VerifyResearchConditions(MagicMock(), MagicMock(), MagicMock())
        uncovered = use_case._get_uncovered_topics([finding], ["topic1", "topic2"])
        assert "topic2" in uncovered

    def test_returns_all_when_none_covered(self) -> None:
        use_case = VerifyResearchConditions(MagicMock(), MagicMock(), MagicMock())
        uncovered = use_case._get_uncovered_topics([], ["topic1", "topic2"])
        assert uncovered == ["topic1", "topic2"]
