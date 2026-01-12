"""Comprehensive tests for Supervisor service."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.application.services.supervisor import Supervisor
from src.domain.entities.budget import Budget
from src.domain.entities.condition import Condition
from src.domain.entities.iteration import Iteration, IterationDecision
from src.domain.entities.plan import Plan, PlanStep
from src.domain.entities.task import Task
from src.domain.value_objects.condition_enums import CheckStatus, ConditionRole
from src.domain.value_objects.supervision_enums import (
    AnomalyType,
    RetryStrategy,
    SupervisionDecision,
)


@pytest.fixture
def supervisor():
    return Supervisor(
        stagnation_limit=3,
        loop_limit=5,
        flaky_retry_limit=2,
        rollback_limit=2,
    )


@pytest.fixture
def task(tmp_path):
    task = Task(
        id=uuid4(),
        description="Test task",
        goals=["Goal"],
        sources=[str(tmp_path)],
        budget=Budget(max_iterations=10, stagnation_limit=3),
    )
    task.plan = Plan(
        goal="Test",
        boundaries=[],
        steps=[PlanStep(number=1, description="Step 1")],
    )
    task.plan.approve()
    return task


def make_iteration(
    number: int,
    changes: list[str] | None = None,
    check_results: dict | None = None,
) -> Iteration:
    """Helper to create iterations."""
    return Iteration(
        number=number,
        goal=f"Iteration {number}",
        changes=changes or [],
        check_results=check_results or {},
        decision=IterationDecision.CONTINUE,
        decision_reason="Continue",
        timestamp=datetime.now(UTC),
    )


def add_conditions_to_task(task: Task, check_results: dict) -> None:
    """Add conditions to task matching check_results."""
    for check_id, status in check_results.items():
        condition = Condition(
            id=check_id,
            description=f"Test condition {check_id}",
            role=ConditionRole.BLOCKING,
        )
        condition.check_status = status
        task.conditions.append(condition)


class TestSupervisorAnalyze:
    def test_analyze_returns_continue_on_progress(self, supervisor, task):
        """Analyze should return CONTINUE when progress is made."""
        iteration = make_iteration(1, changes=["file.py"])
        task.iterations.append(iteration)

        result = supervisor.analyze(task, iteration)

        assert result.decision == SupervisionDecision.CONTINUE
        assert result.anomaly is None

    def test_analyze_detects_budget_risk(self, supervisor, task):
        """Analyze should detect budget risk at 80%."""
        task.budget = Budget(max_iterations=10, iteration_count=8)
        iteration = make_iteration(9, changes=["file.py"])
        task.iterations.append(iteration)

        result = supervisor.analyze(task, iteration)

        assert result.decision == SupervisionDecision.STOP
        assert result.anomaly == AnomalyType.CONTRACT_RISK


class TestSupervisorCheckStagnation:
    def test_detects_stagnation_after_limit(self, supervisor, task):
        """_check_stagnation should detect stagnation after limit."""
        # Add stagnant iterations (no changes)
        for i in range(3):
            task.iterations.append(make_iteration(i + 1, changes=[]))

        result = supervisor._check_stagnation(task.iterations)

        assert result is not None
        assert result.decision == SupervisionDecision.REPLAN
        assert result.anomaly == AnomalyType.STAGNATION

    def test_suggests_deepen_context_at_2_stagnant(self, supervisor, task):
        """_check_stagnation should suggest DEEPEN_CONTEXT at 2 stagnant
        iterations."""
        task.iterations.append(make_iteration(1, changes=[]))
        task.iterations.append(make_iteration(2, changes=[]))

        result = supervisor._check_stagnation(task.iterations)

        assert result is not None
        assert result.decision == SupervisionDecision.DEEPEN_CONTEXT

    def test_no_stagnation_with_changes(self, supervisor, task):
        """_check_stagnation should not detect stagnation when changes made."""
        task.iterations.append(make_iteration(1, changes=["file.py"]))
        task.iterations.append(make_iteration(2, changes=["test.py"]))

        result = supervisor._check_stagnation(task.iterations)

        assert result is None

    def test_no_stagnation_with_single_iteration(self, supervisor, task):
        """_check_stagnation should not detect stagnation with single
        iteration."""
        task.iterations.append(make_iteration(1, changes=[]))

        result = supervisor._check_stagnation(task.iterations)

        assert result is None


class TestSupervisorCheckLoop:
    def test_detects_loop_at_limit(self, supervisor, task):
        """_check_loop should detect loop when same error repeated at limit."""
        check_id = uuid4()
        check_results = {check_id: CheckStatus.FAIL}
        add_conditions_to_task(task, check_results)
        iteration = make_iteration(1, check_results=check_results)

        # Simulate running analyze multiple times with same error
        for _ in range(5):
            supervisor._check_loop(task, iteration)

        result = supervisor._check_loop(task, iteration)

        assert result is not None
        assert result.decision == SupervisionDecision.STOP
        assert result.anomaly == AnomalyType.LOOP_DETECTED

    def test_suggests_replan_at_3_repeats(self, supervisor, task):
        """_check_loop should suggest REPLAN at 3 repeats."""
        check_id = uuid4()
        check_results = {check_id: CheckStatus.FAIL}
        add_conditions_to_task(task, check_results)
        iteration = make_iteration(1, check_results=check_results)

        # Simulate 3 occurrences
        for _ in range(3):
            supervisor._check_loop(task, iteration)

        result = supervisor._check_loop(task, iteration)

        assert result is not None
        assert result.decision == SupervisionDecision.REPLAN

    def test_no_loop_with_passing_checks(self, supervisor, task):
        """_check_loop should not detect loop with passing checks."""
        check_id = uuid4()
        check_results = {check_id: CheckStatus.PASS}
        add_conditions_to_task(task, check_results)
        iteration = make_iteration(1, check_results=check_results)

        result = supervisor._check_loop(task, iteration)

        assert result is None


class TestSupervisorCheckRegression:
    def test_detects_regression(self, supervisor, task):
        """_check_regression should detect regression from PASS to FAIL."""
        check_id = uuid4()
        task.iterations.append(make_iteration(1, check_results={check_id: CheckStatus.PASS}))
        task.iterations.append(make_iteration(2, check_results={check_id: CheckStatus.FAIL}))

        result = supervisor._check_regression(task.iterations)

        assert result is not None
        assert result.decision == SupervisionDecision.REPLAN
        assert result.anomaly == AnomalyType.REGRESSION

    def test_no_regression_with_consistent_pass(self, supervisor, task):
        """_check_regression should not detect regression with consistent
        passes."""
        check_id = uuid4()
        task.iterations.append(make_iteration(1, check_results={check_id: CheckStatus.PASS}))
        task.iterations.append(make_iteration(2, check_results={check_id: CheckStatus.PASS}))

        result = supervisor._check_regression(task.iterations)

        assert result is None

    def test_no_regression_with_single_iteration(self, supervisor, task):
        """_check_regression should not detect regression with single
        iteration."""
        check_id = uuid4()
        task.iterations.append(make_iteration(1, check_results={check_id: CheckStatus.FAIL}))

        result = supervisor._check_regression(task.iterations)

        assert result is None


class TestSupervisorCheckFlaky:
    def test_detects_flaky_pass_fail_pass(self, supervisor, task):
        """_check_flaky should detect PASS-FAIL-PASS pattern."""
        check_id = uuid4()
        task.iterations.append(make_iteration(1, check_results={check_id: CheckStatus.PASS}))
        task.iterations.append(make_iteration(2, check_results={check_id: CheckStatus.FAIL}))
        task.iterations.append(make_iteration(3, check_results={check_id: CheckStatus.PASS}))

        result = supervisor._check_flaky(task.iterations)

        assert result is not None
        assert result.decision == SupervisionDecision.BLOCK
        assert result.anomaly == AnomalyType.FLAKY_CHECK

    def test_detects_flaky_fail_pass_fail(self, supervisor, task):
        """_check_flaky should detect FAIL-PASS-FAIL pattern."""
        check_id = uuid4()
        task.iterations.append(make_iteration(1, check_results={check_id: CheckStatus.FAIL}))
        task.iterations.append(make_iteration(2, check_results={check_id: CheckStatus.PASS}))
        task.iterations.append(make_iteration(3, check_results={check_id: CheckStatus.FAIL}))

        result = supervisor._check_flaky(task.iterations)

        assert result is not None
        assert result.decision == SupervisionDecision.BLOCK
        assert result.anomaly == AnomalyType.FLAKY_CHECK

    def test_no_flaky_with_consistent_results(self, supervisor, task):
        """_check_flaky should not detect flaky with consistent results."""
        check_id = uuid4()
        task.iterations.append(make_iteration(1, check_results={check_id: CheckStatus.FAIL}))
        task.iterations.append(make_iteration(2, check_results={check_id: CheckStatus.FAIL}))
        task.iterations.append(make_iteration(3, check_results={check_id: CheckStatus.FAIL}))

        result = supervisor._check_flaky(task.iterations)

        assert result is None

    def test_no_flaky_with_less_than_3_iterations(self, supervisor, task):
        """_check_flaky should not detect flaky with < 3 iterations."""
        check_id = uuid4()
        task.iterations.append(make_iteration(1, check_results={check_id: CheckStatus.PASS}))
        task.iterations.append(make_iteration(2, check_results={check_id: CheckStatus.FAIL}))

        result = supervisor._check_flaky(task.iterations)

        assert result is None


class TestSupervisorDecideRetryStrategy:
    def test_stop_on_same_error_at_limit(self, supervisor, task):
        """decide_retry_strategy should STOP at loop limit."""
        check_id = uuid4()
        check_results = {check_id: CheckStatus.FAIL}
        add_conditions_to_task(task, check_results)
        iteration = make_iteration(1, check_results=check_results)

        # Fill error history to limit
        for _ in range(5):
            supervisor._check_loop(task, iteration)

        strategy, reason = supervisor.decide_retry_strategy(task, iteration)

        assert strategy == RetryStrategy.STOP
        assert "stopping" in reason.lower()

    def test_rollback_on_repeated_error(self, supervisor, task):
        """decide_retry_strategy should ROLLBACK_AND_RETRY on repeated
        error."""
        check_id = uuid4()
        check_results = {check_id: CheckStatus.FAIL}
        add_conditions_to_task(task, check_results)
        iteration = make_iteration(1, check_results=check_results)

        # Add to error history
        for _ in range(2):
            supervisor._check_loop(task, iteration)

        strategy, reason = supervisor.decide_retry_strategy(task, iteration)

        assert strategy == RetryStrategy.ROLLBACK_AND_RETRY
        assert "fresh" in reason.lower()

    def test_stop_on_no_changes(self, supervisor, task):
        """decide_retry_strategy should STOP when no changes made."""
        iteration = make_iteration(1, changes=[])  # No changes

        strategy, reason = supervisor.decide_retry_strategy(task, iteration)

        assert strategy == RetryStrategy.STOP
        assert "no changes" in reason.lower()

    def test_continue_with_context_otherwise(self, supervisor, task):
        """decide_retry_strategy should CONTINUE_WITH_CONTEXT by default."""
        check_id = uuid4()
        check_results = {check_id: CheckStatus.FAIL}
        add_conditions_to_task(task, check_results)
        iteration = make_iteration(1, changes=["file.py"], check_results=check_results)

        strategy, reason = supervisor.decide_retry_strategy(task, iteration)

        assert strategy == RetryStrategy.CONTINUE_WITH_CONTEXT
        assert "feedback" in reason.lower()


class TestSupervisorReset:
    def test_reset_error_history(self, supervisor, task):
        """reset_error_history should clear error history."""
        check_id = uuid4()
        check_results = {check_id: CheckStatus.FAIL}
        add_conditions_to_task(task, check_results)
        iteration = make_iteration(1, check_results=check_results)

        # Add some errors
        supervisor._check_loop(task, iteration)
        assert len(supervisor._error_history) > 0

        supervisor.reset_error_history()

        assert len(supervisor._error_history) == 0

    def test_reset_rollback_count(self, supervisor):
        """reset_rollback_count should reset rollback counter."""
        supervisor._rollback_count = 5

        supervisor.reset_rollback_count()

        assert supervisor._rollback_count == 0


class TestSupervisorComputeErrorHash:
    def test_computes_hash_for_failed_checks(self, supervisor, task):
        """_compute_error_hash should compute hash for failed checks."""
        check_id = uuid4()
        check_results = {check_id: CheckStatus.FAIL}
        add_conditions_to_task(task, check_results)
        iteration = make_iteration(1, check_results=check_results)

        hash_value = supervisor._compute_error_hash(task, iteration)

        assert hash_value is not None
        assert len(hash_value) == 16  # SHA256 truncated to 16 chars

    def test_returns_none_for_all_passing(self, supervisor, task):
        """_compute_error_hash should return None when all checks pass."""
        check_id = uuid4()
        check_results = {check_id: CheckStatus.PASS}
        add_conditions_to_task(task, check_results)
        iteration = make_iteration(1, check_results=check_results)

        hash_value = supervisor._compute_error_hash(task, iteration)

        assert hash_value is None

    def test_same_hash_for_same_failures(self, supervisor, task):
        """_compute_error_hash should return same hash for same failures."""
        check_id = uuid4()
        check_results = {check_id: CheckStatus.FAIL}
        add_conditions_to_task(task, check_results)
        iteration1 = make_iteration(1, check_results=check_results)
        iteration2 = make_iteration(2, check_results=check_results)

        hash1 = supervisor._compute_error_hash(task, iteration1)
        hash2 = supervisor._compute_error_hash(task, iteration2)

        assert hash1 == hash2


class TestSupervisorCountStagnantIterations:
    def test_counts_trailing_stagnant_iterations(self, supervisor, task):
        """_count_stagnant_iterations should count trailing stagnant
        iterations."""
        task.iterations.append(make_iteration(1, changes=["file.py"]))
        task.iterations.append(make_iteration(2, changes=[]))
        task.iterations.append(make_iteration(3, changes=[]))

        count = supervisor._count_stagnant_iterations(task.iterations)

        assert count == 2

    def test_stops_at_first_non_stagnant(self, supervisor, task):
        """_count_stagnant_iterations should stop at first non-stagnant."""
        task.iterations.append(make_iteration(1, changes=[]))
        task.iterations.append(make_iteration(2, changes=["file.py"]))
        task.iterations.append(make_iteration(3, changes=[]))

        count = supervisor._count_stagnant_iterations(task.iterations)

        assert count == 1

    def test_returns_zero_for_empty_iterations(self, supervisor, task):
        """_count_stagnant_iterations should return 0 for empty iterations."""
        count = supervisor._count_stagnant_iterations([])

        assert count == 0


class TestSupervisorIsFlakyPattern:
    def test_detects_pass_fail_pass(self, supervisor):
        """_is_flaky_pattern should detect PASS-FAIL-PASS."""
        result = supervisor._is_flaky_pattern(
            [
                CheckStatus.PASS,
                CheckStatus.FAIL,
                CheckStatus.PASS,
            ]
        )

        assert result is True

    def test_detects_fail_pass_fail(self, supervisor):
        """_is_flaky_pattern should detect FAIL-PASS-FAIL."""
        result = supervisor._is_flaky_pattern(
            [
                CheckStatus.FAIL,
                CheckStatus.PASS,
                CheckStatus.FAIL,
            ]
        )

        assert result is True

    def test_not_flaky_for_consistent(self, supervisor):
        """_is_flaky_pattern should return False for consistent results."""
        result = supervisor._is_flaky_pattern(
            [
                CheckStatus.FAIL,
                CheckStatus.FAIL,
                CheckStatus.FAIL,
            ]
        )

        assert result is False

    def test_not_flaky_for_less_than_3(self, supervisor):
        """_is_flaky_pattern should return False for < 3 statuses."""
        result = supervisor._is_flaky_pattern(
            [
                CheckStatus.PASS,
                CheckStatus.FAIL,
            ]
        )

        assert result is False

    def test_handles_none_values(self, supervisor):
        """_is_flaky_pattern should filter out None values."""
        result = supervisor._is_flaky_pattern(
            [
                None,
                CheckStatus.PASS,
                CheckStatus.FAIL,
            ]
        )

        assert result is False  # Not enough non-None values
