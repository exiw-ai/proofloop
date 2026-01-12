"""Unit tests for application use cases."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.application.use_cases.approve_conditions import ApproveConditions
from src.application.use_cases.approve_plan import ApprovePlan
from src.domain.entities.condition import Condition
from src.domain.entities.plan import Plan, PlanStep
from src.domain.entities.task import Task
from src.domain.value_objects.condition_enums import ApprovalStatus, ConditionRole
from src.domain.value_objects.task_status import TaskStatus


class TestApproveConditions:
    @pytest.fixture
    def mock_task_repo(self) -> MagicMock:
        repo = MagicMock()
        repo.save = AsyncMock()
        repo.save_conditions_approval = AsyncMock()
        return repo

    @pytest.fixture
    def task_with_conditions(self) -> Task:
        task = Task(
            id=uuid4(),
            description="Test task",
            goals=["Goal"],
            sources=["."],
        )
        # Add blocking condition with check_id
        blocking = Condition(
            id=uuid4(),
            description="Tests pass",
            role=ConditionRole.BLOCKING,
            check_id=uuid4(),
        )
        # Add signal condition without check_id
        signal = Condition(
            id=uuid4(),
            description="Coverage",
            role=ConditionRole.SIGNAL,
        )
        task.conditions = [blocking, signal]
        return task

    async def test_auto_approve_approves_all_conditions(
        self, mock_task_repo: MagicMock, task_with_conditions: Task
    ) -> None:
        use_case = ApproveConditions(mock_task_repo)

        result = await use_case.execute(task_with_conditions, auto_approve=True)

        assert result is True
        assert task_with_conditions.status == TaskStatus.APPROVAL_CONDITIONS
        for cond in task_with_conditions.conditions:
            assert cond.approval_status == ApprovalStatus.APPROVED
        mock_task_repo.save_conditions_approval.assert_called_once()
        mock_task_repo.save.assert_called_once()

    async def test_no_auto_approve_returns_false(
        self, mock_task_repo: MagicMock, task_with_conditions: Task
    ) -> None:
        use_case = ApproveConditions(mock_task_repo)

        result = await use_case.execute(task_with_conditions, auto_approve=False)

        assert result is False
        # Status should not change
        assert task_with_conditions.status == TaskStatus.INTAKE
        mock_task_repo.save.assert_not_called()

    async def test_blocking_condition_without_check_id_can_be_approved(
        self, mock_task_repo: MagicMock
    ) -> None:
        """Manual blocking conditions can be approved - verified by agent during delivery."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=[],
            sources=["."],
        )
        # Blocking without check_id - will be verified by agent later
        task.conditions = [
            Condition(
                id=uuid4(),
                description="Manual check",
                role=ConditionRole.BLOCKING,
                check_id=None,
            )
        ]

        use_case = ApproveConditions(mock_task_repo)
        result = await use_case.execute(task, auto_approve=True)

        # Should return True (process continues)
        assert result is True
        # Condition should be approved (will be verified by agent later)
        assert task.conditions[0].approval_status == ApprovalStatus.APPROVED


class TestApprovePlan:
    @pytest.fixture
    def mock_task_repo(self) -> MagicMock:
        repo = MagicMock()
        repo.save = AsyncMock()
        repo.save_plan_approval = AsyncMock()
        return repo

    @pytest.fixture
    def task_with_plan(self) -> Task:
        task = Task(
            id=uuid4(),
            description="Test task",
            goals=["Goal"],
            sources=["."],
        )
        task.plan = Plan(
            goal="Implement feature",
            boundaries=["No breaking changes"],
            steps=[
                PlanStep(number=1, description="Step 1"),
            ],
        )
        return task

    async def test_auto_approve_approves_plan(
        self, mock_task_repo: MagicMock, task_with_plan: Task
    ) -> None:
        use_case = ApprovePlan(mock_task_repo)

        result = await use_case.execute(task_with_plan, auto_approve=True)

        assert result is True
        assert task_with_plan.plan is not None
        assert task_with_plan.plan.approved is True
        assert task_with_plan.status == TaskStatus.APPROVAL_PLAN
        mock_task_repo.save_plan_approval.assert_called_once()
        mock_task_repo.save.assert_called_once()

    async def test_no_auto_approve_returns_false(
        self, mock_task_repo: MagicMock, task_with_plan: Task
    ) -> None:
        use_case = ApprovePlan(mock_task_repo)

        result = await use_case.execute(task_with_plan, auto_approve=False)

        assert result is False
        assert task_with_plan.plan is not None
        assert task_with_plan.plan.approved is False
        mock_task_repo.save.assert_not_called()

    async def test_no_plan_returns_false(self, mock_task_repo: MagicMock) -> None:
        task = Task(
            id=uuid4(),
            description="Test",
            goals=[],
            sources=["."],
            plan=None,
        )

        use_case = ApprovePlan(mock_task_repo)
        result = await use_case.execute(task, auto_approve=True)

        assert result is False
        mock_task_repo.save.assert_not_called()
