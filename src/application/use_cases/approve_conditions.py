from loguru import logger

from src.domain.entities.task import Task
from src.domain.ports.task_repo_port import TaskRepoPort
from src.domain.value_objects.task_status import TaskStatus


class ApproveConditions:
    def __init__(self, task_repo: TaskRepoPort):
        self.task_repo = task_repo

    async def execute(self, task: Task, auto_approve: bool = False) -> bool:
        """Approve conditions.

        If no conditions exist, returns True (nothing to approve). If
        auto_approve=True, approves all conditions. Otherwise, returns
        False (requires user action -> Blocked).
        """
        # No conditions = nothing to approve, proceed
        if not task.conditions:
            logger.info("No conditions to approve, proceeding")
            task.transition_to(TaskStatus.APPROVAL_CONDITIONS)
            await self.task_repo.save(task)
            return True

        if auto_approve:
            for condition in task.conditions:
                try:
                    condition.approve()
                    logger.info(f"Auto-approved condition: {condition.description}")
                except ValueError as e:
                    logger.warning(f"Cannot approve condition {condition.id}: {e}")

            task.transition_to(TaskStatus.APPROVAL_CONDITIONS)
            await self.task_repo.save_conditions_approval(task.id, task.conditions)
            await self.task_repo.save(task)
            return True

        # Has conditions but no auto_approve - need user action
        return False
