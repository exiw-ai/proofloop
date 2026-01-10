from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.value_objects import CheckStatus, EvidenceRef


class IterationDecision(str, Enum):
    CONTINUE = "continue"
    DEEPEN_CONTEXT = "deepen_context"
    REPLAN = "replan"
    BLOCKED = "blocked"
    STOPPED = "stopped"
    DONE = "done"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Iteration(BaseModel):
    number: int
    goal: str
    changes: list[str] = []
    check_results: dict[UUID, CheckStatus] = {}
    decision: IterationDecision
    decision_reason: str
    timestamp: datetime = Field(default_factory=_utc_now)
    metrics: dict[str, float] = Field(default_factory=dict)
    artifacts: list[EvidenceRef] = Field(default_factory=list)
