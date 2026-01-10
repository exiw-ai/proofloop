from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.value_objects import (
    ApprovalStatus,
    CheckStatus,
    ConditionRole,
    EvidenceRef,
    EvidenceSummary,
)


class Condition(BaseModel):
    id: UUID
    description: str
    role: ConditionRole
    approval_status: ApprovalStatus = ApprovalStatus.DRAFT
    check_id: UUID | None = None
    check_status: CheckStatus = CheckStatus.NOT_RUN
    evidence_ref: EvidenceRef | None = None
    evidence_summary: EvidenceSummary | None = None
    params: dict[str, Any] = Field(default_factory=dict)

    def approve(self) -> None:
        """Transition approval_status DRAFT/PROPOSED -> APPROVED.

        Manual blocking conditions (no check_id) are allowed - they will be
        verified by the agent during delivery.
        """
        self.approval_status = ApprovalStatus.APPROVED

    def record_check_result(
        self,
        status: CheckStatus,
        evidence_ref: EvidenceRef,
        evidence_summary: EvidenceSummary,
    ) -> None:
        """Record check result with evidence.

        Before first run: evidence_ref/evidence_summary are None in Condition.
        After any run: always non-null (both PASS and FAIL for debugging).

        Args are non-null: caller is responsible for creating evidence.
        """
        self.check_status = status
        self.evidence_ref = evidence_ref
        self.evidence_summary = evidence_summary
