from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.value_objects import ReportPackTemplate


class ReportPack(BaseModel):
    id: UUID
    task_id: UUID
    template: ReportPackTemplate
    created_at: datetime
    status: str = "pending"
    required_files: list[str] = Field(default_factory=list)
    present_files: list[str] = Field(default_factory=list)
    missing_files: list[str] = Field(default_factory=list)
    manifest_path: str | None = None
    manifest_hash: str | None = None
