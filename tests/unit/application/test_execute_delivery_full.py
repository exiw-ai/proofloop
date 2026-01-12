"""Comprehensive tests for ExecuteDelivery use case."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.application.use_cases.execute_delivery import ExecuteDelivery
from src.domain.entities.budget import Budget
from src.domain.entities.condition import Condition
from src.domain.entities.iteration import Iteration, IterationDecision
from src.domain.entities.plan import Plan, PlanStep
from src.domain.entities.task import Task
from src.domain.entities.verification_inventory import VerificationInventory
from src.domain.ports.agent_port import AgentResult
from src.domain.ports.diff_port import DiffResult
from src.domain.value_objects.check_types import CheckKind, CheckSpec
from src.domain.value_objects.condition_enums import CheckStatus, ConditionRole
from src.domain.value_objects.evidence_types import EvidenceSummary
from src.domain.value_objects.task_status import TaskStatus


@pytest.fixture
def mock_agent():
    agent = AsyncMock()
    agent.execute.return_value = AgentResult(
        messages=[],
        final_response="Done",
        tools_used=["Bash", "Edit"],
    )
    return agent


@pytest.fixture
def mock_check_runner():
    runner = AsyncMock()
    runner.run_check.return_value = MagicMock(
        check_id=uuid4(),
        status=CheckStatus.PASS,
        exit_code=0,
        stdout="All tests passed",
        stderr="",
        duration_ms=1000,
        timestamp=datetime.now(UTC),
    )
    return runner


@pytest.fixture
def mock_diff_port():
    port = AsyncMock()
    port.get_worktree_diff.return_value = DiffResult(
        diff="+ new line",
        patch="patch",
        files_changed=["file.py", "test.py"],
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
def task_with_plan(tmp_path):
    task = Task(
        id=uuid4(),
        description="Test task",
        goals=["Goal 1"],
        sources=[str(tmp_path)],
        budget=Budget(max_iterations=10),
    )
    task.plan = Plan(
        goal="Implement feature",
        boundaries=[],
        steps=[
            PlanStep(number=1, description="Step 1", target_files=["file.py"]),
            PlanStep(number=2, description="Step 2", target_files=["test.py"]),
        ],
    )
    task.plan.approve()
    return task


class TestExecuteDeliveryExecute:
    @pytest.mark.asyncio
    async def test_execute_transitions_to_executing(self, execute_delivery, task_with_plan):
        """Execute should transition task to EXECUTING."""
        await execute_delivery.execute(task_with_plan)

        assert task_with_plan.status == TaskStatus.EXECUTING

    @pytest.mark.asyncio
    async def test_execute_returns_iteration(self, execute_delivery, task_with_plan):
        """Execute should return an iteration."""
        iteration = await execute_delivery.execute(task_with_plan)

        assert isinstance(iteration, Iteration)
        assert iteration.number == 1
        assert "file.py" in iteration.changes
        assert "test.py" in iteration.changes

    @pytest.mark.asyncio
    async def test_execute_adds_iteration_to_task(self, execute_delivery, task_with_plan):
        """Execute should add iteration to task."""
        await execute_delivery.execute(task_with_plan)

        assert len(task_with_plan.iterations) == 1

    @pytest.mark.asyncio
    async def test_execute_saves_task(self, execute_delivery, task_with_plan, mock_task_repo):
        """Execute should save task after completion."""
        await execute_delivery.execute(task_with_plan)

        mock_task_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_message_callback(
        self, execute_delivery, task_with_plan, mock_agent
    ):
        """Execute should wrap callback with command tracker."""
        callback = MagicMock()
        await execute_delivery.execute(task_with_plan, on_message=callback)

        mock_agent.execute.assert_called_once()
        # Callback should be wrapped (not the exact same object)
        wrapped_callback = mock_agent.execute.call_args.kwargs.get("on_message")
        assert wrapped_callback is not None
        assert wrapped_callback != callback  # It's wrapped now

        # Verify the wrapper calls the original callback
        from src.domain.ports.agent_port import AgentMessage

        test_msg = AgentMessage(role="test", content="test")
        wrapped_callback(test_msg)
        callback.assert_called_once_with(test_msg)

    @pytest.mark.asyncio
    async def test_execute_without_plan(
        self, execute_delivery, mock_agent, tmp_path, mock_task_repo
    ):
        """Execute should work without a plan."""
        task = Task(
            id=uuid4(),
            description="Simple task",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )

        iteration = await execute_delivery.execute(task)

        assert iteration is not None
        call_args = mock_agent.execute.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "Simple task" in prompt


class TestBuildFullPlanPrompt:
    def test_includes_task_description(self, execute_delivery, task_with_plan):
        """_build_full_plan_prompt should include task description."""
        prompt = execute_delivery._build_full_plan_prompt(task_with_plan)

        assert "Test task" in prompt

    def test_includes_plan_steps(self, execute_delivery, task_with_plan):
        """_build_full_plan_prompt should include all plan steps."""
        prompt = execute_delivery._build_full_plan_prompt(task_with_plan)

        assert "Step 1" in prompt
        assert "Step 2" in prompt

    def test_includes_constraints(self, execute_delivery, task_with_plan):
        """_build_full_plan_prompt should include constraints."""
        task_with_plan.constraints = ["No breaking changes"]
        prompt = execute_delivery._build_full_plan_prompt(task_with_plan)

        assert "No breaking changes" in prompt

    def test_includes_blocking_conditions(self, execute_delivery, task_with_plan):
        """_build_full_plan_prompt should include blocking conditions."""
        cond = Condition(
            id=uuid4(),
            description="Tests must pass",
            role=ConditionRole.BLOCKING,
        )
        task_with_plan.conditions = [cond]

        prompt = execute_delivery._build_full_plan_prompt(task_with_plan)

        assert "Tests must pass" in prompt

    def test_without_plan(self, execute_delivery, tmp_path):
        """_build_full_plan_prompt should handle task without plan."""
        task = Task(
            id=uuid4(),
            description="No plan task",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )

        prompt = execute_delivery._build_full_plan_prompt(task)

        assert "No plan task" in prompt


class TestRunAllChecks:
    @pytest.mark.asyncio
    async def test_runs_automated_checks(self, execute_delivery, task_with_plan, mock_check_runner):
        """_run_all_checks should run automated checks."""
        check_id = uuid4()
        task_with_plan.verification_inventory = VerificationInventory(
            checks=[
                CheckSpec(
                    id=check_id,
                    name="pytest",
                    kind=CheckKind.TEST,
                    command="pytest",
                    cwd=task_with_plan.sources[0],
                )
            ],
            baseline=None,
            project_structure={},
            conventions=[],
        )
        cond = Condition(
            id=uuid4(),
            description="Tests pass",
            role=ConditionRole.BLOCKING,
            check_id=check_id,
        )
        task_with_plan.conditions = [cond]

        results = await execute_delivery._run_all_checks(task_with_plan, 1)

        assert cond.id in results
        mock_check_runner.run_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_verifies_manual_conditions(self, execute_delivery, task_with_plan, mock_agent):
        """_run_all_checks should verify manual conditions via agent."""
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="Looks good CONDITION_PASS",
            tools_used=["Read"],
        )
        cond = Condition(
            id=uuid4(),
            description="Manual check",
            role=ConditionRole.BLOCKING,
            check_id=None,  # Manual condition
        )
        cond.check_status = CheckStatus.NOT_RUN  # Must be NOT_RUN to trigger verification
        task_with_plan.conditions = [cond]

        results = await execute_delivery._run_all_checks(task_with_plan, 1)

        assert cond.id in results
        assert results[cond.id] == CheckStatus.PASS


class TestVerifyManualCondition:
    @pytest.mark.asyncio
    async def test_returns_pass_on_condition_pass(
        self, execute_delivery, task_with_plan, mock_agent
    ):
        """_verify_manual_condition should return PASS on CONDITION_PASS."""
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="Everything looks good. CONDITION_PASS",
            tools_used=["Read"],
        )
        cond = Condition(
            id=uuid4(),
            description="Check something",
            role=ConditionRole.BLOCKING,
        )

        status, evidence_ref, evidence_summary = await execute_delivery._verify_manual_condition(
            task_with_plan, 1, cond
        )

        assert status == CheckStatus.PASS
        assert evidence_ref is not None
        assert evidence_summary is not None

    @pytest.mark.asyncio
    async def test_returns_fail_on_condition_fail(
        self, execute_delivery, task_with_plan, mock_agent
    ):
        """_verify_manual_condition should return FAIL on CONDITION_FAIL."""
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="Not satisfied. CONDITION_FAIL",
            tools_used=["Read"],
        )
        cond = Condition(
            id=uuid4(),
            description="Check something",
            role=ConditionRole.BLOCKING,
        )

        status, _, _ = await execute_delivery._verify_manual_condition(task_with_plan, 1, cond)

        assert status == CheckStatus.FAIL

    @pytest.mark.asyncio
    async def test_returns_fail_on_no_verdict(self, execute_delivery, task_with_plan, mock_agent):
        """_verify_manual_condition should return FAIL if no verdict in
        response."""
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="I checked but couldn't determine",
            tools_used=["Read"],
        )
        cond = Condition(
            id=uuid4(),
            description="Check something",
            role=ConditionRole.BLOCKING,
        )

        status, _, _ = await execute_delivery._verify_manual_condition(task_with_plan, 1, cond)

        assert status == CheckStatus.FAIL


class TestRecordEvidence:
    @pytest.mark.asyncio
    async def test_creates_evidence_ref(self, execute_delivery, task_with_plan):
        """_record_evidence should create evidence ref."""
        run_result = MagicMock(
            check_id=uuid4(),
            status=CheckStatus.PASS,
            exit_code=0,
            stdout="OK",
            stderr="",
            duration_ms=1000,
            timestamp=datetime.now(UTC),
        )

        evidence_ref, evidence_summary = await execute_delivery._record_evidence(
            task_with_plan, 1, uuid4(), run_result, "pytest"
        )

        assert evidence_ref is not None
        assert evidence_ref.task_id == task_with_plan.id
        assert evidence_summary is not None
        assert evidence_summary.command == "pytest"

    @pytest.mark.asyncio
    async def test_truncates_long_output(self, execute_delivery, task_with_plan):
        """_record_evidence should truncate long output."""
        run_result = MagicMock(
            check_id=uuid4(),
            status=CheckStatus.PASS,
            exit_code=0,
            stdout="x" * 1000,
            stderr="",
            duration_ms=1000,
            timestamp=datetime.now(UTC),
        )

        _, evidence_summary = await execute_delivery._record_evidence(
            task_with_plan, 1, uuid4(), run_result, "pytest"
        )

        assert len(evidence_summary.output_tail) <= 500


class TestExecuteRetry:
    @pytest.fixture
    def previous_iteration(self):
        return Iteration(
            number=1,
            goal="First attempt",
            changes=["file.py"],
            check_results={},
            decision=IterationDecision.CONTINUE,
            decision_reason="Checks failed",
            timestamp=datetime.now(UTC),
        )

    @pytest.mark.asyncio
    async def test_includes_previous_iteration_in_prompt(
        self, execute_delivery, task_with_plan, previous_iteration, mock_agent
    ):
        """execute_retry should include previous iteration in prompt."""
        cond = Condition(
            id=uuid4(),
            description="Tests pass",
            role=ConditionRole.BLOCKING,
        )
        cond.check_status = CheckStatus.FAIL
        cond.evidence_summary = EvidenceSummary(
            command="pytest",
            cwd="/tmp",
            exit_code=1,
            duration_ms=1000,
            output_tail="FAILED test_example",
            timestamp=datetime.now(UTC),
        )
        task_with_plan.conditions = [cond]

        await execute_delivery.execute_retry(task_with_plan, previous_iteration)

        # First call is the retry prompt, second call is manual condition verification
        call_args = mock_agent.execute.call_args_list[0]
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "previous attempt" in prompt.lower()
        assert "file.py" in prompt
        assert "FAILED test_example" in prompt

    @pytest.mark.asyncio
    async def test_returns_new_iteration(
        self, execute_delivery, task_with_plan, previous_iteration
    ):
        """execute_retry should return a new iteration."""
        task_with_plan.iterations.append(previous_iteration)

        new_iteration = await execute_delivery.execute_retry(task_with_plan, previous_iteration)

        assert new_iteration.number == 2
        assert "Fix failed checks" in new_iteration.goal


class TestExecuteFreshRetry:
    @pytest.mark.asyncio
    async def test_includes_warning_in_prompt(self, execute_delivery, task_with_plan, mock_agent):
        """execute_fresh_retry should include warning in prompt."""
        warning = "Previous approach failed repeatedly"

        await execute_delivery.execute_fresh_retry(task_with_plan, warning)

        call_args = mock_agent.execute.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "WARNING" in prompt
        assert warning in prompt

    @pytest.mark.asyncio
    async def test_returns_iteration_with_fresh_goal(self, execute_delivery, task_with_plan):
        """execute_fresh_retry should return iteration with fresh retry
        goal."""
        iteration = await execute_delivery.execute_fresh_retry(
            task_with_plan, "Try different approach"
        )

        assert "Fresh retry" in iteration.goal
        assert "different approach" in iteration.goal


class TestGetFailedConditionsWithEvidence:
    def test_returns_only_failed_conditions(self, execute_delivery, task_with_plan):
        """_get_failed_conditions_with_evidence should return only failed
        conditions."""
        passing = Condition(
            id=uuid4(),
            description="Passing",
            role=ConditionRole.BLOCKING,
        )
        passing.check_status = CheckStatus.PASS

        failing = Condition(
            id=uuid4(),
            description="Failing",
            role=ConditionRole.BLOCKING,
        )
        failing.check_status = CheckStatus.FAIL

        task_with_plan.conditions = [passing, failing]

        failed = execute_delivery._get_failed_conditions_with_evidence(task_with_plan)

        assert len(failed) == 1
        assert failed[0][0].description == "Failing"

    def test_includes_evidence_summary(self, execute_delivery, task_with_plan):
        """_get_failed_conditions_with_evidence should include evidence."""
        cond = Condition(
            id=uuid4(),
            description="Failing",
            role=ConditionRole.BLOCKING,
        )
        cond.check_status = CheckStatus.FAIL
        cond.evidence_summary = EvidenceSummary(
            command="pytest",
            cwd="/tmp",
            exit_code=1,
            duration_ms=1000,
            output_tail="FAILED",
            timestamp=datetime.now(UTC),
        )
        task_with_plan.conditions = [cond]

        failed = execute_delivery._get_failed_conditions_with_evidence(task_with_plan)

        assert failed[0][1] is not None
        assert failed[0][1].exit_code == 1


class TestBuildRetryPrompt:
    @pytest.fixture
    def previous_iteration(self):
        return Iteration(
            number=1,
            goal="First attempt",
            changes=["file.py", "test.py"],
            check_results={},
            decision=IterationDecision.CONTINUE,
            decision_reason="Checks failed",
            timestamp=datetime.now(UTC),
        )

    def test_includes_task_description(self, execute_delivery, task_with_plan, previous_iteration):
        """_build_retry_prompt should include task description."""
        prompt = execute_delivery._build_retry_prompt(task_with_plan, previous_iteration, [])

        assert "Test task" in prompt

    def test_includes_files_changed(self, execute_delivery, task_with_plan, previous_iteration):
        """_build_retry_prompt should include files changed."""
        prompt = execute_delivery._build_retry_prompt(task_with_plan, previous_iteration, [])

        assert "file.py" in prompt
        assert "test.py" in prompt

    def test_includes_failed_conditions(self, execute_delivery, task_with_plan, previous_iteration):
        """_build_retry_prompt should include failed conditions."""
        cond = Condition(
            id=uuid4(),
            description="Tests must pass",
            role=ConditionRole.BLOCKING,
        )
        cond.check_status = CheckStatus.FAIL
        evidence = EvidenceSummary(
            command="pytest",
            cwd="/tmp",
            exit_code=1,
            duration_ms=1000,
            output_tail="AssertionError: expected True",
            timestamp=datetime.now(UTC),
        )

        prompt = execute_delivery._build_retry_prompt(
            task_with_plan, previous_iteration, [(cond, evidence)]
        )

        assert "Tests must pass" in prompt
        assert "Exit code: 1" in prompt
        assert "AssertionError" in prompt

    def test_handles_condition_without_evidence(
        self, execute_delivery, task_with_plan, previous_iteration
    ):
        """_build_retry_prompt should handle condition without evidence."""
        cond = Condition(
            id=uuid4(),
            description="Manual check",
            role=ConditionRole.BLOCKING,
        )
        cond.check_status = CheckStatus.FAIL

        prompt = execute_delivery._build_retry_prompt(
            task_with_plan, previous_iteration, [(cond, None)]
        )

        assert "Manual check" in prompt
        assert "No evidence available" in prompt

    def test_handles_no_changes(self, execute_delivery, task_with_plan):
        """_build_retry_prompt should handle iteration with no changes."""
        iteration = Iteration(
            number=1,
            goal="First attempt",
            changes=[],
            check_results={},
            decision=IterationDecision.CONTINUE,
            decision_reason="Nothing happened",
            timestamp=datetime.now(UTC),
        )

        prompt = execute_delivery._build_retry_prompt(task_with_plan, iteration, [])

        assert "none" in prompt.lower()
