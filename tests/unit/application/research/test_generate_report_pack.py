"""Tests for GenerateReportPack use case."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.use_cases.research.generate_report_pack import GenerateReportPack
from src.domain.entities import Finding, ResearchInventory, Source, Task
from src.domain.entities.report_pack import ReportPack
from src.domain.entities.source import FetchMeta
from src.domain.ports.agent_port import AgentResult
from src.domain.value_objects import (
    ReportPackTemplate,
    ResearchPreset,
    ResearchType,
    TaskStatus,
)


@pytest.fixture
def mock_agent() -> AsyncMock:
    agent = AsyncMock()
    agent.execute.return_value = AgentResult(
        messages=[],
        final_response="Generated report content.",
        tools_used=[],
    )
    return agent


@pytest.fixture
def mock_kb_store() -> AsyncMock:
    store = AsyncMock()
    store.list_sources.return_value = []
    store.list_findings.return_value = []
    return store


@pytest.fixture
def mock_report_store() -> AsyncMock:
    store = AsyncMock()
    pack = ReportPack(
        id=uuid4(),
        task_id=uuid4(),
        template=ReportPackTemplate.GENERAL_DEFAULT,
        created_at=datetime.now(UTC),
        status="complete",
        required_files=["executive_summary.md"],
        present_files=["executive_summary.md"],
        missing_files=[],
    )
    store.create_report_pack.return_value = pack
    store.update_pack_status.return_value = pack
    return store


@pytest.fixture
def task() -> Task:
    t = Task(
        id=uuid4(),
        description="Test research",
        goals=["goal1"],
        sources=[],
        status=TaskStatus.RESEARCH_DEEPENING,
    )
    t.research_inventory = ResearchInventory(
        id=uuid4(),
        task_id=t.id,
        queries=[],
        required_topics=[],
        topic_synonyms={},
        sections=[],
        research_type=ResearchType.TECHNICAL,
        preset=ResearchPreset.STANDARD,
        created_at=datetime.now(UTC),
    )
    return t


@pytest.fixture
def sample_source() -> Source:
    return Source(
        id=uuid4(),
        source_key="sample_source",
        title="Sample Paper",
        url="https://example.com/paper",
        canonical_url="https://example.com/paper",
        retrieved_at=datetime.now(UTC),
        content_hash="sha256:abc",
        source_type="web",
        raw_path="sources/sample.html",
        text_path="sources/sample.txt",
        fetch_meta=FetchMeta(
            http_status=200,
            final_url="https://example.com/paper",
            mime_type="text/html",
            size_bytes=5000,
            extract_method="html2text",
        ),
    )


@pytest.fixture
def sample_finding(sample_source: Source) -> Finding:
    return Finding(
        id=uuid4(),
        source_id=sample_source.id,
        source_key=sample_source.source_key,
        excerpt_ref="excerpts/exc1.json",
        content="Important finding about research.",
        finding_type="fact",
        confidence=0.9,
        topics=["security"],
    )


class TestGenerateReportPackRun:
    @pytest.mark.asyncio
    async def test_generates_report_files(
        self,
        mock_agent: AsyncMock,
        mock_kb_store: AsyncMock,
        mock_report_store: AsyncMock,
        task: Task,
    ) -> None:
        use_case = GenerateReportPack(mock_agent, mock_kb_store, mock_report_store)

        success = await use_case.run(task, ReportPackTemplate.GENERAL_DEFAULT)

        assert success
        assert task.status == TaskStatus.RESEARCH_REPORT_GENERATION
        mock_report_store.save_report_file.assert_called()
        mock_report_store.save_manifest.assert_called_once()

    @pytest.mark.asyncio
    async def test_transitions_task_status(
        self,
        mock_agent: AsyncMock,
        mock_kb_store: AsyncMock,
        mock_report_store: AsyncMock,
        task: Task,
    ) -> None:
        use_case = GenerateReportPack(mock_agent, mock_kb_store, mock_report_store)

        await use_case.run(task, ReportPackTemplate.GENERAL_DEFAULT)

        assert task.status == TaskStatus.RESEARCH_REPORT_GENERATION

    @pytest.mark.asyncio
    async def test_uses_sources_in_prompt(
        self,
        mock_agent: AsyncMock,
        mock_kb_store: AsyncMock,
        mock_report_store: AsyncMock,
        task: Task,
        sample_source: Source,
    ) -> None:
        mock_kb_store.list_sources.return_value = [sample_source]

        use_case = GenerateReportPack(mock_agent, mock_kb_store, mock_report_store)
        await use_case.run(task, ReportPackTemplate.GENERAL_DEFAULT)

        # Verify agent was called with source info in prompt
        call_args = mock_agent.execute.call_args
        prompt = call_args.kwargs.get("prompt", "")
        assert "sample_source" in prompt or "Available Sources" in prompt

    @pytest.mark.asyncio
    async def test_uses_findings_in_prompt(
        self,
        mock_agent: AsyncMock,
        mock_kb_store: AsyncMock,
        mock_report_store: AsyncMock,
        task: Task,
        sample_finding: Finding,
    ) -> None:
        mock_kb_store.list_findings.return_value = [sample_finding]

        use_case = GenerateReportPack(mock_agent, mock_kb_store, mock_report_store)
        await use_case.run(task, ReportPackTemplate.GENERAL_DEFAULT)

        call_args = mock_agent.execute.call_args
        prompt = call_args.kwargs.get("prompt", "")
        assert "Key Findings" in prompt

    @pytest.mark.asyncio
    async def test_returns_false_on_incomplete_pack(
        self,
        mock_agent: AsyncMock,
        mock_kb_store: AsyncMock,
        mock_report_store: AsyncMock,
        task: Task,
    ) -> None:
        # Make pack incomplete
        incomplete_pack = ReportPack(
            id=uuid4(),
            task_id=task.id,
            template=ReportPackTemplate.GENERAL_DEFAULT,
            created_at=datetime.now(UTC),
            status="partial",
            required_files=["summary.md", "findings.md"],
            present_files=["summary.md"],
            missing_files=["findings.md"],
        )
        mock_report_store.update_pack_status.return_value = incomplete_pack

        use_case = GenerateReportPack(mock_agent, mock_kb_store, mock_report_store)
        success = await use_case.run(task, ReportPackTemplate.GENERAL_DEFAULT)

        assert not success
