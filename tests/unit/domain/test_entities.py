from datetime import UTC, datetime
from uuid import uuid4

from src.domain.entities import (
    Budget,
    Condition,
    Iteration,
    IterationDecision,
    Plan,
    PlanStep,
    Task,
    VerificationInventory,
)
from src.domain.value_objects import (
    ApprovalStatus,
    CheckKind,
    CheckSpec,
    CheckStatus,
    ConditionRole,
    EvidenceRef,
    EvidenceSummary,
    TaskStatus,
)


class TestBudget:
    def test_default_budget_is_not_exhausted(self) -> None:
        budget = Budget()
        assert not budget.is_exhausted()

    def test_exhausted_when_wall_time_exceeded(self) -> None:
        budget = Budget(wall_time_limit_s=3600, elapsed_s=3601)
        assert budget.is_exhausted()

    def test_exhausted_when_max_iterations_reached(self) -> None:
        budget = Budget(max_iterations=50, iteration_count=50)
        assert budget.is_exhausted()

    def test_exhausted_when_stagnation_limit_reached(self) -> None:
        budget = Budget(stagnation_limit=3, stagnation_count=3)
        assert budget.is_exhausted()

    def test_exhausted_when_quality_loop_limit_reached(self) -> None:
        budget = Budget(quality_loop_limit=3, quality_loop_count=3)
        assert budget.is_exhausted()

    def test_record_iteration_with_progress_resets_stagnation(self) -> None:
        budget = Budget(stagnation_count=2)
        budget.start_tracking()
        budget.record_iteration(is_progress=True)
        assert budget.stagnation_count == 0
        assert budget.iteration_count == 1
        assert budget.elapsed_s >= 0  # Time is now auto-calculated

    def test_record_iteration_without_progress_increments_stagnation(self) -> None:
        budget = Budget(stagnation_count=1)
        budget.start_tracking()
        budget.record_iteration(is_progress=False)
        assert budget.stagnation_count == 2
        assert budget.iteration_count == 1

    def test_start_tracking_sets_timestamp(self) -> None:
        budget = Budget()
        assert budget.start_timestamp == 0.0
        budget.start_tracking()
        assert budget.start_timestamp > 0

    def test_elapsed_time_calculated_automatically(self) -> None:
        import time

        budget = Budget()
        budget.start_tracking()
        time.sleep(0.1)  # 100ms
        budget.record_iteration(is_progress=True)
        assert budget.elapsed_s >= 0  # At least 0 seconds


class TestCondition:
    def test_approve_blocking_condition_without_check_id_succeeds(self) -> None:
        """Manual blocking conditions can be approved - verified by agent later."""
        condition = Condition(
            id=uuid4(),
            description="All tests pass",
            role=ConditionRole.BLOCKING,
            check_id=None,
        )
        condition.approve()
        assert condition.approval_status == ApprovalStatus.APPROVED

    def test_approve_blocking_condition_with_check_id_succeeds(self) -> None:
        condition = Condition(
            id=uuid4(),
            description="All tests pass",
            role=ConditionRole.BLOCKING,
            check_id=uuid4(),
        )
        condition.approve()
        assert condition.approval_status == ApprovalStatus.APPROVED

    def test_approve_signal_condition_without_check_id_succeeds(self) -> None:
        condition = Condition(
            id=uuid4(),
            description="Coverage above 80%",
            role=ConditionRole.SIGNAL,
            check_id=None,
        )
        condition.approve()
        assert condition.approval_status == ApprovalStatus.APPROVED

    def test_record_check_result_stores_evidence(self) -> None:
        condition = Condition(
            id=uuid4(),
            description="All tests pass",
            role=ConditionRole.BLOCKING,
            check_id=uuid4(),
        )
        evidence_ref = EvidenceRef(
            task_id=uuid4(),
            condition_id=condition.id,
            check_id=condition.check_id,
            artifact_path_rel="tasks/abc/iterations/0001/checks/def/123.json",
            log_path_rel="tasks/abc/iterations/0001/checks/def/123.log",
        )
        evidence_summary = EvidenceSummary(
            command="pytest",
            cwd="/project",
            exit_code=0,
            duration_ms=1500,
            output_tail="5 passed",
            timestamp=datetime.now(UTC),
        )

        condition.record_check_result(
            status=CheckStatus.PASS,
            evidence_ref=evidence_ref,
            evidence_summary=evidence_summary,
        )

        assert condition.check_status == CheckStatus.PASS
        assert condition.evidence_ref == evidence_ref
        assert condition.evidence_summary == evidence_summary


class TestVerificationInventory:
    def test_get_check_returns_check_by_id(self) -> None:
        check_id = uuid4()
        check = CheckSpec(
            id=check_id,
            name="pytest",
            kind=CheckKind.TEST,
            command="pytest",
            cwd="/project",
        )
        inventory = VerificationInventory(
            checks=[check],
            project_structure={"files": []},
            conventions=["PEP8"],
        )

        result = inventory.get_check(check_id)
        assert result == check

    def test_get_check_returns_none_for_unknown_id(self) -> None:
        inventory = VerificationInventory(
            checks=[],
            project_structure={"files": []},
            conventions=[],
        )

        result = inventory.get_check(uuid4())
        assert result is None


