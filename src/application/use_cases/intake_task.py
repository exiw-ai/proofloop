from uuid import UUID, uuid4

from loguru import logger

from src.application.dto.task_input import TaskInput
from src.domain.entities.budget import Budget
from src.domain.entities.task import Task
from src.domain.ports.task_repo_port import TaskRepoPort
from src.domain.value_objects.task_status import TaskStatus


class IntakeTask:
    def __init__(self, task_repo: TaskRepoPort) -> None:
        self.task_repo = task_repo

    async def execute(self, input: TaskInput, task_id: UUID | None = None) -> Task:
        """Create and persist a new Task from input.

        Sets status to INTAKE.
        """
        task = Task(
            id=task_id or uuid4(),
            description=input.description,
            goals=input.goals,
            sources=input.sources,
            constraints=input.constraints,
            workspace_path=input.workspace_path,
            status=TaskStatus.INTAKE,
            budget=Budget(
                wall_time_limit_s=input.timeout_minutes * 60,
                max_iterations=input.max_iterations,
            ),
        )

        await self.task_repo.save(task)
        logger.info("Task {} created with status {}", task.id, task.status)

        return task
