"""Tests for SourceDeduplicator."""

from datetime import datetime
from uuid import uuid4

import pytest

from src.domain.entities.source import FetchMeta, Source
from src.domain.services.source_deduplicator import SourceDeduplicator
from src.domain.value_objects import SourceLocator


@pytest.fixture
def deduplicator() -> SourceDeduplicator:
    return SourceDeduplicator()


@pytest.fixture
def source_factory():
    def _create(
        url: str = "https://example.com",
        canonical_url: str | None = None,
        locator: SourceLocator | None = None,
    ) -> Source:
        return Source(
            id=uuid4(),
            source_key="test",
            title="Test Source",
            url=url,
            canonical_url=canonical_url or url,
            retrieved_at=datetime.now(),
            content_hash="abc123",
            locator=locator or SourceLocator(),
            source_type="web",
            raw_path="sources/test.html",
            text_path="sources/test.txt",
            fetch_meta=FetchMeta(
                http_status=200,
                final_url=url,
                mime_type="text/html",
                size_bytes=1000,
                extract_method="html2text",
            ),
        )

    return _create


class TestIsDuplicate:
    def test_not_duplicate_empty_list(self, deduplicator: SourceDeduplicator) -> None:
        is_dup, existing = deduplicator.is_duplicate(
            "https://example.com",
            SourceLocator(),
            [],
        )
        assert not is_dup
        assert existing is None

    def test_duplicate_by_canonical_url(
        self, deduplicator: SourceDeduplicator, source_factory
    ) -> None:
        source1 = source_factory(canonical_url="https://example.com/article")
        is_dup, existing = deduplicator.is_duplicate(
            "https://example.com/article",
            SourceLocator(),
            [source1],
        )
        assert is_dup
        assert existing == source1

    def test_duplicate_by_doi(self, deduplicator: SourceDeduplicator, source_factory) -> None:
        source1 = source_factory(locator=SourceLocator(doi="10.1234/test"))
        is_dup, existing = deduplicator.is_duplicate(
            "https://different.com",
            SourceLocator(doi="10.1234/test"),
            [source1],
        )
        assert is_dup
        assert existing == source1

    def test_duplicate_by_arxiv_id(self, deduplicator: SourceDeduplicator, source_factory) -> None:
        source1 = source_factory(locator=SourceLocator(arxiv_id="2301.12345"))
        is_dup, existing = deduplicator.is_duplicate(
            "https://different.com",
            SourceLocator(arxiv_id="2301.12345"),
            [source1],
        )
        assert is_dup
        assert existing == source1

    def test_duplicate_by_github_sha(
        self, deduplicator: SourceDeduplicator, source_factory
    ) -> None:
        source1 = source_factory(locator=SourceLocator(github_sha="abc123def456"))
        is_dup, existing = deduplicator.is_duplicate(
            "https://different.com",
            SourceLocator(github_sha="abc123def456"),
            [source1],
        )
        assert is_dup
        assert existing == source1

    def test_not_duplicate_different_urls_and_locators(
        self, deduplicator: SourceDeduplicator, source_factory
    ) -> None:
        source1 = source_factory(
            canonical_url="https://example.com/article1",
            locator=SourceLocator(doi="10.1234/test1"),
        )
        is_dup, existing = deduplicator.is_duplicate(
            "https://example.com/article2",
            SourceLocator(doi="10.1234/test2"),
            [source1],
        )
        assert not is_dup
        assert existing is None


class TestFindDuplicates:
    def test_no_duplicates(self, deduplicator: SourceDeduplicator, source_factory) -> None:
        sources = [
            source_factory(canonical_url="https://example.com/1"),
            source_factory(canonical_url="https://example.com/2"),
            source_factory(canonical_url="https://example.com/3"),
        ]
        duplicates = deduplicator.find_duplicates(sources)
        assert duplicates == []

    def test_finds_duplicates(self, deduplicator: SourceDeduplicator, source_factory) -> None:
        sources = [
            source_factory(canonical_url="https://example.com/1"),
            source_factory(canonical_url="https://example.com/1"),
            source_factory(canonical_url="https://example.com/2"),
        ]
        duplicates = deduplicator.find_duplicates(sources)
        assert len(duplicates) == 1
        assert duplicates[0][0] == sources[1]
        assert duplicates[0][1] == sources[0]

    def test_finds_multiple_duplicate_pairs(
        self, deduplicator: SourceDeduplicator, source_factory
    ) -> None:
        sources = [
            source_factory(canonical_url="https://example.com/1"),
            source_factory(canonical_url="https://example.com/1"),
            source_factory(canonical_url="https://example.com/2"),
            source_factory(canonical_url="https://example.com/2"),
        ]
        duplicates = deduplicator.find_duplicates(sources)
        assert len(duplicates) == 2

    def test_finds_duplicates_by_locator(
        self, deduplicator: SourceDeduplicator, source_factory
    ) -> None:
        sources = [
            source_factory(
                canonical_url="https://a.com", locator=SourceLocator(doi="10.1234/test")
            ),
            source_factory(
                canonical_url="https://b.com", locator=SourceLocator(doi="10.1234/test")
            ),
        ]
        duplicates = deduplicator.find_duplicates(sources)
        assert len(duplicates) == 1
