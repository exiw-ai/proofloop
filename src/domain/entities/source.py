from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


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
    locator: dict[str, Any] = {}
    source_type: str
    raw_path: str
    text_path: str
    fetch_meta: FetchMeta
