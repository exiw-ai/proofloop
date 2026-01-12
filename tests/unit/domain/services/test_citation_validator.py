"""Tests for CitationValidator."""

from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from src.domain.entities.source import FetchMeta, Source
from src.domain.services.citation_validator import CitationValidator


@pytest.fixture
def validator() -> CitationValidator:
    return CitationValidator()


@pytest.fixture
def valid_source() -> Source:
    return Source(
        id=uuid4(),
        source_key="valid_source",
        title="Test Source",
        url="https://example.com/article",
        canonical_url="https://example.com/article",
        retrieved_at=datetime.now(),
        content_hash="abc123",
        source_type="web",
        raw_path="sources/valid_source.html",
        text_path="sources/valid_source.txt",
        fetch_meta=FetchMeta(
            http_status=200,
            final_url="https://example.com/article",
            mime_type="text/html",
            size_bytes=1000,
            extract_method="html2text",
        ),
    )


class TestExtractCitations:
    def test_extract_single_citation(self, validator: CitationValidator) -> None:
        text = "Some text with a citation [@source_1]."
        assert validator.extract_citations(text) == ["source_1"]

    def test_extract_multiple_citations(self, validator: CitationValidator) -> None:
        text = "Text [@source_1] and more [@source_2] and [@source-3]."
        citations = validator.extract_citations(text)
        assert "source_1" in citations
        assert "source_2" in citations
        assert "source-3" in citations

    def test_extract_no_citations(self, validator: CitationValidator) -> None:
        text = "Text without any citations."
        assert validator.extract_citations(text) == []

    def test_extract_citation_with_numbers(self, validator: CitationValidator) -> None:
        text = "Citation [@arxiv_2301_12345]."
        assert validator.extract_citations(text) == ["arxiv_2301_12345"]


class TestValidateCitations:
    def test_all_valid_citations(
        self, validator: CitationValidator, valid_source: Source, tmp_path: Path
    ) -> None:
        source_id = valid_source.id
        source_key_map = {valid_source.source_key: source_id}
        sources = {source_id: valid_source}

        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "sources").mkdir()
        (kb_path / "sources" / "valid_source.html").write_text("raw content")
        (kb_path / "sources" / "valid_source.txt").write_text("text content")

        report_files = {"report.md": "Text with citation [@valid_source]."}

        result = validator.validate_citations(report_files, source_key_map, sources, kb_path)

        assert result.passed
        assert result.all_citations_resolve
        assert "valid_source" in result.citations_valid

    def test_citation_not_found(self, validator: CitationValidator, tmp_path: Path) -> None:
        report_files = {"report.md": "Text with citation [@nonexistent]."}
        result = validator.validate_citations(report_files, {}, {}, tmp_path)

        assert not result.passed
        assert not result.all_citations_resolve
        assert "nonexistent" in result.citations_invalid

    def test_source_missing_url(self, validator: CitationValidator, tmp_path: Path) -> None:
        source = Source(
            id=uuid4(),
            source_key="no_url",
            title="Test",
            url="",
            canonical_url="",
            retrieved_at=datetime.now(),
            content_hash="abc",
            source_type="web",
            raw_path="sources/no_url.html",
            text_path="sources/no_url.txt",
            fetch_meta=FetchMeta(
                http_status=200,
                final_url="",
                mime_type="text/html",
                size_bytes=100,
                extract_method="html2text",
            ),
        )

        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "sources").mkdir()
        (kb_path / "sources" / "no_url.html").write_text("raw")
        (kb_path / "sources" / "no_url.txt").write_text("text")

        source_key_map = {"no_url": source.id}
        sources = {source.id: source}
        report_files = {"report.md": "[@no_url]"}

        result = validator.validate_citations(report_files, source_key_map, sources, kb_path)

        assert not result.all_sources_have_url

    def test_http_error_status(self, validator: CitationValidator, tmp_path: Path) -> None:
        source = Source(
            id=uuid4(),
            source_key="error_source",
            title="Test",
            url="https://example.com",
            canonical_url="https://example.com",
            retrieved_at=datetime.now(),
            content_hash="abc",
            source_type="web",
            raw_path="sources/error.html",
            text_path="sources/error.txt",
            fetch_meta=FetchMeta(
                http_status=404,
                final_url="https://example.com",
                mime_type="text/html",
                size_bytes=100,
                extract_method="html2text",
            ),
        )

        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "sources").mkdir()
        (kb_path / "sources" / "error.html").write_text("raw")
        (kb_path / "sources" / "error.txt").write_text("text")

        source_key_map = {"error_source": source.id}
        sources = {source.id: source}
        report_files = {"report.md": "[@error_source]"}

        result = validator.validate_citations(report_files, source_key_map, sources, kb_path)

        assert not result.all_http_status_ok
        assert not result.passed

    def test_missing_raw_file(
        self, validator: CitationValidator, valid_source: Source, tmp_path: Path
    ) -> None:
        source_id = valid_source.id
        source_key_map = {valid_source.source_key: source_id}
        sources = {source_id: valid_source}

        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "sources").mkdir()
        (kb_path / "sources" / "valid_source.txt").write_text("text")
        # raw file not created

        report_files = {"report.md": "[@valid_source]"}

        result = validator.validate_citations(report_files, source_key_map, sources, kb_path)

        assert not result.all_raw_files_exist
        assert not result.passed

    def test_multiple_report_files(
        self, validator: CitationValidator, valid_source: Source, tmp_path: Path
    ) -> None:
        source_id = valid_source.id
        source_key_map = {valid_source.source_key: source_id}
        sources = {source_id: valid_source}

        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "sources").mkdir()
        (kb_path / "sources" / "valid_source.html").write_text("raw")
        (kb_path / "sources" / "valid_source.txt").write_text("text")

        report_files = {
            "report1.md": "[@valid_source]",
            "report2.md": "[@valid_source] mentioned again",
        }

        result = validator.validate_citations(report_files, source_key_map, sources, kb_path)

        assert len(result.checked_files) == 2
        assert result.passed
