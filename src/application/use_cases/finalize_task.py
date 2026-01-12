from loguru import logger

from src.application.dto.final_result import FinalResult
from src.application.dto.task_output import ConditionOutput
from src.domain.entities.task import Task
from src.domain.ports.diff_port import DiffPort, DiffResult
from src.domain.ports.task_repo_port import TaskRepoPort
from src.domain.value_objects.evidence_types import EvidenceRef
from src.domain.value_objects.task_status import TaskStatus


class FinalizeTask:
    """Use case for finalizing task and producing the final result."""

    def __init__(self, diff_port: DiffPort, task_repo: TaskRepoPort) -> None:
        self.diff_port = diff_port
        self.task_repo = task_repo

    async def execute(self, task: Task) -> FinalResult:
        """Finalize task and produce final result.

        Validates contract: Done only if all blocking conditions pass with evidence.
        """
        # Save incoming status BEFORE transitioning (for BLOCKED detection)
        incoming_status = task.status

        task.transition_to(TaskStatus.FINALIZE)
        await self.task_repo.save(task)

        # Get final diff
        cwd = task.sources[0] if task.sources else "."
        diff_result = await self.diff_port.get_worktree_diff(cwd)

        # Determine final status
        if task.can_mark_done():
            final_status = TaskStatus.DONE
            summary = self._build_done_summary(task, diff_result)
            blocked_reason = None
            stopped_reason = None
        elif incoming_status == TaskStatus.BLOCKED:
            final_status = TaskStatus.BLOCKED
            summary = "Task blocked - requires user action"
            blocked_reason = self._get_blocked_reason(task)
            stopped_reason = None
        else:
            final_status = TaskStatus.STOPPED
            summary = "Task stopped"
            blocked_reason = None
            stopped_reason = self._get_stopped_reason(task)

        # Collect condition outputs
        condition_outputs = [
            ConditionOutput(
                id=c.id,
                description=c.description,
                role=c.role.value,
                approval_status=c.approval_status,
                check_status=c.check_status,
                evidence_summary=(c.evidence_summary.output_tail if c.evidence_summary else None),
            )
            for c in task.conditions
        ]

        # Collect evidence refs
        evidence_refs: list[EvidenceRef] = [
            c.evidence_ref for c in task.conditions if c.evidence_ref is not None
        ]

        # Update task status and save
        task.transition_to(final_status)
        await self.task_repo.save(task)

        result = FinalResult(
            task_id=task.id,
            status=final_status,
            diff=diff_result.diff,
            patch=diff_result.patch,
            summary=summary,
            conditions=condition_outputs,
            evidence_refs=evidence_refs,
            blocked_reason=blocked_reason,
            stopped_reason=stopped_reason,
        )

        logger.info(f"Task {task.id} finalized with status {final_status.value}")

        return result

    def _build_done_summary(self, task: Task, diff_result: DiffResult) -> str:
        """Build a richer summary for completed tasks."""
        headline = task.plan.goal if task.plan else task.description
        lines = [f"Completed: {headline}."]

        files = diff_result.files_changed
        if files:
            preview = files[:5]
            suffix = f" (+{len(files) - 5} more)" if len(files) > 5 else ""
            lines.append(f"Updated files: {', '.join(preview)}{suffix}.")
        else:
            lines.append("No files changed.")

        if task.plan:
            lines.append(f"Plan steps executed: {len(task.plan.steps)}.")

        return "\n".join(lines)

    def _get_blocked_reason(self, task: Task) -> str:
        """Get reason for blocked status."""
        for c in task.get_blocking_conditions():
            if c.approval_status.value != "approved":
                return f"Condition '{c.description}' requires approval"
        return "User action required"

    def _get_stopped_reason(self, task: Task) -> str:
        """Get reason for stopped status."""
        if task.budget.is_exhausted():
            if task.budget.iteration_count >= task.budget.max_iterations:
                return f"Max iterations ({task.budget.max_iterations}) reached"
            if task.budget.stagnation_count >= task.budget.stagnation_limit:
                return f"Stagnation limit ({task.budget.stagnation_limit}) reached"
            if task.budget.elapsed_s >= task.budget.wall_time_limit_s:
                return f"Wall time limit ({task.budget.wall_time_limit_s}s) reached"
        return "Stopped by supervisor decision"
