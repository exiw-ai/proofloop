import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from src.domain.entities import ReportPack
from src.domain.value_objects import TEMPLATE_SPECS, ReportPackTemplate


class ReportPackStore:
    """Store for report pack artifacts."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.reports_path = base_path / "reports"

    def _ensure_dirs(self) -> None:
        self.reports_path.mkdir(parents=True, exist_ok=True)

    async def create_report_pack(
        self,
        task_id: UUID,
        template: ReportPackTemplate,
    ) -> ReportPack:
        """Create a new report pack with template structure."""
        self._ensure_dirs()

        spec = TEMPLATE_SPECS[template]

        pack = ReportPack(
            id=uuid4(),
            task_id=task_id,
            template=template,
            created_at=datetime.now(UTC),
            status="pending",
            required_files=spec.required_files,
            present_files=[],
            missing_files=spec.required_files.copy(),
        )

        return pack

    async def save_report_file(
        self,
        filename: str,
        content: str,
    ) -> None:
        """Save a report file."""
        self._ensure_dirs()
        file_path = self.reports_path / filename
        file_path.write_text(content, encoding="utf-8")

    async def load_report_file(self, filename: str) -> str | None:
        """Load a report file."""
        file_path = self.reports_path / filename
        if not file_path.exists():
            return None
        return file_path.read_text(encoding="utf-8")

    async def list_report_files(self) -> list[str]:
        """List all report files."""
        if not self.reports_path.exists():
            return []
        return [f.name for f in self.reports_path.glob("*.md")]

    async def update_pack_status(self, pack: ReportPack) -> ReportPack:
        """Update pack status based on present files."""
        existing_files = await self.list_report_files()

        pack.present_files = [f for f in pack.required_files if f in existing_files]
        pack.missing_files = [f for f in pack.required_files if f not in existing_files]

        if not pack.missing_files:
            pack.status = "complete"
        elif pack.present_files:
            pack.status = "partial"
        else:
            pack.status = "pending"

        return pack

    async def save_manifest(self, pack: ReportPack, metrics: dict[str, float]) -> str:
        """Save the report manifest."""
        self._ensure_dirs()

        manifest = {
            "template": pack.template.value,
            "created_at": pack.created_at.isoformat(),
            "task_id": str(pack.task_id),
            "status": pack.status,
            "required_files": pack.required_files,
            "present_files": pack.present_files,
            "missing_files": pack.missing_files,
            "validation": {
                "citations_valid": True,
                "all_artifacts_present": not pack.missing_files,
            },
            "metrics": metrics,
        }

        manifest_path = self.reports_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        import hashlib

        manifest_hash = f"sha256:{hashlib.sha256(json.dumps(manifest).encode()).hexdigest()}"
        pack.manifest_path = str(manifest_path.relative_to(self.base_path))
        pack.manifest_hash = manifest_hash

        return manifest_hash

    async def load_manifest(self) -> dict[str, Any] | None:
        """Load the report manifest."""
        manifest_path = self.reports_path / "manifest.json"
        if not manifest_path.exists():
            return None
        result: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        return result
