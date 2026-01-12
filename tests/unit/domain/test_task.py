from datetime import UTC, datetime
from uuid import uuid4

from src.domain.entities.condition import Condition
from src.domain.entities.task import Task
from src.domain.value_objects.condition_enums import ApprovalStatus, CheckStatus, ConditionRole
from src.domain.value_objects.evidence_types import EvidenceRef, EvidenceSummary
from src.domain.value_objects.task_status import TaskStatus


def test_task_creation():
    task = Task(
        id=uuid4(),
        description="Add feature",
        goals=["Implement X"],
        sources=["."],
    )
    assert task.status == TaskStatus.INTAKE
    assert task.conditions == []
    assert task.plan is None


def test_can_mark_done_no_conditions():
    task = Task(
        id=uuid4(),
        description="Add feature",
        goals=[],
        sources=["."],
    )
    # No blocking conditions = can mark done
    assert task.can_mark_done() is True


def test_can_mark_done_with_passing_blocking_condition():
    task = Task(
        id=uuid4(),
        description="Add feature",
        goals=[],
        sources=["."],
    )

    cond = Condition(
        id=uuid4(),
        description="Tests pass",
        role=ConditionRole.BLOCKING,
        check_id=uuid4(),
        approval_status=ApprovalStatus.APPROVED,
        check_status=CheckStatus.PASS,
        evidence_ref=EvidenceRef(
            task_id=task.id,
            condition_id=uuid4(),
            check_id=uuid4(),
            artifact_path_rel="test.json",
            log_path_rel=None,
        ),
        evidence_summary=EvidenceSummary(
            command="pytest",
            cwd=".",
            exit_code=0,
            duration_ms=100,
            output_tail="ok",
            timestamp=datetime.now(UTC),
        ),
    )
    task.conditions.append(cond)

    assert task.can_mark_done() is True


def test_cannot_mark_done_with_failing_blocking_condition():
    task = Task(
        id=uuid4(),
        description="Add feature",
        goals=[],
        sources=["."],
    )

    cond = Condition(
        id=uuid4(),
        description="Tests pass",
        role=ConditionRole.BLOCKING,
        check_id=uuid4(),
        approval_status=ApprovalStatus.APPROVED,
        check_status=CheckStatus.FAIL,
    )
    task.conditions.append(cond)

    assert task.can_mark_done() is False


def test_cannot_mark_done_without_evidence():
    task = Task(
        id=uuid4(),
        description="Add feature",
        goals=[],
        sources=["."],
    )

    cond = Condition(
        id=uuid4(),
        description="Tests pass",
        role=ConditionRole.BLOCKING,
        check_id=uuid4(),
        approval_status=ApprovalStatus.APPROVED,
        check_status=CheckStatus.PASS,
        evidence_ref=None,  # No evidence!
    )
    task.conditions.append(cond)

    assert task.can_mark_done() is False
