from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.value_objects import ResearchPreset, ResearchType


class ResearchInventory(BaseModel):
    id: UUID
    task_id: UUID
    queries: list[str] = Field(default_factory=list)
    required_topics: list[str] = Field(default_factory=list)
    topic_synonyms: dict[str, list[str]] = Field(default_factory=dict)
    sections: list[str] = Field(default_factory=list)
    research_type: ResearchType
    preset: ResearchPreset
    created_at: datetime
