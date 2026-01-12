"""Tests for CoverageCalculator."""

from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from src.domain.entities.finding import Finding
from src.domain.entities.source import FetchMeta, Source
from src.domain.services.coverage_calculator import CoverageCalculator


@pytest.fixture
def calculator() -> CoverageCalculator:
    return CoverageCalculator()


@pytest.fixture
def source_factory():
    def _create(key: str = "test_source") -> Source:
        return Source(
            id=uuid4(),
            source_key=key,
            title="Test Source",
            url="https://example.com",
            canonical_url="https://example.com",
            retrieved_at=datetime.now(),
            content_hash="abc123",
            source_type="web",
            raw_path=f"sources/{key}.html",
            text_path=f"sources/{key}.txt",
            fetch_meta=FetchMeta(
                http_status=200,
                final_url="https://example.com",
                mime_type="text/html",
                size_bytes=1000,
                extract_method="html2text",
            ),
        )

    return _create


@pytest.fixture
def finding_factory():
    def _create(source: Source, topics: list[str], excerpt_ref: str = "sources/ref.txt") -> Finding:
        return Finding(
            id=uuid4(),
            source_id=source.id,
            source_key=source.source_key,
            excerpt_ref=excerpt_ref,
            content="Test finding content",
            finding_type="fact",
            confidence=0.9,
            topics=topics,
        )

    return _create


class TestCalculateCoverage:
    def test_empty_required_topics(self, calculator: CoverageCalculator, tmp_path: Path) -> None:
        result = calculator.calculate_coverage(
            required_topics=[],
            topic_synonyms={},
            findings=[],
            sources={},
            knowledge_base_path=tmp_path,
        )

        assert result.passed
        assert result.actual_coverage == 1.0
        assert result.required_topics == []

    def test_all_topics_covered(
        self, calculator: CoverageCalculator, source_factory, finding_factory, tmp_path: Path
    ) -> None:
        source = source_factory("s1")
        findings = [
            finding_factory(source, ["security"]),
            finding_factory(source, ["performance"]),
        ]

        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "sources").mkdir()
        (kb_path / "sources" / "s1.html").write_text("raw")
        (kb_path / "sources" / "s1.txt").write_text("text")

        # Need to provide synonyms because the calculator only matches through synonym_map
        result = calculator.calculate_coverage(
            required_topics=["security", "performance"],
            topic_synonyms={"security": ["security"], "performance": ["performance"]},
            findings=findings,
            sources={source.id: source},
            knowledge_base_path=kb_path,
            threshold=0.8,
        )

        assert result.passed
        assert result.actual_coverage == 1.0
        assert len(result.covered_topics) == 2
        assert len(result.uncovered_topics) == 0

    def test_partial_coverage_below_threshold(
        self, calculator: CoverageCalculator, source_factory, finding_factory, tmp_path: Path
    ) -> None:
        source = source_factory("s1")
        findings = [finding_factory(source, ["security"])]

        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "sources").mkdir()
        (kb_path / "sources" / "s1.html").write_text("raw")
        (kb_path / "sources" / "s1.txt").write_text("text")

        result = calculator.calculate_coverage(
            required_topics=["security", "performance", "scalability"],
            topic_synonyms={
                "security": ["security"],
                "performance": ["performance"],
                "scalability": ["scalability"],
            },
            findings=findings,
            sources={source.id: source},
            knowledge_base_path=kb_path,
            threshold=0.8,
        )

        assert not result.passed
        assert result.actual_coverage < 0.8
        assert "security" in result.covered_topics
        assert "performance" in result.uncovered_topics

    def test_synonym_matching(
        self, calculator: CoverageCalculator, source_factory, finding_factory, tmp_path: Path
    ) -> None:
        source = source_factory("s1")
        findings = [finding_factory(source, ["auth"])]

        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "sources").mkdir()
        (kb_path / "sources" / "s1.html").write_text("raw")
        (kb_path / "sources" / "s1.txt").write_text("text")

        result = calculator.calculate_coverage(
            required_topics=["security"],
            topic_synonyms={"security": ["auth", "authentication", "authz"]},
            findings=findings,
            sources={source.id: source},
            knowledge_base_path=kb_path,
        )

        assert result.passed
        assert "security" in result.covered_topics

    def test_finding_without_excerpt_not_counted(
        self, calculator: CoverageCalculator, source_factory, tmp_path: Path
    ) -> None:
        source = source_factory("s1")
        finding = Finding(
            id=uuid4(),
            source_id=source.id,
            source_key=source.source_key,
            excerpt_ref="",  # No excerpt reference
            content="Test",
            finding_type="fact",
            confidence=0.9,
            topics=["security"],
        )

        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "sources").mkdir()
        (kb_path / "sources" / "s1.html").write_text("raw")
        (kb_path / "sources" / "s1.txt").write_text("text")

        result = calculator.calculate_coverage(
            required_topics=["security"],
            topic_synonyms={},
            findings=[finding],
            sources={source.id: source},
            knowledge_base_path=kb_path,
        )

        assert not result.passed
        assert "security" in result.uncovered_topics

    def test_missing_raw_file_not_counted(
        self, calculator: CoverageCalculator, source_factory, finding_factory, tmp_path: Path
    ) -> None:
        source = source_factory("s1")
        findings = [finding_factory(source, ["security"])]

        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "sources").mkdir()
        (kb_path / "sources" / "s1.txt").write_text("text only")
        # raw file not created

        result = calculator.calculate_coverage(
            required_topics=["security"],
            topic_synonyms={},
            findings=findings,
            sources={source.id: source},
            knowledge_base_path=kb_path,
        )

        assert not result.passed
        assert "security" in result.uncovered_topics

    def test_case_insensitive_topic_matching(
        self, calculator: CoverageCalculator, source_factory, finding_factory, tmp_path: Path
    ) -> None:
        source = source_factory("s1")
        findings = [finding_factory(source, ["SECURITY"])]

        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "sources").mkdir()
        (kb_path / "sources" / "s1.html").write_text("raw")
        (kb_path / "sources" / "s1.txt").write_text("text")

        result = calculator.calculate_coverage(
            required_topics=["security"],
            topic_synonyms={"security": ["security"]},
            findings=findings,
            sources={source.id: source},
            knowledge_base_path=kb_path,
        )

        assert result.passed
        assert "security" in result.covered_topics

    def test_topics_detail_populated(
        self, calculator: CoverageCalculator, source_factory, finding_factory, tmp_path: Path
    ) -> None:
        source = source_factory("s1")
        findings = [
            finding_factory(source, ["security"]),
            finding_factory(source, ["security"]),
        ]

        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "sources").mkdir()
        (kb_path / "sources" / "s1.html").write_text("raw")
        (kb_path / "sources" / "s1.txt").write_text("text")

        result = calculator.calculate_coverage(
            required_topics=["security", "performance"],
            topic_synonyms={"security": ["security"], "performance": ["performance"]},
            findings=findings,
            sources={source.id: source},
            knowledge_base_path=kb_path,
        )

        assert len(result.topics_detail) == 2
        security_detail = next(d for d in result.topics_detail if d.topic == "security")
        assert security_detail.finding_count == 2
        assert security_detail.has_valid_excerpts
