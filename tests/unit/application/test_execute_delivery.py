from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.use_cases.execute_delivery import ExecuteDelivery
from src.domain.entities.budget import Budget
from src.domain.entities.condition import Condition
from src.domain.entities.iteration import Iteration, IterationDecision
from src.domain.entities.plan import Plan, PlanStep
from src.domain.entities.task import Task
from src.domain.ports.agent_port import AgentResult
from src.domain.ports.diff_port import DiffResult
from src.domain.value_objects.condition_enums import CheckStatus, ConditionRole
from src.domain.value_objects.evidence_types import EvidenceSummary
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
    return port


@pytest.fixture
def mock_task_repo():
    return AsyncMock()


@pytest.fixture
def execute_delivery(mock_agent, mock_check_runner, mock_diff_port, mock_task_repo, tmp_path):
    return ExecuteDelivery(
        agent=mock_agent,
        check_runner=mock_check_runner,
        diff_port=mock_diff_port,
        task_repo=mock_task_repo,
        state_dir=tmp_path,
    )


@pytest.fixture
def task_with_failed_condition():
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
    condition.evidence_summary = EvidenceSummary(
        command="pytest",
        cwd="/tmp/test",
        exit_code=1,
        duration_ms=5000,
        output_tail="FAILED test_example.py::test_one - AssertionError",
        timestamp=datetime.now(UTC),
    )

    task.conditions = [condition]
    task.plan = Plan(
        goal="Complete task", boundaries=[], steps=[PlanStep(number=1, description="Fix tests")]
    )
    task.plan.approve()

    return task


@pytest.fixture
def previous_iteration():
    return Iteration(
        number=1,
        goal="First attempt",
        changes=["file.py", "test_file.py"],
        check_results={uuid4(): CheckStatus.FAIL},
        decision=IterationDecision.CONTINUE,
        decision_reason="Checks not passing",
        timestamp=datetime.now(UTC),
    )


# ===== Tests for _build_retry_prompt() =====


class TestBuildRetryPrompt:
    def test_includes_task_description(
        self, execute_delivery, task_with_failed_condition, previous_iteration
    ):
        """Prompt contains task description."""
        failed = execute_delivery._get_failed_conditions_with_evidence(task_with_failed_condition)
        prompt = execute_delivery._build_retry_prompt(
            task_with_failed_condition, previous_iteration, failed
        )

        assert task_with_failed_condition.description in prompt

    def test_includes_previous_iteration_changes(
        self, execute_delivery, task_with_failed_condition, previous_iteration
    ):
        """Prompt contains list of changed files."""
        failed = execute_delivery._get_failed_conditions_with_evidence(task_with_failed_condition)
        prompt = execute_delivery._build_retry_prompt(
            task_with_failed_condition, previous_iteration, failed
        )

        assert "file.py" in prompt
        assert "test_file.py" in prompt

    def test_includes_failed_conditions_with_evidence(
        self, execute_delivery, task_with_failed_condition, previous_iteration
    ):
        """Prompt contains failed conditions + output_tail."""
        failed = execute_delivery._get_failed_conditions_with_evidence(task_with_failed_condition)
        prompt = execute_delivery._build_retry_prompt(
            task_with_failed_condition, previous_iteration, failed
        )

        assert "Tests must pass" in prompt
        assert "FAILED" in prompt

    def test_evidence_output_tail_included(
        self, execute_delivery, task_with_failed_condition, previous_iteration
    ):
        """Evidence output_tail is fully included in prompt."""
        failed = execute_delivery._get_failed_conditions_with_evidence(task_with_failed_condition)
        prompt = execute_delivery._build_retry_prompt(
            task_with_failed_condition, previous_iteration, failed
        )

        assert "AssertionError" in prompt

    def test_exit_code_shown_for_failed_checks(
        self, execute_delivery, task_with_failed_condition, previous_iteration
    ):
        """Exit code is shown for each failed check."""
        failed = execute_delivery._get_failed_conditions_with_evidence(task_with_failed_condition)
        prompt = execute_delivery._build_retry_prompt(
            task_with_failed_condition, previous_iteration, failed
        )

        assert "Exit code: 1" in prompt

    def test_handles_no_evidence(self, execute_delivery, previous_iteration):
        """Handles condition without evidence gracefully."""
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
            description="Manual condition",
            role=ConditionRole.BLOCKING,
            check_id=None,
        )
        condition.check_status = CheckStatus.FAIL
        # No evidence_summary set

        task.conditions = [condition]

        failed = execute_delivery._get_failed_conditions_with_evidence(task)
        prompt = execute_delivery._build_retry_prompt(task, previous_iteration, failed)

        assert "Manual condition" in prompt
        assert "No evidence available" in prompt


