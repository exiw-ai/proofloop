from pydantic import BaseModel


class SourceLocator(BaseModel, frozen=True):
    """Unique identifiers for deduplicating sources."""

    doi: str | None = None
    arxiv_id: str | None = None
    github_sha: str | None = None
