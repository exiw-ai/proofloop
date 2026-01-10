"""Tests for KnowledgeBaseStore."""

from pathlib import Path
from uuid import uuid4

import pytest

from src.domain.entities import Excerpt, Finding
from src.infrastructure.research.knowledge_base_store import KnowledgeBaseStore


@pytest.fixture
def store(tmp_path: Path) -> KnowledgeBaseStore:
    return KnowledgeBaseStore(base_path=tmp_path)


class TestSaveSource:
    @pytest.mark.asyncio
    async def test_saves_new_source(self, store: KnowledgeBaseStore) -> None:
        source, is_dup = await store.save_source(
            url="https://example.com/article",
            content=b"<html><body>Test content</body></html>",
            source_type="web",
            title="Test Article",
        )

        assert not is_dup
        assert source.url == "https://example.com/article"
        assert source.title == "Test Article"
        assert source.content_hash.startswith("sha256:")

    @pytest.mark.asyncio
    async def test_creates_raw_and_text_files(self, store: KnowledgeBaseStore) -> None:
        source, _ = await store.save_source(
            url="https://example.com",
            content=b"Hello World",
            source_type="web",
            mime_type="text/plain",
        )

        raw_path = store.kb_path / source.raw_path
        text_path = store.kb_path / source.text_path

        assert raw_path.exists()
        assert text_path.exists()

    @pytest.mark.asyncio
    async def test_detects_duplicate_by_canonical_url(self, store: KnowledgeBaseStore) -> None:
        await store.save_source(
            url="https://www.example.com/page",
            content=b"Content 1",
            source_type="web",
        )

        source2, is_dup = await store.save_source(
            url="https://example.com/page",
            content=b"Content 2",
            source_type="web",
        )

        assert is_dup

    @pytest.mark.asyncio
    async def test_detects_duplicate_by_locator(self, store: KnowledgeBaseStore) -> None:
        await store.save_source(
            url="https://arxiv.org/abs/2301.12345",
            content=b"Paper 1",
            source_type="arxiv",
            locator={"arxiv_id": "2301.12345"},
        )

        source2, is_dup = await store.save_source(
            url="https://arxiv.org/pdf/2301.12345.pdf",
            content=b"Paper 2",
            source_type="arxiv",
            locator={"arxiv_id": "2301.12345"},
        )

        assert is_dup


class TestSaveAndLoadFinding:
    @pytest.mark.asyncio
    async def test_saves_and_loads_finding(self, store: KnowledgeBaseStore) -> None:
        source_id = uuid4()
        finding = Finding(
            id=uuid4(),
            source_id=source_id,
            source_key="test_source",
            excerpt_ref="excerpts/test.json",
            content="Test finding content",
            finding_type="fact",
            confidence=0.9,
            topics=["security"],
        )

        await store.save_finding(finding)
        loaded = await store.load_finding(finding.id)

        assert loaded is not None
        assert loaded.id == finding.id
        assert loaded.content == finding.content

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_finding(self, store: KnowledgeBaseStore) -> None:
        loaded = await store.load_finding(uuid4())
        assert loaded is None


class TestSaveAndLoadExcerpt:
    @pytest.mark.asyncio
    async def test_saves_and_loads_excerpt(self, store: KnowledgeBaseStore) -> None:
        source_id = uuid4()
        excerpt = Excerpt(
            id=uuid4(),
            source_id=source_id,
            text="Supporting text fragment",
            location="page 5, section 3.2",
        )

        await store.save_excerpt(excerpt)
        loaded = await store.load_excerpt(excerpt.id)

        assert loaded is not None
        assert loaded.id == excerpt.id
        assert loaded.text == excerpt.text

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_excerpt(self, store: KnowledgeBaseStore) -> None:
        loaded = await store.load_excerpt(uuid4())
        assert loaded is None


class TestLoadSource:
    @pytest.mark.asyncio
    async def test_loads_saved_source(self, store: KnowledgeBaseStore) -> None:
        source, _ = await store.save_source(
            url="https://example.com",
            content=b"Content",
            source_type="web",
            title="Test",
        )

        loaded = await store.load_source(source.id)

        assert loaded is not None
        assert loaded.id == source.id
        assert loaded.title == source.title

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_source(self, store: KnowledgeBaseStore) -> None:
        loaded = await store.load_source(uuid4())
        assert loaded is None