# ===== Tests for execute_retry() =====


class TestExecuteRetry:
    @pytest.mark.asyncio
    async def test_uses_retry_prompt_not_initial(
        self,
        execute_delivery,
        mock_agent,
        task_with_failed_condition,
        previous_iteration,
    ):
        """execute_retry() uses _build_retry_prompt(), not
        _build_full_plan_prompt()."""
        await execute_delivery.execute_retry(task_with_failed_condition, previous_iteration)

        # Check that agent was called with retry-style prompt
        call_args = mock_agent.execute.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]

        assert "continuing work" in prompt.lower()
        assert "previous attempt" in prompt.lower()
        assert "failed checks" in prompt.lower()

    @pytest.mark.asyncio
    async def test_passes_previous_iteration_to_prompt_builder(
        self,
        execute_delivery,
        mock_agent,
        task_with_failed_condition,
        previous_iteration,
    ):
        """Previous iteration is passed to prompt builder."""
        await execute_delivery.execute_retry(task_with_failed_condition, previous_iteration)

        call_args = mock_agent.execute.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]

        # Should contain info from previous iteration
        assert "file.py" in prompt  # From previous_iteration.changes

    @pytest.mark.asyncio
    async def test_failed_conditions_extracted_correctly(
        self, execute_delivery, task_with_failed_condition
    ):
        """Failed conditions are correctly extracted from task."""
        failed = execute_delivery._get_failed_conditions_with_evidence(task_with_failed_condition)

        assert len(failed) == 1
        condition, evidence = failed[0]
        assert condition.description == "Tests must pass"
        assert evidence is not None
        assert evidence.exit_code == 1


# ===== Tests for _get_failed_conditions_with_evidence() =====


class TestGetFailedConditionsWithEvidence:
    def test_returns_only_failed_conditions(self, execute_delivery):
        """Only returns conditions with FAIL status."""
        task = Task(
            id=uuid4(),
            description="Test task",
            goals=[],
            sources=["/tmp/test"],
            budget=Budget(max_iterations=10),
        )

        passing = Condition(
            id=uuid4(),
            description="Passing condition",
            role=ConditionRole.BLOCKING,
        )
        passing.check_status = CheckStatus.PASS

        failing = Condition(
            id=uuid4(),
            description="Failing condition",
            role=ConditionRole.BLOCKING,
        )
        failing.check_status = CheckStatus.FAIL

        task.conditions = [passing, failing]

        failed = execute_delivery._get_failed_conditions_with_evidence(task)

        assert len(failed) == 1
        assert failed[0][0].description == "Failing condition"

    def test_returns_empty_list_when_all_pass(self, execute_delivery):
        """Returns empty list when all conditions pass."""
        task = Task(
            id=uuid4(),
            description="Test task",
            goals=[],
            sources=["/tmp/test"],
            budget=Budget(max_iterations=10),
        )

        passing = Condition(
            id=uuid4(),
            description="Passing condition",
            role=ConditionRole.BLOCKING,
        )
        passing.check_status = CheckStatus.PASS

        task.conditions = [passing]

        failed = execute_delivery._get_failed_conditions_with_evidence(task)

        assert len(failed) == 0


# ===== Tests for execute_fresh_retry() =====


class TestExecuteFreshRetry:
    @pytest.mark.asyncio
    async def test_includes_warning_in_prompt(
        self, execute_delivery, mock_agent, task_with_failed_condition
    ):
        """execute_fresh_retry() includes warning message in prompt."""
        warning = "Previous approach failed repeatedly. Try a different approach."

        await execute_delivery.execute_fresh_retry(task_with_failed_condition, warning)

        call_args = mock_agent.execute.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]

        assert warning in prompt
        assert "WARNING" in prompt
