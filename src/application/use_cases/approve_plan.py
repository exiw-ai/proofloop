from loguru import logger

from src.domain.entities.task import Task
from src.domain.ports.task_repo_port import TaskRepoPort
from src.domain.value_objects.task_status import TaskStatus


class ApprovePlan:
    def __init__(self, task_repo: TaskRepoPort):
        self.task_repo = task_repo

    async def execute(self, task: Task, auto_approve: bool = False) -> bool:
        """Approve plan.

        If auto_approve=True, approves current plan version. Otherwise,
        returns False (requires user action -> Blocked).
        """
        if auto_approve:
            if task.plan:
                task.plan.approve()
                logger.info(f"Auto-approved plan v{task.plan.version}: {task.plan.goal}")
                task.transition_to(TaskStatus.APPROVAL_PLAN)
                await self.task_repo.save_plan_approval(task.id, task.plan)
                await self.task_repo.save(task)
                return True
            logger.warning("No plan to approve")
            return False

        return False
