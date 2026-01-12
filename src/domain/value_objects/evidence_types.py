from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class EvidenceSummary(BaseModel, frozen=True):
    command: str
    cwd: str
    exit_code: int
    duration_ms: int
    output_tail: str
    timestamp: datetime


class EvidenceRef(BaseModel, frozen=True):
    task_id: UUID
    condition_id: UUID
    check_id: UUID | None
    artifact_path_rel: str
    log_path_rel: str | None
