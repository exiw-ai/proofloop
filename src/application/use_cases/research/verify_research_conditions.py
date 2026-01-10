import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.domain.entities import Task
from src.domain.value_objects import (
    PRESET_PARAMS,
    TaskStatus,
)
from src.infrastructure.research import KnowledgeBaseStore, ReportPackStore


class VerifyResearchConditions:
    """Use case for verifying research conditions."""

    def __init__(
        self,
        kb_store: KnowledgeBaseStore,
        report_store: ReportPackStore,
        base_path: Path,
    ):
        self.kb_store = kb_store
        self.report_store = report_store
        self.base_path = base_path

    async def run(self, task: Task) -> dict[str, bool]:
        """Verify all research conditions.

        Returns dict of condition name to pass/fail.
        """
        task.transition_to(TaskStatus.RESEARCH_CONDITIONS)

        if not task.research_inventory:
            return {"error": False}

        preset_params = PRESET_PARAMS[task.research_inventory.preset]
        results: dict[str, bool] = {}

        evidence_dir = self.base_path / "evidence" / "conditions"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        # Check MIN_SOURCES
        sources = await self.kb_store.list_sources()
        min_sources_passed = len(sources) >= preset_params.min_sources

        sources_evidence = {
            "checked_at": datetime.now(UTC).isoformat(),
            "required_min": preset_params.min_sources,
            "actual_count": len(sources),
            "unique_count": len(sources),
            "duplicates_removed": 0,
            "by_type": self._count_by_type(sources),
            "passed": min_sources_passed,
        }

        (evidence_dir / "min_sources").mkdir(exist_ok=True)
        (evidence_dir / "min_sources" / "sources_count.json").write_text(
            json.dumps(sources_evidence, indent=2), encoding="utf-8"
        )
        results["MIN_SOURCES"] = min_sources_passed

        # Check COVERAGE_THRESHOLD
        findings = await self.kb_store.list_findings()
        coverage = self._calculate_coverage(findings, task.research_inventory.required_topics)
        coverage_passed = coverage >= preset_params.coverage

        coverage_evidence = {
            "checked_at": datetime.now(UTC).isoformat(),
            "required_threshold": preset_params.coverage,
            "actual_coverage": coverage,
            "required_topics": task.research_inventory.required_topics,
            "covered_topics": self._get_covered_topics(
                findings, task.research_inventory.required_topics
            ),
            "uncovered_topics": self._get_uncovered_topics(
                findings, task.research_inventory.required_topics
            ),
            "passed": coverage_passed,
        }

        (evidence_dir / "coverage").mkdir(exist_ok=True)
        (evidence_dir / "coverage" / "coverage_report.json").write_text(
            json.dumps(coverage_evidence, indent=2), encoding="utf-8"
        )
        results["COVERAGE_THRESHOLD"] = coverage_passed

        # Check SYNTHESIS_PASSES
        synthesis_log_path = self.base_path / "knowledge_base" / "synthesis" / "synthesis_log.json"
        synthesis_passed = False
        if synthesis_log_path.exists():
            synthesis_log = json.loads(synthesis_log_path.read_text(encoding="utf-8"))
            synthesis_passed = synthesis_log.get("passed", False)
        results["SYNTHESIS_PASSES"] = synthesis_passed

        # Check REPORT_ARTIFACTS_PRESENT
        manifest = await self.report_store.load_manifest()
        artifacts_passed = False
        if manifest:
            artifacts_passed = not manifest.get("missing_files", ["placeholder"])

        artifacts_evidence = {
            "checked_at": datetime.now(UTC).isoformat(),
            "required_files": manifest.get("required_files", []) if manifest else [],
            "present_files": manifest.get("present_files", []) if manifest else [],
            "missing_files": manifest.get("missing_files", []) if manifest else [],
            "manifest_path": "reports/manifest.json",
            "passed": artifacts_passed,
        }

        (evidence_dir / "report_artifacts").mkdir(exist_ok=True)
        (evidence_dir / "report_artifacts" / "report_artifacts_present.json").write_text(
            json.dumps(artifacts_evidence, indent=2), encoding="utf-8"
        )
        results["REPORT_ARTIFACTS_PRESENT"] = artifacts_passed

        # Check CITATIONS_VALID
        citations_path = evidence_dir / "citations" / "citation_validation.json"
        citations_passed = False
        if citations_path.exists():
            citations_data = json.loads(citations_path.read_text(encoding="utf-8"))
            citations_passed = citations_data.get("passed", False)
        results["CITATIONS_VALID"] = citations_passed

        return results

    def _count_by_type(self, sources: list[Any]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in sources:
            t = s.source_type
            counts[t] = counts.get(t, 0) + 1
        return counts

    def _calculate_coverage(self, findings: list[Any], required_topics: list[str]) -> float:
        if not required_topics:
            return 1.0

        covered = set()
        for finding in findings:
            for topic in finding.topics:
                topic_lower = topic.lower()
                for req in required_topics:
                    if req.lower() in topic_lower or topic_lower in req.lower():
                        covered.add(req.lower())

        return len(covered) / len(required_topics)

    def _get_covered_topics(self, findings: list[Any], required_topics: list[str]) -> list[str]:
        covered = set()
        for finding in findings:
            for topic in finding.topics:
                topic_lower = topic.lower()
                for req in required_topics:
                    if req.lower() in topic_lower or topic_lower in req.lower():
                        covered.add(req)
        return list(covered)

    def _get_uncovered_topics(self, findings: list[Any], required_topics: list[str]) -> list[str]:
        covered = set()
        for finding in findings:
            for topic in finding.topics:
                topic_lower = topic.lower()
                for req in required_topics:
                    if req.lower() in topic_lower or topic_lower in req.lower():
                        covered.add(req.lower())
        return [t for t in required_topics if t.lower() not in covered]
