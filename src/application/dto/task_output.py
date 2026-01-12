from uuid import UUID

from pydantic import BaseModel

from src.domain.value_objects.condition_enums import ApprovalStatus, CheckStatus
from src.domain.value_objects.task_status import TaskStatus


class ConditionOutput(BaseModel):
    id: UUID
    description: str
    role: str
    approval_status: ApprovalStatus
    check_status: CheckStatus
    evidence_summary: str | None = None


class TaskOutput(BaseModel):
    task_id: UUID
    status: TaskStatus
    current_stage: str
    iteration_count: int
    conditions: list[ConditionOutput]
    plan_summary: str | None = None
