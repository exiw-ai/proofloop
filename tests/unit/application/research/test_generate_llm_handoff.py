"""Tests for GenerateLLMHandoff use case."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from src.application.use_cases.research.generate_llm_handoff import GenerateLLMHandoff
from src.domain.entities import Finding, ResearchInventory, Source, Task
from src.domain.entities.source import FetchMeta
from src.domain.ports.agent_port import AgentResult
from src.domain.value_objects import ResearchPreset, ResearchType, TaskStatus


@pytest.fixture
def mock_agent() -> AsyncMock:
    agent = AsyncMock()
    agent.execute.return_value = AgentResult(
        messages=[],
        final_response='{"headline": "Implement auth", "recommended_approach": "Use JWT", "risks": ["complexity"], "assumptions": ["python 3.11"]}',
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
    return AsyncMock()


@pytest.fixture
def mock_handoff_store() -> AsyncMock:
    store = AsyncMock()
    store.save_handoff.return_value = "derive_payload.json"
    return store


@pytest.fixture
def mock_repo_context_store() -> Mock:
    store = Mock()
    store.context_exists.return_value = False
    return store


@pytest.fixture
def task() -> Task:
    t = Task(
        id=uuid4(),
        description="Implement authentication",
        goals=["Secure login", "Token handling"],
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
def sample_source() -> Source:
    return Source(
        id=uuid4(),
        source_key="auth_paper",
        title="Authentication Best Practices",
        url="https://example.com/auth",
        canonical_url="https://example.com/auth",
        retrieved_at=datetime.now(UTC),
        content_hash="sha256:abc",
        source_type="web",
        raw_path="sources/auth.html",
        text_path="sources/auth.txt",
        fetch_meta=FetchMeta(
            http_status=200,
            final_url="https://example.com/auth",
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
        excerpt_ref=f"excerpts/{uuid4()}.json",
        content="JWT tokens should expire within 15 minutes.",
        finding_type="fact",
        confidence=0.9,
        topics=["security", "tokens"],
    )


class TestGenerateLLMHandoffRun:
    @pytest.mark.asyncio
    async def test_generates_handoff(
        self,
        mock_agent: AsyncMock,
        mock_kb_store: AsyncMock,
        mock_report_store: AsyncMock,
        mock_handoff_store: AsyncMock,
        mock_repo_context_store: Mock,
        task: Task,
        tmp_path: Path,
    ) -> None:
        use_case = GenerateLLMHandoff(
            mock_agent,
            mock_kb_store,
            mock_report_store,
            mock_handoff_store,
            mock_repo_context_store,
        )

        path = await use_case.run(task, tmp_path)

        assert path == "derive_payload.json"
        mock_handoff_store.save_handoff.assert_called_once()

    @pytest.mark.asyncio
    async def test_includes_findings_in_handoff(
        self,
        mock_agent: AsyncMock,
        mock_kb_store: AsyncMock,
        mock_report_store: AsyncMock,
        mock_handoff_store: AsyncMock,
        mock_repo_context_store: Mock,
        task: Task,
        sample_source: Source,
        sample_finding: Finding,
        tmp_path: Path,
    ) -> None:
        mock_kb_store.list_sources.return_value = [sample_source]
        mock_kb_store.list_findings.return_value = [sample_finding]

        use_case = GenerateLLMHandoff(
            mock_agent,
            mock_kb_store,
            mock_report_store,
            mock_handoff_store,
            mock_repo_context_store,
        )

        await use_case.run(task, tmp_path)

        # Check the saved handoff has findings
        call_args = mock_handoff_store.save_handoff.call_args
        handoff = call_args[0][0]
        assert len(handoff.key_findings) == 1
        assert handoff.key_findings[0].source_key == sample_source.source_key

    @pytest.mark.asyncio
    async def test_includes_source_references(
        self,
        mock_agent: AsyncMock,
        mock_kb_store: AsyncMock,
        mock_report_store: AsyncMock,
        mock_handoff_store: AsyncMock,
        mock_repo_context_store: Mock,
        task: Task,
        sample_source: Source,
        tmp_path: Path,
    ) -> None:
        mock_kb_store.list_sources.return_value = [sample_source]

        use_case = GenerateLLMHandoff(
            mock_agent,
            mock_kb_store,
            mock_report_store,
            mock_handoff_store,
            mock_repo_context_store,
        )

        await use_case.run(task, tmp_path)

        call_args = mock_handoff_store.save_handoff.call_args
        handoff = call_args[0][0]
        assert len(handoff.source_references) == 1
        assert handoff.source_references[0].url == sample_source.url

    @pytest.mark.asyncio
    async def test_fallback_on_invalid_json(
        self,
        mock_agent: AsyncMock,
        mock_kb_store: AsyncMock,
        mock_report_store: AsyncMock,
        mock_handoff_store: AsyncMock,
        mock_repo_context_store: Mock,
        task: Task,
        tmp_path: Path,
    ) -> None:
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="Not valid JSON",
            tools_used=[],
        )

        use_case = GenerateLLMHandoff(
            mock_agent,
            mock_kb_store,
            mock_report_store,
            mock_handoff_store,
            mock_repo_context_store,
        )

        await use_case.run(task, tmp_path)

        # Should still save handoff with task description as headline
        call_args = mock_handoff_store.save_handoff.call_args
        handoff = call_args[0][0]
        assert handoff.headline == task.description

    @pytest.mark.asyncio
    async def test_includes_context_refs(
        self,
        mock_agent: AsyncMock,
        mock_kb_store: AsyncMock,
        mock_report_store: AsyncMock,
        mock_handoff_store: AsyncMock,
        mock_repo_context_store: Mock,
        task: Task,
        tmp_path: Path,
    ) -> None:
        use_case = GenerateLLMHandoff(
            mock_agent,
            mock_kb_store,
            mock_report_store,
            mock_handoff_store,
            mock_repo_context_store,
        )

        await use_case.run(task, tmp_path)

        call_args = mock_handoff_store.save_handoff.call_args
        handoff = call_args[0][0]
        # Should always include reports context ref
        assert any(ref.kind == "reports" for ref in handoff.context_refs)

    @pytest.mark.asyncio
    async def test_includes_repo_context_if_exists(
        self,
        mock_agent: AsyncMock,
        mock_kb_store: AsyncMock,
        mock_report_store: AsyncMock,
        mock_handoff_store: AsyncMock,
        mock_repo_context_store: Mock,
        task: Task,
        tmp_path: Path,
    ) -> None:
        # Configure store to return True for context_exists
        mock_repo_context_store.context_exists.return_value = True

        use_case = GenerateLLMHandoff(
            mock_agent,
            mock_kb_store,
            mock_report_store,
            mock_handoff_store,
            mock_repo_context_store,
        )

        await use_case.run(task, tmp_path)

        call_args = mock_handoff_store.save_handoff.call_args
        handoff = call_args[0][0]
        # Should include both reports and repo_context
        kinds = [ref.kind for ref in handoff.context_refs]
        assert "reports" in kinds
        assert "repo_context" in kinds
