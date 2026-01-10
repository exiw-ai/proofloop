from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ResearchContextInfo:
    exists: bool
    derive_payload_path: str | None
    findings_path: str | None
    recommendations_path: str | None
    prompt_injection: str


class HydrateExternalContext:
    """Use case for discovering and loading research context for CODE
    pipeline."""

    def discover_research_context(self, workspace_path: Path) -> ResearchContextInfo:
        """Discover if research context exists in workspace.

        Returns information about available research context.
        """
        research_dir = workspace_path / ".proofloop" / "research"

        if not research_dir.exists():
            return ResearchContextInfo(
                exists=False,
                derive_payload_path=None,
                findings_path=None,
                recommendations_path=None,
                prompt_injection="",
            )

        derive_payload = research_dir / "derive_payload.json"
        findings = research_dir / "reports" / "findings.md"
        recommendations = research_dir / "reports" / "recommendations.md"

        if not derive_payload.exists():
            return ResearchContextInfo(
                exists=False,
                derive_payload_path=None,
                findings_path=None,
                recommendations_path=None,
                prompt_injection="",
            )

        # Build prompt injection
        prompt_injection = """
## Research Context Available

Research artifacts found at: .proofloop/research/
Key files to read:
- .proofloop/research/derive_payload.json (canonical source for implementation)
"""

        if findings.exists():
            prompt_injection += "- .proofloop/research/reports/findings.md\n"

        if recommendations.exists():
            prompt_injection += "- .proofloop/research/reports/recommendations.md\n"

        prompt_injection += """
Use Read tool to access this context for your plan.
The derive_payload.json contains structured information about:
- Goals and constraints from research
- Key findings with citations
- Recommended approach
- Suggested blocking conditions
"""

        return ResearchContextInfo(
            exists=True,
            derive_payload_path=str(derive_payload.relative_to(workspace_path)),
            findings_path=str(findings.relative_to(workspace_path)) if findings.exists() else None,
            recommendations_path=str(recommendations.relative_to(workspace_path))
            if recommendations.exists()
            else None,
            prompt_injection=prompt_injection,
        )

    def load_derive_payload(self, workspace_path: Path) -> dict[str, Any] | None:
        """Load the derive_payload.json if it exists."""
        payload_path = workspace_path / ".proofloop" / "research" / "derive_payload.json"

        if not payload_path.exists():
            return None

        import json

        result: dict[str, Any] = json.loads(payload_path.read_text(encoding="utf-8"))
        return result
