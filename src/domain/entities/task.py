from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.entities.budget import Budget
from src.domain.entities.condition import Condition
from src.domain.entities.iteration import Iteration
from src.domain.entities.plan import Plan
from src.domain.entities.research_inventory import ResearchInventory
from src.domain.entities.verification_inventory import VerificationInventory
from src.domain.value_objects import (
    ApprovalStatus,
    CheckStatus,
    ConditionRole,
    ContextRef,
    TaskStatus,
    TaskType,
)


class Task(BaseModel):
    id: UUID
    description: str
    goals: list[str]
    sources: list[str]
    constraints: list[str] = []

    task_type: TaskType = TaskType.CODE
    status: TaskStatus = TaskStatus.INTAKE
    verification_inventory: VerificationInventory | None = None
    research_inventory: ResearchInventory | None = None
    conditions: list[Condition] = []
    plan: Plan | None = None
    budget: Budget = Field(default_factory=Budget)
    iterations: list[Iteration] = []
    depends_on: list[UUID] = Field(default_factory=list)
    context_refs: list[ContextRef] = Field(default_factory=list)
    conditions_relaxed: bool = False

    def can_mark_done(self) -> bool:
        """Check if task can be marked as done.

        Per contract 1.1 and 1.2:
        Done iff for all (role=BLOCKING && approval_status=APPROVED):
        - check_status=PASS
        - evidence_ref exists
        """
        for condition in self.conditions:
            if condition.role == ConditionRole.BLOCKING:
                if condition.approval_status != ApprovalStatus.APPROVED:
                    return False
                # Contract 1.1: All blocking conditions must pass
                if condition.check_status != CheckStatus.PASS:
                    return False
                # Contract 1.2: Evidence mandatory for ALL approved blocking conditions
                if condition.evidence_ref is None:
                    return False
        return True

    def all_plan_steps_done(self) -> bool:
        """Check if all plan steps have been executed."""
        if not self.plan:
            return True
        return len(self.iterations) >= len(self.plan.steps)

    def get_blocking_conditions(self) -> list[Condition]:
        return [c for c in self.conditions if c.role == ConditionRole.BLOCKING]

    def add_condition(self, condition: Condition) -> None:
        self.conditions.append(condition)

    def add_iteration(self, iteration: Iteration) -> None:
        self.iterations.append(iteration)

    def transition_to(self, status: TaskStatus) -> None:
        self.status = status