class TestListMethods:
    @pytest.mark.asyncio
    async def test_list_sources(self, store: KnowledgeBaseStore) -> None:
        await store.save_source(
            url="https://example1.com",
            content=b"Content 1",
            source_type="web",
        )
        await store.save_source(
            url="https://example2.com",
            content=b"Content 2",
            source_type="web",
        )

        sources = await store.list_sources()

        assert len(sources) == 2

    @pytest.mark.asyncio
    async def test_list_sources_empty(self, store: KnowledgeBaseStore) -> None:
        sources = await store.list_sources()
        assert sources == []

    @pytest.mark.asyncio
    async def test_list_findings(self, store: KnowledgeBaseStore) -> None:
        source_id = uuid4()
        for i in range(3):
            finding = Finding(
                id=uuid4(),
                source_id=source_id,
                source_key=f"source_{i}",
                excerpt_ref=f"excerpts/{i}.json",
                content=f"Finding {i}",
                finding_type="fact",
                confidence=0.8,
                topics=["test"],
            )
            await store.save_finding(finding)

        findings = await store.list_findings()

        assert len(findings) == 3

    @pytest.mark.asyncio
    async def test_list_findings_empty(self, store: KnowledgeBaseStore) -> None:
        findings = await store.list_findings()
        assert findings == []

    @pytest.mark.asyncio
    async def test_list_excerpts(self, store: KnowledgeBaseStore) -> None:
        source_id = uuid4()
        for i in range(2):
            excerpt = Excerpt(
                id=uuid4(),
                source_id=source_id,
                text=f"Excerpt {i}",
                location=f"page {i}",
            )
            await store.save_excerpt(excerpt)

        excerpts = await store.list_excerpts()

        assert len(excerpts) == 2

    @pytest.mark.asyncio
    async def test_list_excerpts_empty(self, store: KnowledgeBaseStore) -> None:
        excerpts = await store.list_excerpts()
        assert excerpts == []


class TestBuildKnowledgeBase:
    @pytest.mark.asyncio
    async def test_builds_knowledge_base(self, store: KnowledgeBaseStore) -> None:
        task_id = uuid4()

        # Add a source
        source, _ = await store.save_source(
            url="https://example.com",
            content=b"Content",
            source_type="web",
        )

        # Add a finding
        finding = Finding(
            id=uuid4(),
            source_id=source.id,
            source_key=source.source_key,
            excerpt_ref="excerpts/test.json",
            content="Finding",
            finding_type="fact",
            confidence=0.9,
            topics=["test"],
        )
        await store.save_finding(finding)

        kb = await store.build_knowledge_base(task_id)

        assert kb.task_id == task_id
        assert source.id in kb.sources
        assert finding.id in kb.findings
        assert source.source_key in kb.source_key_map


class TestMimeTypeHandling:
    @pytest.mark.asyncio
    async def test_html_extension(self, store: KnowledgeBaseStore) -> None:
        source, _ = await store.save_source(
            url="https://example.com",
            content=b"<html><body>Test</body></html>",
            source_type="web",
            mime_type="text/html",
        )

        assert source.raw_path.endswith(".html")

    @pytest.mark.asyncio
    async def test_pdf_extension(self, store: KnowledgeBaseStore) -> None:
        source, _ = await store.save_source(
            url="https://example.com/doc.pdf",
            content=b"PDF content",
            source_type="web",
            mime_type="application/pdf",
        )

        assert source.raw_path.endswith(".pdf")

    @pytest.mark.asyncio
    async def test_plain_text_extension(self, store: KnowledgeBaseStore) -> None:
        source, _ = await store.save_source(
            url="https://example.com/readme.txt",
            content=b"Plain text",
            source_type="web",
            mime_type="text/plain",
        )

        assert source.raw_path.endswith(".txt")


class TestTextExtraction:
    @pytest.mark.asyncio
    async def test_extracts_plain_text(self, store: KnowledgeBaseStore) -> None:
        source, _ = await store.save_source(
            url="https://example.com",
            content=b"Hello World",
            source_type="web",
            mime_type="text/plain",
        )

        text_content = (store.kb_path / source.text_path).read_text()
        assert "Hello World" in text_content

    @pytest.mark.asyncio
    async def test_handles_html_extraction(self, store: KnowledgeBaseStore) -> None:
        source, _ = await store.save_source(
            url="https://example.com",
            content=b"<html><body><p>Test paragraph</p></body></html>",
            source_type="web",
            mime_type="text/html",
        )

        text_content = (store.kb_path / source.text_path).read_text()
        # Should have extracted text (exact format depends on trafilatura availability)
        assert len(text_content) > 0

    @pytest.mark.asyncio
    async def test_handles_extraction_error(self, store: KnowledgeBaseStore) -> None:
        # Non-UTF8 content should still be handled
        source, _ = await store.save_source(
            url="https://example.com",
            content=b"\xff\xfe Invalid UTF8",
            source_type="web",
            mime_type="text/plain",
        )

        # Should still create files
        assert (store.kb_path / source.text_path).exists()
