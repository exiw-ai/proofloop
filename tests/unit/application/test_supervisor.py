from datetime import UTC, datetime
from uuid import uuid4

from src.application.services.supervisor import Supervisor
from src.domain.entities.budget import Budget
from src.domain.entities.condition import Condition
from src.domain.entities.iteration import Iteration, IterationDecision
from src.domain.entities.task import Task
from src.domain.value_objects.condition_enums import CheckStatus, ConditionRole
from src.domain.value_objects.supervision_enums import (
    AnomalyType,
    RetryStrategy,
    SupervisionDecision,
)


def _make_task_with_conditions(
    check_results: dict,
    max_iterations: int = 50,
) -> Task:
    """Create a task with conditions matching check_results."""
    task = Task(
        id=uuid4(),
        description="Test task",
        goals=[],
        sources=["."],
        budget=Budget(max_iterations=max_iterations),
    )
    # Create conditions for each check_id
    for check_id, status in check_results.items():
        condition = Condition(
            id=check_id,
            description=f"Test condition {check_id}",
            role=ConditionRole.BLOCKING,
        )
        condition.check_status = status
        task.conditions.append(condition)
    return task


def test_supervisor_continue_on_progress():
    supervisor = Supervisor()

    task = Task(
        id=uuid4(),
        description="Test task",
        goals=[],
        sources=["."],
        budget=Budget(max_iterations=50),
    )

    iteration = Iteration(
        number=1,
        goal="Make changes",
        changes=["file.py"],  # Has changes = progress
        check_results={},
        decision=IterationDecision.CONTINUE,
        decision_reason="",
        timestamp=datetime.now(UTC),
    )

    result = supervisor.analyze(task, iteration)
    assert result.decision == SupervisionDecision.CONTINUE


def test_supervisor_stop_on_budget_exhaustion():
    supervisor = Supervisor()

    task = Task(
        id=uuid4(),
        description="Test task",
        goals=[],
        sources=["."],
        budget=Budget(max_iterations=10, iteration_count=9),  # 90% used
    )

    iteration = Iteration(
        number=9,
        goal="Another try",
        changes=[],
        check_results={},
        decision=IterationDecision.CONTINUE,
        decision_reason="",
        timestamp=datetime.now(UTC),
    )

    result = supervisor.analyze(task, iteration)
    assert result.decision == SupervisionDecision.STOP
    assert result.anomaly == AnomalyType.CONTRACT_RISK


# ===== Tests for decide_retry_strategy() =====


