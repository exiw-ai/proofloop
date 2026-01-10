"""Tests for HydrateExternalContext use case."""

import json
from pathlib import Path

import pytest

from src.application.use_cases.hydrate_external_context import HydrateExternalContext


@pytest.fixture
def use_case() -> HydrateExternalContext:
    return HydrateExternalContext()


class TestDiscoverResearchContext:
    def test_returns_not_exists_when_no_research_dir(
        self, use_case: HydrateExternalContext, tmp_path: Path
    ) -> None:
        result = use_case.discover_research_context(tmp_path)

        assert result.exists is False
        assert result.derive_payload_path is None
        assert result.findings_path is None
        assert result.recommendations_path is None
        assert result.prompt_injection == ""

    def test_returns_not_exists_when_no_derive_payload(
        self, use_case: HydrateExternalContext, tmp_path: Path
    ) -> None:
        # Create research dir without derive_payload.json
        research_dir = tmp_path / ".proofloop" / "research"
        research_dir.mkdir(parents=True)

        result = use_case.discover_research_context(tmp_path)

        assert result.exists is False

    def test_returns_exists_with_derive_payload(
        self, use_case: HydrateExternalContext, tmp_path: Path
    ) -> None:
        # Create research dir with derive_payload.json
        research_dir = tmp_path / ".proofloop" / "research"
        research_dir.mkdir(parents=True)
        payload = research_dir / "derive_payload.json"
        payload.write_text(json.dumps({"headline": "Test"}))

        result = use_case.discover_research_context(tmp_path)

        assert result.exists is True
        assert result.derive_payload_path == ".proofloop/research/derive_payload.json"
        assert "Research Context Available" in result.prompt_injection

    def test_includes_findings_path_when_exists(
        self, use_case: HydrateExternalContext, tmp_path: Path
    ) -> None:
        # Create research dir with derive_payload.json and findings
        research_dir = tmp_path / ".proofloop" / "research"
        research_dir.mkdir(parents=True)
        payload = research_dir / "derive_payload.json"
        payload.write_text(json.dumps({"headline": "Test"}))

        reports_dir = research_dir / "reports"
        reports_dir.mkdir()
        findings = reports_dir / "findings.md"
        findings.write_text("# Findings")

        result = use_case.discover_research_context(tmp_path)

        assert result.exists is True
        assert result.findings_path == ".proofloop/research/reports/findings.md"
        assert "findings.md" in result.prompt_injection

    def test_includes_recommendations_path_when_exists(
        self, use_case: HydrateExternalContext, tmp_path: Path
    ) -> None:
        # Create research dir with all artifacts
        research_dir = tmp_path / ".proofloop" / "research"
        research_dir.mkdir(parents=True)
        payload = research_dir / "derive_payload.json"
        payload.write_text(json.dumps({"headline": "Test"}))

        reports_dir = research_dir / "reports"
        reports_dir.mkdir()
        recommendations = reports_dir / "recommendations.md"
        recommendations.write_text("# Recommendations")

        result = use_case.discover_research_context(tmp_path)

        assert result.exists is True
        assert result.recommendations_path == ".proofloop/research/reports/recommendations.md"
        assert "recommendations.md" in result.prompt_injection


class TestLoadDerivePayload:
    def test_returns_none_when_not_exists(
        self, use_case: HydrateExternalContext, tmp_path: Path
    ) -> None:
        result = use_case.load_derive_payload(tmp_path)
        assert result is None

    def test_loads_payload_when_exists(
        self, use_case: HydrateExternalContext, tmp_path: Path
    ) -> None:
        # Create derive_payload.json
        research_dir = tmp_path / ".proofloop" / "research"
        research_dir.mkdir(parents=True)
        payload = research_dir / "derive_payload.json"
        payload_data = {
            "headline": "Implement feature",
            "goals": ["Goal 1"],
            "key_findings": [{"summary": "Finding 1"}],
        }
        payload.write_text(json.dumps(payload_data))

        result = use_case.load_derive_payload(tmp_path)

        assert result is not None
        assert result["headline"] == "Implement feature"
        assert len(result["goals"]) == 1
        assert len(result["key_findings"]) == 1
