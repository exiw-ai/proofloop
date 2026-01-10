from pathlib import Path
from typing import Any

from src.domain.entities import ResearchResult, Task
from src.domain.value_objects import TaskStatus
from src.infrastructure.research import KnowledgeBaseStore, ReportPackStore


class FinalizeResearch:
    """Use case for finalizing research task."""

    def __init__(
        self,
        kb_store: KnowledgeBaseStore,
        report_store: ReportPackStore,
        base_path: Path,
    ):
        self.kb_store = kb_store
        self.report_store = report_store
        self.base_path = base_path

    async def run(
        self,
        task: Task,
        conditions_results: dict[str, bool],
    ) -> ResearchResult:
        """Finalize research and produce ResearchResult."""
        all_passed = all(conditions_results.values())

        if all_passed:
            task.transition_to(TaskStatus.RESEARCH_FINALIZED)
            status = TaskStatus.RESEARCH_FINALIZED
        else:
            task.transition_to(TaskStatus.RESEARCH_FAILED)
            status = TaskStatus.RESEARCH_FAILED

        # Gather metrics
        sources = await self.kb_store.list_sources()
        findings = await self.kb_store.list_findings()

        metrics = {
            "sources_count": float(len(sources)),
            "findings_count": float(len(findings)),
            "coverage": self._calculate_coverage(
                findings,
                task.research_inventory.required_topics if task.research_inventory else [],
            ),
        }

        # Determine next actions
        next_actions = []
        if all_passed:
            next_actions.append("Run 'proofloop task derive-code <task_id>' to create CODE task")
            next_actions.append("Review reports in .proofloop/research/reports/")
        else:
            failed = [k for k, v in conditions_results.items() if not v]
            if "MIN_SOURCES" in failed:
                next_actions.append("Find more sources to meet minimum requirement")
            if "COVERAGE_THRESHOLD" in failed:
                next_actions.append("Improve coverage of required topics")
            if "CITATIONS_VALID" in failed:
                next_actions.append("Fix invalid citations in reports")

        return ResearchResult(
            task_id=task.id,
            status=status,
            report_pack_path="reports/",
            handoff_payload_path="derive_payload.json",
            metrics=metrics,
            iterations_count=len(task.iterations),
            conditions_met=[k for k, v in conditions_results.items() if v],
            conditions_failed=[k for k, v in conditions_results.items() if not v],
            next_actions=next_actions,
            error=None if all_passed else "Some conditions failed",
        )

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
