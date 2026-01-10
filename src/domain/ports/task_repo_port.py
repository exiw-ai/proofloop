from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.domain.entities.condition import Condition
    from src.domain.entities.plan import Plan
    from src.domain.entities.task import Task
    from src.domain.entities.verification_inventory import VerificationInventory


class TaskRepoPort(ABC):
    """Port for task persistence (resume functionality)."""

    @abstractmethod
    async def save(self, task: "Task") -> None:
        """Save task snapshot for resume."""

    @abstractmethod
    async def load(self, task_id: UUID) -> "Task | None":
        """Load task by ID."""

    @abstractmethod
    async def list_tasks(self) -> list[UUID]:
        """List all task IDs."""

    @abstractmethod
    async def save_conditions_approval(
        self,
        task_id: UUID,
        conditions: list["Condition"],
    ) -> None:
        """Save conditions approval state."""

    @abstractmethod
    async def save_plan_approval(self, task_id: UUID, plan: "Plan") -> None:
        """Save plan approval state."""

    @abstractmethod
    async def save_inventory(
        self,
        task_id: UUID,
        inventory: "VerificationInventory",
    ) -> None:
        """Save verification inventory."""