class TestDecideRetryStrategy:
    def test_first_failure_returns_continue_with_context(self):
        """First failure → CONTINUE_WITH_CONTEXT (give feedback to agent)."""
        supervisor = Supervisor()
        check_id = uuid4()
        check_results = {check_id: CheckStatus.FAIL}
        task = _make_task_with_conditions(check_results)

        iteration = Iteration(
            number=1,
            goal="Make changes",
            changes=["file.py"],
            check_results=check_results,
            decision=IterationDecision.CONTINUE,
            decision_reason="Check failed",
            timestamp=datetime.now(UTC),
        )

        strategy, reason = supervisor.decide_retry_strategy(task, iteration)
        assert strategy == RetryStrategy.CONTINUE_WITH_CONTEXT
        assert "feedback" in reason.lower()

    def test_same_error_twice_returns_rollback(self):
        """Same error 2 times → ROLLBACK_AND_RETRY."""
        supervisor = Supervisor()
        check_id = uuid4()
        check_results = {check_id: CheckStatus.FAIL}
        task = _make_task_with_conditions(check_results)

        # First iteration with failure
        iteration1 = Iteration(
            number=1,
            goal="First attempt",
            changes=["file.py"],
            check_results=check_results,
            decision=IterationDecision.CONTINUE,
            decision_reason="Check failed",
            timestamp=datetime.now(UTC),
        )

        # Register first error
        supervisor._check_loop(task, iteration1)
        supervisor.decide_retry_strategy(task, iteration1)

        # Second iteration with same failure
        iteration2 = Iteration(
            number=2,
            goal="Second attempt",
            changes=["file.py"],
            check_results=check_results,
            decision=IterationDecision.CONTINUE,
            decision_reason="Check still failed",
            timestamp=datetime.now(UTC),
        )

        # Register second error (same pattern)
        supervisor._check_loop(task, iteration2)

        strategy, reason = supervisor.decide_retry_strategy(task, iteration2)
        assert strategy == RetryStrategy.ROLLBACK_AND_RETRY
        assert "repeated" in reason.lower() or "fresh" in reason.lower()

    def test_same_error_exceeds_loop_limit_returns_stop(self):
        """Same error >= loop_limit times → STOP."""
        supervisor = Supervisor(loop_limit=3)
        check_id = uuid4()
        check_results = {check_id: CheckStatus.FAIL}
        task = _make_task_with_conditions(check_results)

        # Simulate loop_limit failures with same error pattern
        for i in range(5):
            iteration = Iteration(
                number=i + 1,
                goal=f"Attempt {i + 1}",
                changes=["file.py"],
                check_results=check_results,
                decision=IterationDecision.CONTINUE,
                decision_reason="Check failed",
                timestamp=datetime.now(UTC),
            )
            supervisor._check_loop(task, iteration)

        # Final check
        final_iteration = Iteration(
            number=6,
            goal="Final attempt",
            changes=["file.py"],
            check_results=check_results,
            decision=IterationDecision.CONTINUE,
            decision_reason="Check failed again",
            timestamp=datetime.now(UTC),
        )
        supervisor._check_loop(task, final_iteration)

        strategy, reason = supervisor.decide_retry_strategy(task, final_iteration)
        assert strategy == RetryStrategy.STOP
        assert "stopping" in reason.lower()

    def test_no_changes_in_iteration_returns_stop(self):
        """Iteration without changes → STOP (stagnation)."""
        supervisor = Supervisor()
        task = _make_task_with_conditions({})

        iteration = Iteration(
            number=1,
            goal="Make changes",
            changes=[],  # No changes
            check_results={},
            decision=IterationDecision.CONTINUE,
            decision_reason="Nothing happened",
            timestamp=datetime.now(UTC),
        )

        strategy, reason = supervisor.decide_retry_strategy(task, iteration)
        assert strategy == RetryStrategy.STOP
        assert "no changes" in reason.lower() or "stopping" in reason.lower()

    def test_rollback_count_respects_limit(self):
        """After rollback_limit rollbacks → STOP, not infinite rollback."""
        supervisor = Supervisor(rollback_limit=1, loop_limit=10)
        check_id = uuid4()
        check_results = {check_id: CheckStatus.FAIL}
        task = _make_task_with_conditions(check_results)

        # Simulate 2 failures with same pattern, triggering first rollback
        for i in range(2):
            iteration = Iteration(
                number=i + 1,
                goal=f"Attempt {i + 1}",
                changes=["file.py"],
                check_results=check_results,
                decision=IterationDecision.CONTINUE,
                decision_reason="Check failed",
                timestamp=datetime.now(UTC),
            )
            supervisor._check_loop(task, iteration)

        # First rollback should happen
        strategy1, _ = supervisor.decide_retry_strategy(task, iteration)
        assert strategy1 == RetryStrategy.ROLLBACK_AND_RETRY

        # Simulate 2 more failures after rollback
        for i in range(2, 4):
            iteration = Iteration(
                number=i + 1,
                goal=f"Attempt {i + 1}",
                changes=["file.py"],
                check_results=check_results,
                decision=IterationDecision.CONTINUE,
                decision_reason="Check failed",
                timestamp=datetime.now(UTC),
            )
            supervisor._check_loop(task, iteration)

        # Second time should NOT rollback (limit reached), should continue with context
        strategy2, _ = supervisor.decide_retry_strategy(task, iteration)
        # Since we've used 1 rollback and limit is 1, next should be CONTINUE_WITH_CONTEXT
        assert strategy2 == RetryStrategy.CONTINUE_WITH_CONTEXT

    def test_different_errors_dont_trigger_loop_detection(self):
        """Different errors → not considered as loop."""
        supervisor = Supervisor()
        check_id1 = uuid4()
        check_id2 = uuid4()

        # First iteration fails check1
        task1 = _make_task_with_conditions({check_id1: CheckStatus.FAIL})
        iteration1 = Iteration(
            number=1,
            goal="First attempt",
            changes=["file.py"],
            check_results={check_id1: CheckStatus.FAIL},
            decision=IterationDecision.CONTINUE,
            decision_reason="Check 1 failed",
            timestamp=datetime.now(UTC),
        )
        supervisor._check_loop(task1, iteration1)

        # Second iteration fails different check (check2)
        task2 = _make_task_with_conditions({check_id2: CheckStatus.FAIL})
        iteration2 = Iteration(
            number=2,
            goal="Second attempt",
            changes=["file.py"],
            check_results={check_id2: CheckStatus.FAIL},
            decision=IterationDecision.CONTINUE,
            decision_reason="Check 2 failed",
            timestamp=datetime.now(UTC),
        )
        supervisor._check_loop(task2, iteration2)

        strategy, reason = supervisor.decide_retry_strategy(task2, iteration2)
        # Different error, should just continue with context
        assert strategy == RetryStrategy.CONTINUE_WITH_CONTEXT

    def test_error_hash_computed_from_failed_check_ids(self):
        """Hash is computed from failed check IDs and task conditions."""
        supervisor = Supervisor()
        check_id1 = uuid4()
        check_id2 = uuid4()

        # Same checks failing = same hash
        task1 = _make_task_with_conditions(
            {check_id1: CheckStatus.FAIL, check_id2: CheckStatus.PASS}
        )
        iteration1 = Iteration(
            number=1,
            goal="Attempt 1",
            changes=["file.py"],
            check_results={check_id1: CheckStatus.FAIL, check_id2: CheckStatus.PASS},
            decision=IterationDecision.CONTINUE,
            decision_reason="",
            timestamp=datetime.now(UTC),
        )

        task2 = _make_task_with_conditions(
            {check_id1: CheckStatus.FAIL, check_id2: CheckStatus.PASS}
        )
        iteration2 = Iteration(
            number=2,
            goal="Attempt 2",
            changes=["file.py"],
            check_results={check_id1: CheckStatus.FAIL, check_id2: CheckStatus.PASS},
            decision=IterationDecision.CONTINUE,
            decision_reason="",
            timestamp=datetime.now(UTC),
        )

        hash1 = supervisor._compute_error_hash(task1, iteration1)
        hash2 = supervisor._compute_error_hash(task2, iteration2)
        assert hash1 == hash2

        # Different check failing = different hash
        task3 = _make_task_with_conditions(
            {check_id1: CheckStatus.PASS, check_id2: CheckStatus.FAIL}
        )
        iteration3 = Iteration(
            number=3,
            goal="Attempt 3",
            changes=["file.py"],
            check_results={check_id1: CheckStatus.PASS, check_id2: CheckStatus.FAIL},
            decision=IterationDecision.CONTINUE,
            decision_reason="",
            timestamp=datetime.now(UTC),
        )

        hash3 = supervisor._compute_error_hash(task3, iteration3)
        assert hash1 != hash3

    def test_reset_rollback_count(self):
        """reset_rollback_count() resets the counter."""
        supervisor = Supervisor(rollback_limit=1)
        check_id = uuid4()
        check_results = {check_id: CheckStatus.FAIL}
        task = _make_task_with_conditions(check_results)

        # Trigger a rollback
        for i in range(2):
            iteration = Iteration(
                number=i + 1,
                goal=f"Attempt {i + 1}",
                changes=["file.py"],
                check_results=check_results,
                decision=IterationDecision.CONTINUE,
                decision_reason="",
                timestamp=datetime.now(UTC),
            )
            supervisor._check_loop(task, iteration)

        strategy, _ = supervisor.decide_retry_strategy(task, iteration)
        assert strategy == RetryStrategy.ROLLBACK_AND_RETRY
        assert supervisor._rollback_count == 1

        # Reset
        supervisor.reset_rollback_count()
        assert supervisor._rollback_count == 0
