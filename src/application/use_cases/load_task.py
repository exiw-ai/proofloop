from uuid import UUID

from src.domain.entities.task import Task
from src.domain.ports.task_repo_port import TaskRepoPort


class LoadTask:
    def __init__(self, task_repo: TaskRepoPort):
        self.task_repo = task_repo

    async def execute(self, task_id: UUID) -> Task | None:
        """Load task for resume."""
        return await self.task_repo.load(task_id)
