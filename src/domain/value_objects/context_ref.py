from uuid import UUID

from pydantic import BaseModel

from src.domain.value_objects.artifact_kind import ArtifactKind


class ContextRef(BaseModel, frozen=True):
    task_id: UUID
    kind: ArtifactKind
    rel_path: str
