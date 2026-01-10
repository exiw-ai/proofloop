from uuid import UUID

from pydantic import BaseModel

from src.application.dto.task_output import ConditionOutput
from src.domain.value_objects.evidence_types import EvidenceRef
from src.domain.value_objects.task_status import TaskStatus


class FinalResult(BaseModel):
    task_id: UUID
    status: TaskStatus
    diff: str
    patch: str
    summary: str
    conditions: list[ConditionOutput]
    evidence_refs: list[EvidenceRef]
    blocked_reason: str | None = None
    stopped_reason: str | None = None
