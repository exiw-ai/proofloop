from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.value_objects import SourceLocator


class FetchMeta(BaseModel, frozen=True):
    http_status: int
    final_url: str
    mime_type: str
    size_bytes: int
    extract_method: str


class Source(BaseModel):
    id: UUID
    source_key: str
    title: str
    url: str
    canonical_url: str
    retrieved_at: datetime
    content_hash: str
    locator: SourceLocator = Field(default_factory=SourceLocator)
    source_type: str
    raw_path: str
    text_path: str
    fetch_meta: FetchMeta
