from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.value_objects import TaskStatus


class ResearchResult(BaseModel):
    task_id: UUID
    status: TaskStatus
    report_pack_path: str
    handoff_payload_path: str
    metrics: dict[str, float] = Field(default_factory=dict)
    iterations_count: int
    conditions_met: list[str] = Field(default_factory=list)
    conditions_failed: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    error: str | None = None
