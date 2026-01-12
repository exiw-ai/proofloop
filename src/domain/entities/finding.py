from uuid import UUID

from pydantic import BaseModel, Field


class Finding(BaseModel):
    id: UUID
    source_id: UUID
    source_key: str
    excerpt_ref: str
    content: str
    finding_type: str
    confidence: float = Field(ge=0.0, le=1.0)
    topics: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
