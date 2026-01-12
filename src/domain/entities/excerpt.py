from uuid import UUID

from pydantic import BaseModel


class Excerpt(BaseModel):
    id: UUID
    source_id: UUID
    text: str
    location: str
    char_start: int | None = None
    char_end: int | None = None
