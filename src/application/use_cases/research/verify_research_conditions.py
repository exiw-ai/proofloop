from datetime import UTC, datetime
from typing import Any

from src.domain.entities import Task
from src.domain.value_objects import (
    PRESET_PARAMS,
    TaskStatus,
)
from src.infrastructure.research import (
    KnowledgeBaseStore,
    ReportPackStore,
    VerificationEvidenceStore,
)


class VerifyResearchConditions:
    """Use case for verifying research conditions."""

    def __init__(
        self,
        kb_store: KnowledgeBaseStore,
        report_store: ReportPackStore,
        evidence_store: VerificationEvidenceStore,
    ):
        self.kb_store = kb_store
        self.report_store = report_store
        self.evidence_store = evidence_store

    async def run(self, task: Task) -> dict[str, bool]:
        """Verify all research conditions.

        Returns dict of condition name to pass/fail.
        """
        task.transition_to(TaskStatus.RESEARCH_CONDITIONS)

        if not task.research_inventory:
            return {"error": False}

        preset_params = PRESET_PARAMS[task.research_inventory.preset]
        results: dict[str, bool] = {}

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

        self.evidence_store.save_evidence("min_sources", "sources_count", sources_evidence)
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

        self.evidence_store.save_evidence("coverage", "coverage_report", coverage_evidence)
        results["COVERAGE_THRESHOLD"] = coverage_passed

        # Check SYNTHESIS_PASSES
        synthesis_log = self.kb_store.load_synthesis_log()
        synthesis_passed = False
        if synthesis_log:
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

        self.evidence_store.save_evidence(
            "report_artifacts", "report_artifacts_present", artifacts_evidence
        )
        results["REPORT_ARTIFACTS_PRESENT"] = artifacts_passed

        # Check CITATIONS_VALID
        citations_data = self.evidence_store.load_evidence("citations", "citation_validation")
        citations_passed = False
        if citations_data:
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
