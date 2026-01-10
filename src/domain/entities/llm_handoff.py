from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class KeyFinding(BaseModel, frozen=True):
    finding_id: UUID
    summary: str
    source_key: str
    excerpt_id: UUID


class SourceReference(BaseModel, frozen=True):
    source_key: str
    title: str
    url: str
    content_hash: str


class ContextRefPayload(BaseModel, frozen=True):
    kind: str
    rel_path: str


class LLMHandoff(BaseModel):
    schema_version: str = "1.0"
    research_task_id: UUID
    created_at: datetime
    headline: str
    goals: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    recommended_approach: str = ""
    key_findings: list[KeyFinding] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(default_factory=list)
    context_refs: list[ContextRefPayload] = Field(default_factory=list)
    suggested_blocking_conditions: list[str] = Field(default_factory=list)
    recommended_checks: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    target_workspace_hint: str | None = None