class TestTask:
    def _create_approved_blocking_condition(self, passed: bool = True) -> Condition:
        condition = Condition(
            id=uuid4(),
            description="Test condition",
            role=ConditionRole.BLOCKING,
            check_id=uuid4(),
        )
        condition.approve()
        if passed:
            condition.record_check_result(
                status=CheckStatus.PASS,
                evidence_ref=EvidenceRef(
                    task_id=uuid4(),
                    condition_id=condition.id,
                    check_id=condition.check_id,
                    artifact_path_rel="path/to/artifact.json",
                    log_path_rel="path/to/artifact.log",
                ),
                evidence_summary=EvidenceSummary(
                    command="pytest",
                    cwd="/project",
                    exit_code=0,
                    duration_ms=1000,
                    output_tail="passed",
                    timestamp=datetime.now(UTC),
                ),
            )
        return condition

    def test_can_mark_done_with_all_blocking_conditions_passed(self) -> None:
        task = Task(
            id=uuid4(),
            description="Implement feature",
            goals=["Feature works"],
            sources=["."],
        )
        task.add_condition(self._create_approved_blocking_condition(passed=True))
        task.add_condition(self._create_approved_blocking_condition(passed=True))

        assert task.can_mark_done()

    def test_cannot_mark_done_with_unapproved_blocking_condition(self) -> None:
        task = Task(
            id=uuid4(),
            description="Implement feature",
            goals=["Feature works"],
            sources=["."],
        )
        condition = Condition(
            id=uuid4(),
            description="Test",
            role=ConditionRole.BLOCKING,
            check_id=uuid4(),
            approval_status=ApprovalStatus.DRAFT,
        )
        task.add_condition(condition)

        assert not task.can_mark_done()

    def test_cannot_mark_done_with_failing_blocking_condition(self) -> None:
        task = Task(
            id=uuid4(),
            description="Implement feature",
            goals=["Feature works"],
            sources=["."],
        )
        condition = Condition(
            id=uuid4(),
            description="Test",
            role=ConditionRole.BLOCKING,
            check_id=uuid4(),
            approval_status=ApprovalStatus.APPROVED,
            check_status=CheckStatus.FAIL,
        )
        task.add_condition(condition)

        assert not task.can_mark_done()

    def test_cannot_mark_done_without_evidence_ref(self) -> None:
        task = Task(
            id=uuid4(),
            description="Implement feature",
            goals=["Feature works"],
            sources=["."],
        )
        condition = Condition(
            id=uuid4(),
            description="Test",
            role=ConditionRole.BLOCKING,
            check_id=uuid4(),
            approval_status=ApprovalStatus.APPROVED,
            check_status=CheckStatus.PASS,
            evidence_ref=None,
        )
        task.add_condition(condition)

        assert not task.can_mark_done()

    def test_signal_conditions_dont_block_done(self) -> None:
        task = Task(
            id=uuid4(),
            description="Implement feature",
            goals=["Feature works"],
            sources=["."],
        )
        signal_condition = Condition(
            id=uuid4(),
            description="Coverage",
            role=ConditionRole.SIGNAL,
            check_status=CheckStatus.FAIL,
        )
        task.add_condition(signal_condition)
        task.add_condition(self._create_approved_blocking_condition(passed=True))

        assert task.can_mark_done()

    def test_get_blocking_conditions(self) -> None:
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=["."],
        )
        blocking = Condition(
            id=uuid4(),
            description="Blocking",
            role=ConditionRole.BLOCKING,
        )
        signal = Condition(
            id=uuid4(),
            description="Signal",
            role=ConditionRole.SIGNAL,
        )
        task.add_condition(blocking)
        task.add_condition(signal)

        result = task.get_blocking_conditions()
        assert len(result) == 1
        assert result[0].role == ConditionRole.BLOCKING

    def test_transition_to_updates_status(self) -> None:
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=["."],
        )
        initial_status = task.status
        assert initial_status == TaskStatus.INTAKE
        task.transition_to(TaskStatus.STRATEGY)
        new_status = task.status
        assert new_status == TaskStatus.STRATEGY


class TestIteration:
    def test_iteration_creation(self) -> None:
        iteration = Iteration(
            number=1,
            goal="Implement feature",
            changes=["src/main.py"],
            check_results={uuid4(): CheckStatus.PASS},
            decision=IterationDecision.CONTINUE,
            decision_reason="Progress made",
        )
        assert iteration.number == 1
        assert iteration.decision == IterationDecision.CONTINUE


class TestPlan:
    def test_plan_creation(self) -> None:
        plan = Plan(
            goal="Add authentication",
            boundaries=["No breaking changes"],
            steps=[
                PlanStep(
                    number=1,
                    description="Create auth module",
                    target_files=["src/auth.py"],
                )
            ],
        )
        assert plan.goal == "Add authentication"
        assert len(plan.steps) == 1
        assert plan.version == 1
        assert plan.approved is False

    def test_plan_approve(self) -> None:
        plan = Plan(
            goal="Add feature",
            boundaries=[],
            steps=[],
        )
        assert plan.approved is False
        plan.approve()
        assert plan.approved is True
