"""Tests for ValidateCitations use case."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.use_cases.research.validate_citations import ValidateCitations
from src.domain.entities import ResearchInventory, Source, Task
from src.domain.entities.source import FetchMeta
from src.domain.value_objects import ResearchPreset, ResearchType, TaskStatus


@pytest.fixture
def mock_kb_store() -> AsyncMock:
    store = AsyncMock()
    store.list_sources.return_value = []
    store.kb_path = Path("/tmp/kb")
    return store


@pytest.fixture
def mock_report_store() -> AsyncMock:
    store = AsyncMock()
    store.list_report_files.return_value = []
    return store


@pytest.fixture
def task() -> Task:
    t = Task(
        id=uuid4(),
        description="Test task",
        goals=["test"],
        sources=[],
        status=TaskStatus.RESEARCH_REPORT_GENERATION,
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
def valid_source() -> Source:
    return Source(
        id=uuid4(),
        source_key="test_source",
        title="Test",
        url="https://example.com",
        canonical_url="https://example.com",
        retrieved_at=datetime.now(UTC),
        content_hash="sha256:abc",
        source_type="web",
        raw_path="sources/test.html",
        text_path="sources/test.txt",
        fetch_meta=FetchMeta(
            http_status=200,
            final_url="https://example.com",
            mime_type="text/html",
            size_bytes=100,
            extract_method="html2text",
        ),
    )


class TestValidateCitationsRun:
    @pytest.mark.asyncio
    async def test_passes_with_no_citations(
        self,
        mock_kb_store: AsyncMock,
        mock_report_store: AsyncMock,
        task: Task,
        tmp_path: Path,
    ) -> None:
        mock_report_store.list_report_files.return_value = ["summary.md"]
        mock_report_store.load_report_file.return_value = "No citations here."

        use_case = ValidateCitations(mock_kb_store, mock_report_store, tmp_path)
        passed = await use_case.run(task)

        assert passed
        assert task.status == TaskStatus.RESEARCH_CITATION_VALIDATE

    @pytest.mark.asyncio
    async def test_passes_with_valid_citation(
        self,
        mock_kb_store: AsyncMock,
        mock_report_store: AsyncMock,
        task: Task,
        valid_source: Source,
        tmp_path: Path,
    ) -> None:
        # Set up source
        mock_kb_store.list_sources.return_value = [valid_source]
        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "sources").mkdir()
        (kb_path / "sources" / "test.html").write_text("raw")
        (kb_path / "sources" / "test.txt").write_text("text")
        mock_kb_store.kb_path = kb_path

        # Set up report with citation
        mock_report_store.list_report_files.return_value = ["findings.md"]
        mock_report_store.load_report_file.return_value = "Findings [@test_source]."

        use_case = ValidateCitations(mock_kb_store, mock_report_store, tmp_path)
        passed = await use_case.run(task)

        assert passed

    @pytest.mark.asyncio
    async def test_fails_with_invalid_citation(
        self,
        mock_kb_store: AsyncMock,
        mock_report_store: AsyncMock,
        task: Task,
        tmp_path: Path,
    ) -> None:
        # No sources
        mock_kb_store.list_sources.return_value = []
        mock_kb_store.kb_path = tmp_path / "kb"

        # Report with citation that doesn't exist
        mock_report_store.list_report_files.return_value = ["findings.md"]
        mock_report_store.load_report_file.return_value = "Citation [@nonexistent]."

        use_case = ValidateCitations(mock_kb_store, mock_report_store, tmp_path)
        passed = await use_case.run(task)

        assert not passed

    @pytest.mark.asyncio
    async def test_saves_evidence_file(
        self,
        mock_kb_store: AsyncMock,
        mock_report_store: AsyncMock,
        task: Task,
        tmp_path: Path,
    ) -> None:
        mock_report_store.list_report_files.return_value = []
        mock_kb_store.kb_path = tmp_path / "kb"

        use_case = ValidateCitations(mock_kb_store, mock_report_store, tmp_path)
        await use_case.run(task)

        evidence_file = (
            tmp_path / "evidence" / "conditions" / "citations" / "citation_validation.json"
        )
        assert evidence_file.exists()

    @pytest.mark.asyncio
    async def test_handles_empty_report_content(
        self,
        mock_kb_store: AsyncMock,
        mock_report_store: AsyncMock,
        task: Task,
        tmp_path: Path,
    ) -> None:
        mock_report_store.list_report_files.return_value = ["empty.md"]
        mock_report_store.load_report_file.return_value = None
        mock_kb_store.kb_path = tmp_path / "kb"

        use_case = ValidateCitations(mock_kb_store, mock_report_store, tmp_path)
        passed = await use_case.run(task)

        # Should pass since no citations to validate
        assert passed
