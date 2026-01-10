import json
from datetime import UTC, datetime
from pathlib import Path

from src.domain.entities import Task
from src.domain.services import CitationValidator
from src.domain.value_objects import TaskStatus
from src.infrastructure.research import KnowledgeBaseStore, ReportPackStore


class ValidateCitations:
    """Use case for validating citations in reports."""

    def __init__(
        self,
        kb_store: KnowledgeBaseStore,
        report_store: ReportPackStore,
        base_path: Path,
    ):
        self.kb_store = kb_store
        self.report_store = report_store
        self.base_path = base_path
        self._validator = CitationValidator()

    async def run(self, task: Task) -> bool:
        """Validate all citations in reports.

        Returns True if all citations are valid.
        """
        task.transition_to(TaskStatus.RESEARCH_CITATION_VALIDATE)

        # Load report files
        report_files = await self.report_store.list_report_files()
        file_contents = {}
        for filename in report_files:
            content = await self.report_store.load_report_file(filename)
            if content:
                file_contents[filename] = content

        # Load sources and build mappings
        sources = await self.kb_store.list_sources()
        source_key_map = {s.source_key: s.id for s in sources}
        sources_by_id = {s.id: s for s in sources}

        # Validate citations
        result = self._validator.validate_citations(
            report_files=file_contents,
            source_key_map=source_key_map,
            sources=sources_by_id,
            knowledge_base_path=self.kb_store.kb_path,
        )

        # Save evidence
        evidence_dir = self.base_path / "evidence" / "conditions" / "citations"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        evidence = {
            "checked_at": datetime.now(UTC).isoformat(),
            "citation_format": "[@key]",
            "checked_files": result.checked_files,
            "citations_found": result.citations_found,
            "citations_valid": result.citations_valid,
            "citations_invalid": result.citations_invalid,
            "validation_errors": result.validation_errors,
            "sources_checked": [
                {
                    "source_key": sc.source_key,
                    "has_raw": sc.has_raw,
                    "has_text": sc.has_text,
                    "raw_file_exists": sc.raw_file_exists,
                    "text_file_exists": sc.text_file_exists,
                    "http_status": sc.http_status,
                    "final_url": sc.final_url,
                }
                for sc in result.sources_checked
            ],
            "checks": {
                "all_citations_resolve": result.all_citations_resolve,
                "all_sources_have_url": result.all_sources_have_url,
                "all_sources_have_retrieved_at": result.all_sources_have_retrieved_at,
                "all_sources_have_content_hash": result.all_sources_have_content_hash,
                "all_sources_have_raw": result.all_sources_have_raw,
                "all_sources_have_text": result.all_sources_have_text,
                "all_raw_files_exist": result.all_raw_files_exist,
                "all_text_files_exist": result.all_text_files_exist,
                "all_http_status_ok": result.all_http_status_ok,
            },
            "passed": result.passed,
        }

        (evidence_dir / "citation_validation.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )

        return result.passed
