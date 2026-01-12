import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from src.domain.entities import (
    ContextRefPayload,
    KeyFinding,
    LLMHandoff,
    SourceReference,
)


class LLMHandoffStore:
    """Store for LLM handoff artifacts."""

    def __init__(self, base_path: Path):
        self.base_path = base_path

    async def save_handoff(self, handoff: LLMHandoff) -> str:
        """Save the LLM handoff payload."""
        payload_path = self.base_path / "derive_payload.json"
        payload_path.parent.mkdir(parents=True, exist_ok=True)

        payload_path.write_text(
            handoff.model_dump_json(indent=2),
            encoding="utf-8",
        )

        return str(payload_path.relative_to(self.base_path.parent))

    async def load_handoff(self) -> LLMHandoff | None:
        """Load the LLM handoff payload."""
        payload_path = self.base_path / "derive_payload.json"
        if not payload_path.exists():
            return None

        data = json.loads(payload_path.read_text(encoding="utf-8"))
        return LLMHandoff.model_validate(data)

    async def create_handoff(
        self,
        research_task_id: UUID,
        headline: str,
        goals: list[str],
        constraints: list[str],
        recommended_approach: str,
        key_findings: list[KeyFinding],
        source_references: list[SourceReference],
        context_refs: list[ContextRefPayload],
        suggested_blocking_conditions: list[str],
        recommended_checks: list[str],
        risks: list[str],
        assumptions: list[str],
        target_workspace_hint: str | None = None,
    ) -> LLMHandoff:
        """Create a new LLM handoff payload."""
        return LLMHandoff(
            schema_version="1.0",
            research_task_id=research_task_id,
            created_at=datetime.now(UTC),
            headline=headline,
            goals=goals,
            constraints=constraints,
            recommended_approach=recommended_approach,
            key_findings=key_findings,
            source_references=source_references,
            context_refs=context_refs,
            suggested_blocking_conditions=suggested_blocking_conditions,
            recommended_checks=recommended_checks,
            risks=risks,
            assumptions=assumptions,
            target_workspace_hint=target_workspace_hint,
        )

    def handoff_exists(self) -> bool:
        """Check if handoff payload exists."""
        return (self.base_path / "derive_payload.json").exists()
