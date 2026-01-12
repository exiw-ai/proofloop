"""Tests for SourceKeyGenerator."""

import pytest

from src.domain.services.source_key_generator import SourceKeyGenerator


@pytest.fixture
def generator() -> SourceKeyGenerator:
    return SourceKeyGenerator()


class TestGenerateKey:
    def test_arxiv_url(self, generator: SourceKeyGenerator) -> None:
        url = "https://arxiv.org/abs/2301.12345"
        key = generator.generate_key(url, "arxiv")
        assert key == "arxiv_2301_12345"

    def test_arxiv_pdf_url(self, generator: SourceKeyGenerator) -> None:
        url = "https://arxiv.org/pdf/2301.12345.pdf"
        key = generator.generate_key(url, "arxiv")
        assert key == "arxiv_2301_12345"

    def test_github_repo_url(self, generator: SourceKeyGenerator) -> None:
        url = "https://github.com/anthropics/claude-code"
        key = generator.generate_key(url, "github")
        assert key == "github_anthropics_claude-code"

    def test_semantic_scholar_url(self, generator: SourceKeyGenerator) -> None:
        url = "https://www.semanticscholar.org/paper/abcdef1234567890"
        key = generator.generate_key(url, "semantic_scholar")
        assert key == "s2_abcdef12"

    def test_title_fallback(self, generator: SourceKeyGenerator) -> None:
        url = "https://example.com/random-page"
        key = generator.generate_key(url, "web", title="My Test Article Title")
        assert key == "my_test_article_titl"

    def test_title_special_chars(self, generator: SourceKeyGenerator) -> None:
        url = "https://example.com/random-page"
        key = generator.generate_key(url, "web", title="Hello! World? 123")
        assert key == "hello_world_123"

    def test_url_hash_fallback(self, generator: SourceKeyGenerator) -> None:
        url = "https://example.com/page"
        key = generator.generate_key(url, "web")
        assert key.startswith("example_")
        assert len(key) > 8  # domain + hash

    def test_github_short_path(self, generator: SourceKeyGenerator) -> None:
        url = "https://github.com/user"
        key = generator.generate_key(url, "github")
        assert key.startswith("github_")  # Falls through to hash


class TestCanonicalizeUrl:
    def test_removes_www(self, generator: SourceKeyGenerator) -> None:
        url = "https://www.example.com/page"
        canonical = generator.canonicalize_url(url)
        assert canonical == "https://example.com/page"

    def test_removes_trailing_slash(self, generator: SourceKeyGenerator) -> None:
        url = "https://example.com/page/"
        canonical = generator.canonicalize_url(url)
        assert canonical == "https://example.com/page"

    def test_removes_double_slashes(self, generator: SourceKeyGenerator) -> None:
        url = "https://example.com//page//article"
        canonical = generator.canonicalize_url(url)
        assert canonical == "https://example.com/page/article"

    def test_lowercases_domain(self, generator: SourceKeyGenerator) -> None:
        url = "https://EXAMPLE.COM/Page"
        canonical = generator.canonicalize_url(url)
        assert canonical == "https://example.com/Page"

    def test_preserves_path_case(self, generator: SourceKeyGenerator) -> None:
        url = "https://example.com/MyPath/Article"
        canonical = generator.canonicalize_url(url)
        assert canonical == "https://example.com/MyPath/Article"

    def test_keeps_root_slash(self, generator: SourceKeyGenerator) -> None:
        url = "https://example.com/"
        canonical = generator.canonicalize_url(url)
        assert canonical == "https://example.com/"

    def test_handles_no_path(self, generator: SourceKeyGenerator) -> None:
        url = "https://example.com"
        canonical = generator.canonicalize_url(url)
        assert canonical == "https://example.com"
