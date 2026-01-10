from datetime import UTC, datetime
from uuid import uuid4

from src.domain.entities.condition import Condition
from src.domain.value_objects.condition_enums import ApprovalStatus, CheckStatus, ConditionRole
from src.domain.value_objects.evidence_types import EvidenceRef, EvidenceSummary


def test_condition_creation():
    cond = Condition(
        id=uuid4(),
        description="All tests pass",
        role=ConditionRole.BLOCKING,
    )
    assert cond.approval_status == ApprovalStatus.DRAFT
    assert cond.check_status == CheckStatus.NOT_RUN
    assert cond.check_id is None


def test_blocking_condition_can_approve_without_check_id():
    """Manual blocking conditions can be approved - they'll be verified by agent."""
    cond = Condition(
        id=uuid4(),
        description="All tests pass",
        role=ConditionRole.BLOCKING,
        check_id=None,
    )
    cond.approve()
    assert cond.approval_status == ApprovalStatus.APPROVED


def test_blocking_condition_can_approve_with_check_id():
    cond = Condition(
        id=uuid4(),
        description="All tests pass",
        role=ConditionRole.BLOCKING,
        check_id=uuid4(),
    )
    cond.approve()
    assert cond.approval_status == ApprovalStatus.APPROVED


def test_signal_condition_can_approve_without_check_id():
    cond = Condition(
        id=uuid4(),
        description="Code is clean",
        role=ConditionRole.SIGNAL,
    )
    cond.approve()
    assert cond.approval_status == ApprovalStatus.APPROVED


def test_record_check_result():
    cond = Condition(
        id=uuid4(),
        description="Tests pass",
        role=ConditionRole.BLOCKING,
        check_id=uuid4(),
    )

    evidence_ref = EvidenceRef(
        task_id=uuid4(),
        condition_id=cond.id,
        check_id=cond.check_id,
        artifact_path_rel="checks/test.json",
        log_path_rel="checks/test.log",
    )
    evidence_summary = EvidenceSummary(
        command="pytest",
        cwd="/project",
        exit_code=0,
        duration_ms=1000,
        output_tail="All tests passed",
        timestamp=datetime.now(UTC),
    )

    cond.record_check_result(CheckStatus.PASS, evidence_ref, evidence_summary)

    assert cond.check_status == CheckStatus.PASS
    assert cond.evidence_ref == evidence_ref
    assert cond.evidence_summary == evidence_summary
