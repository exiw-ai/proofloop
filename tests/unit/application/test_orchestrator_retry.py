"""Unit tests for Orchestrator retry flow with Supervisor integration."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.application.orchestrator import Orchestrator
from src.domain.entities.budget import Budget
from src.domain.entities.condition import Condition
from src.domain.entities.iteration import Iteration, IterationDecision
from src.domain.entities.plan import Plan, PlanStep
from src.domain.entities.task import Task
from src.domain.ports.agent_port import AgentResult
from src.domain.ports.diff_port import DiffResult
from src.domain.value_objects.condition_enums import CheckStatus, ConditionRole
from src.domain.value_objects.supervision_enums import RetryStrategy
from src.domain.value_objects.task_status import TaskStatus


@pytest.fixture
def mock_agent():
    agent = AsyncMock()
    agent.execute.return_value = AgentResult(
        messages=[],
        final_response="Done",
        tools_used=["Bash"],
    )
    return agent


@pytest.fixture
def mock_verification_port():
    return AsyncMock()


@pytest.fixture
def mock_check_runner():
    return AsyncMock()


@pytest.fixture
def mock_diff_port():
    port = AsyncMock()
    port.get_worktree_diff.return_value = DiffResult(
        diff="",
        patch="",
        files_changed=["file.py"],
        insertions=10,
        deletions=5,
    )
    port.stash_changes.return_value = "Saved working directory"
    port.rollback_all.return_value = []
    return port


@pytest.fixture
def mock_task_repo():
    return AsyncMock()


@pytest.fixture
def orchestrator(
    mock_agent, mock_verification_port, mock_check_runner, mock_diff_port, mock_task_repo, tmp_path
):
    return Orchestrator(
        agent=mock_agent,
        verification_port=mock_verification_port,
        check_runner=mock_check_runner,
        diff_port=mock_diff_port,
        task_repo=mock_task_repo,
        state_dir=tmp_path,
    )


@pytest.fixture
def task_with_failed_checks():
    task = Task(
        id=uuid4(),
        description="Test task",
        goals=["Goal 1"],
        sources=["/tmp/test"],
        budget=Budget(max_iterations=10),
    )
    task.status = TaskStatus.EXECUTING

    condition = Condition(
        id=uuid4(),
        description="Tests must pass",
        role=ConditionRole.BLOCKING,
        check_id=uuid4(),
    )
    condition.check_status = CheckStatus.FAIL

    task.conditions = [condition]
    task.plan = Plan(
        goal="Complete task", boundaries=[], steps=[PlanStep(number=1, description="Do work")]
    )
    task.plan.approve()

    return task


@pytest.fixture
def previous_iteration():
    return Iteration(
        number=1,
        goal="First attempt",
        changes=["file.py"],
        check_results={uuid4(): CheckStatus.FAIL},
        decision=IterationDecision.CONTINUE,
        decision_reason="Checks not passing",
        timestamp=datetime.now(UTC),
    )


class TestOrchestratorRetry:
    @pytest.mark.asyncio
    async def test_supervisor_called_after_first_iteration(
        self, orchestrator, task_with_failed_checks, previous_iteration
    ):
        """Supervisor.decide_retry_strategy() is called after first
        iteration."""
        with patch.object(
            orchestrator.supervisor,
            "decide_retry_strategy",
            return_value=(RetryStrategy.STOP, "Test"),
        ) as mock_decide:
            await orchestrator._handle_retry(task_with_failed_checks, previous_iteration)

            mock_decide.assert_called_once_with(task_with_failed_checks, previous_iteration)

    @pytest.mark.asyncio
    async def test_retry_strategy_continue_calls_execute_retry(
        self, orchestrator, task_with_failed_checks, previous_iteration
    ):
        """CONTINUE_WITH_CONTEXT → calls execute_delivery.execute_retry()."""
        orchestrator.supervisor = MagicMock()
        orchestrator.supervisor.decide_retry_strategy.return_value = (
            RetryStrategy.CONTINUE_WITH_CONTEXT,
            "Providing feedback",
        )
        orchestrator.supervisor._check_loop = MagicMock()

        with patch.object(
            orchestrator.execute_delivery, "execute_retry", new_callable=AsyncMock
        ) as mock_retry:
            mock_retry.return_value = previous_iteration

            await orchestrator._handle_retry(task_with_failed_checks, previous_iteration)

            mock_retry.assert_called_once()
            # Check that task and previous_iteration were passed (as args or kwargs)
            call_args = mock_retry.call_args
            assert (
                task_with_failed_checks in call_args.args
                or call_args.kwargs.get("task") == task_with_failed_checks
            )
            assert (
                previous_iteration in call_args.args
                or call_args.kwargs.get("previous_iteration") == previous_iteration
            )

    @pytest.mark.asyncio
    async def test_retry_strategy_rollback_stashes_and_retries(
        self, orchestrator, task_with_failed_checks, previous_iteration, mock_diff_port
    ):
        """ROLLBACK_AND_RETRY → rollback_all + execute_fresh_retry with
        warning."""
        from pathlib import Path

        from src.infrastructure.git.repo_root import WorkspaceInfo

        orchestrator.supervisor = MagicMock()
        orchestrator.supervisor.decide_retry_strategy.return_value = (
            RetryStrategy.ROLLBACK_AND_RETRY,
            "Same error repeated",
        )
        orchestrator.supervisor._check_loop = MagicMock()

        # Set up workspace info on WorkspaceManager so rollback_all_repos works
        orchestrator._workspace_manager._workspace_info = WorkspaceInfo(
            is_workspace=False,
            repos=[Path("/test/repo")],
            root=Path("/test/repo"),
        )

        with patch.object(
            orchestrator.execute_delivery, "execute_fresh_retry", new_callable=AsyncMock
        ) as mock_fresh:
            mock_fresh.return_value = previous_iteration

            await orchestrator._handle_retry(task_with_failed_checks, previous_iteration)

            # Check rollback_all was called (new multi-repo API)
            mock_diff_port.rollback_all.assert_called_once()
            rollback_call = mock_diff_port.rollback_all.call_args
            assert "rollback" in rollback_call.args[1].lower()

            # Check fresh retry was called with warning
            mock_fresh.assert_called_once()
            call_kwargs = mock_fresh.call_args.kwargs
            assert "different approach" in call_kwargs["warning"].lower()

    @pytest.mark.asyncio
    async def test_retry_strategy_stop_skips_retry(
        self, orchestrator, task_with_failed_checks, previous_iteration
    ):
        """STOP → retry is not executed."""
        orchestrator.supervisor = MagicMock()
        orchestrator.supervisor.decide_retry_strategy.return_value = (
            RetryStrategy.STOP,
            "No changes made",
        )
        orchestrator.supervisor._check_loop = MagicMock()

        with (
            patch.object(
                orchestrator.execute_delivery, "execute_retry", new_callable=AsyncMock
            ) as mock_retry,
            patch.object(
                orchestrator.execute_delivery, "execute_fresh_retry", new_callable=AsyncMock
            ) as mock_fresh,
        ):
            result = await orchestrator._handle_retry(task_with_failed_checks, previous_iteration)

            # Neither retry method should be called
            mock_retry.assert_not_called()
            mock_fresh.assert_not_called()

            # Should return previous iteration unchanged
            assert result == previous_iteration

    @pytest.mark.asyncio
    async def test_supervisor_receives_correct_iteration(
        self, orchestrator, task_with_failed_checks, previous_iteration
    ):
        """Supervisor receives the latest iteration for analysis."""
        orchestrator.supervisor = MagicMock()
        orchestrator.supervisor.decide_retry_strategy.return_value = (
            RetryStrategy.STOP,
            "Test",
        )
        orchestrator.supervisor._check_loop = MagicMock()

        await orchestrator._handle_retry(task_with_failed_checks, previous_iteration)

        # Check _check_loop was called with correct task and iteration
        orchestrator.supervisor._check_loop.assert_called_once_with(
            task_with_failed_checks, previous_iteration
        )

        # Check decide_retry_strategy was called with correct task and iteration
        orchestrator.supervisor.decide_retry_strategy.assert_called_once_with(
            task_with_failed_checks, previous_iteration
        )

    @pytest.mark.asyncio
    async def test_handle_retry_logs_strategy(
        self, orchestrator, task_with_failed_checks, previous_iteration
    ):
        """_handle_retry logs the chosen strategy."""
        orchestrator.supervisor = MagicMock()
        orchestrator.supervisor.decide_retry_strategy.return_value = (
            RetryStrategy.CONTINUE_WITH_CONTEXT,
            "Providing feedback",
        )
        orchestrator.supervisor._check_loop = MagicMock()

        with patch.object(
            orchestrator.execute_delivery, "execute_retry", new_callable=AsyncMock
        ) as mock_retry:
            mock_retry.return_value = previous_iteration

            with patch("src.application.orchestrator.logger") as mock_logger:
                await orchestrator._handle_retry(task_with_failed_checks, previous_iteration)

                # Check that strategy was logged
                warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
                assert any("continue_with_context" in c.lower() for c in warning_calls)


class TestRetryLoop:
    """Tests for the retry loop behavior (Fix #23)."""

    @pytest.mark.asyncio
    async def test_retry_loop_continues_until_budget_exhausted(
        self, orchestrator, task_with_failed_checks, previous_iteration
    ):
        """Retry loop continues until budget.is_exhausted() returns True."""
        call_count = 0

        async def mock_execute_retry(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            # After 3 calls, mark budget as exhausted
            if call_count >= 3:
                task_with_failed_checks.budget.iteration_count = (
                    task_with_failed_checks.budget.max_iterations
                )
            return Iteration(
                number=call_count + 1,
                goal=f"Retry {call_count}",
                changes=["file.py"],
                check_results={},
                decision=IterationDecision.CONTINUE,
                decision_reason="Still failing",
                timestamp=datetime.now(UTC),
            )

        orchestrator.supervisor = MagicMock()
        orchestrator.supervisor.decide_retry_strategy.return_value = (
            RetryStrategy.CONTINUE_WITH_CONTEXT,
            "Providing feedback",
        )
        orchestrator.supervisor._check_loop = MagicMock()

        with patch.object(
            orchestrator.execute_delivery, "execute_retry", side_effect=mock_execute_retry
        ):
            # Simulate the while loop in orchestrator.run()
            iteration = previous_iteration
            while (
                not task_with_failed_checks.can_mark_done()
                and not task_with_failed_checks.budget.is_exhausted()
            ):
                iteration = await orchestrator._handle_retry(task_with_failed_checks, iteration)
                if iteration == orchestrator._last_iteration:
                    break
                orchestrator._last_iteration = iteration

        # Should have called execute_retry 3 times before budget exhausted
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_loop_stops_when_supervisor_returns_stop(
        self, orchestrator, task_with_failed_checks, previous_iteration
    ):
        """Retry loop stops immediately when supervisor returns STOP."""
        call_count = 0

        def mock_decide_strategy(_task, _iteration):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                return (RetryStrategy.STOP, "Same error repeated")
            return (RetryStrategy.CONTINUE_WITH_CONTEXT, "Trying again")

        orchestrator.supervisor = MagicMock()
        orchestrator.supervisor.decide_retry_strategy.side_effect = mock_decide_strategy
        orchestrator.supervisor._check_loop = MagicMock()

        with patch.object(
            orchestrator.execute_delivery, "execute_retry", new_callable=AsyncMock
        ) as mock_retry:
            mock_retry.return_value = Iteration(
                number=2,
                goal="Retry",
                changes=["file.py"],
                check_results={},
                decision=IterationDecision.CONTINUE,
                decision_reason="Still failing",
                timestamp=datetime.now(UTC),
            )

            # Simulate the while loop
            iteration = previous_iteration
            while (
                not task_with_failed_checks.can_mark_done()
                and not task_with_failed_checks.budget.is_exhausted()
            ):
                new_iteration = await orchestrator._handle_retry(task_with_failed_checks, iteration)
                if new_iteration == iteration:
                    # STOP was returned
                    break
                iteration = new_iteration

        # Should have called decide_retry_strategy twice (first CONTINUE, then STOP)
        assert call_count == 2
        # execute_retry should only be called once (before STOP)
        assert mock_retry.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_loop_stops_when_task_done(
        self, orchestrator, task_with_failed_checks, previous_iteration
    ):
        """Retry loop stops when task.can_mark_done() returns True."""
        call_count = 0

        async def mock_execute_retry(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            # After 2 calls, mark condition as passed
            if call_count >= 2:
                for condition in task_with_failed_checks.conditions:
                    condition.check_status = CheckStatus.PASS
                    condition.approve()
                    condition.evidence_ref = MagicMock()
            return Iteration(
                number=call_count + 1,
                goal=f"Retry {call_count}",
                changes=["file.py"],
                check_results={},
                decision=IterationDecision.CONTINUE,
                decision_reason="Working",
                timestamp=datetime.now(UTC),
            )

        orchestrator.supervisor = MagicMock()
        orchestrator.supervisor.decide_retry_strategy.return_value = (
            RetryStrategy.CONTINUE_WITH_CONTEXT,
            "Providing feedback",
        )
        orchestrator.supervisor._check_loop = MagicMock()

        with patch.object(
            orchestrator.execute_delivery, "execute_retry", side_effect=mock_execute_retry
        ):
            iteration = previous_iteration
            while (
                not task_with_failed_checks.can_mark_done()
                and not task_with_failed_checks.budget.is_exhausted()
            ):
                iteration = await orchestrator._handle_retry(task_with_failed_checks, iteration)
                if iteration == orchestrator._last_iteration:
                    break
                orchestrator._last_iteration = iteration

        # Should have called execute_retry 2 times before task became done
        assert call_count == 2
        assert task_with_failed_checks.can_mark_done()
