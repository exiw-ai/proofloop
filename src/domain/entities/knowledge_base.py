from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class KnowledgeBase(BaseModel):
    id: UUID
    task_id: UUID
    sources: list[UUID] = Field(default_factory=list)
    findings: list[UUID] = Field(default_factory=list)
    excerpts: list[UUID] = Field(default_factory=list)
    source_key_map: dict[str, UUID] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
