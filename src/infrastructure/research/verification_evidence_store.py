import json
from pathlib import Path
from typing import Any


class VerificationEvidenceStore:
    """Store for verification condition evidence artifacts."""

    def __init__(self, research_path: Path):
        self._evidence_dir = research_path / "evidence" / "conditions"

    def save_evidence(self, condition_name: str, filename: str, data: dict[str, Any]) -> Path:
        """Save evidence data as JSON for a condition."""
        condition_dir = self._evidence_dir / condition_name
        condition_dir.mkdir(parents=True, exist_ok=True)

        file_path = condition_dir / f"{filename}.json"
        file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        return file_path

    def load_evidence(self, condition_name: str, filename: str) -> dict[str, Any] | None:
        """Load evidence data for a condition.

        Returns None if not exists.
        """
        file_path = self._evidence_dir / condition_name / f"{filename}.json"

        if not file_path.exists():
            return None

        result: dict[str, Any] = json.loads(file_path.read_text(encoding="utf-8"))
        return result

    def evidence_exists(self, condition_name: str, filename: str) -> bool:
        """Check if evidence file exists for a condition."""
        file_path = self._evidence_dir / condition_name / f"{filename}.json"
        return file_path.exists()
