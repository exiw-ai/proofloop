from uuid import uuid4

from loguru import logger

from src.domain.entities.condition import Condition
from src.domain.entities.task import Task
from src.domain.ports.task_repo_port import TaskRepoPort
from src.domain.value_objects.condition_enums import ConditionRole
from src.domain.value_objects.task_status import TaskStatus


class DefineConditions:
    def __init__(self, task_repo: TaskRepoPort) -> None:
        self.task_repo = task_repo

    async def execute(
        self, task: Task, user_conditions: list[str] | None = None
    ) -> list[Condition]:
        """Define conditions (DoD) from verification inventory and user
        input."""
        if user_conditions is None:
            user_conditions = []

        conditions: list[Condition] = []

        if task.verification_inventory:
            for check in task.verification_inventory.checks:
                condition = Condition(
                    id=uuid4(),
                    description=f"{check.name} passes",
                    role=ConditionRole.BLOCKING,
                    check_id=check.id,
                )
                conditions.append(condition)

        for desc in user_conditions:
            condition = Condition(
                id=uuid4(),
                description=desc,
                role=ConditionRole.SIGNAL,
            )
            conditions.append(condition)

        task.conditions = conditions
        task.transition_to(TaskStatus.CONDITIONS)
        await self.task_repo.save(task)

        logger.info(
            "Conditions defined for task {}: {} blocking, {} signal",
            task.id,
            len([c for c in conditions if c.role == ConditionRole.BLOCKING]),
            len([c for c in conditions if c.role == ConditionRole.SIGNAL]),
        )

        return conditions
