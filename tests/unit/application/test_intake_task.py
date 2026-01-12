"""Tests for IntakeTask use case."""

from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from src.application.dto.task_input import TaskInput
from src.application.use_cases.intake_task import IntakeTask
from src.domain.value_objects import TaskStatus


@pytest.fixture
def mock_repo() -> AsyncMock:
    repo = AsyncMock()
    return repo


@pytest.fixture
def task_input(tmp_path: Path) -> TaskInput:
    return TaskInput(
        description="Fix the bug",
        workspace_path=tmp_path,
        sources=["src/"],
        goals=["Goal 1"],
        constraints=["Constraint 1"],
        timeout_minutes=30,
        max_iterations=10,
    )


class TestIntakeTask:
    @pytest.mark.asyncio
    async def test_creates_task_with_correct_status(
        self, mock_repo: AsyncMock, task_input: TaskInput
    ) -> None:
        use_case = IntakeTask(mock_repo)
        task = await use_case.execute(task_input)

        assert task.status == TaskStatus.INTAKE

    @pytest.mark.asyncio
    async def test_creates_task_with_generated_id(
        self, mock_repo: AsyncMock, task_input: TaskInput
    ) -> None:
        use_case = IntakeTask(mock_repo)
        task = await use_case.execute(task_input)

        assert isinstance(task.id, UUID)

    @pytest.mark.asyncio
    async def test_creates_task_with_provided_id(
        self, mock_repo: AsyncMock, task_input: TaskInput
    ) -> None:
        expected_id = uuid4()
        use_case = IntakeTask(mock_repo)
        task = await use_case.execute(task_input, task_id=expected_id)

        assert task.id == expected_id

    @pytest.mark.asyncio
    async def test_preserves_input_fields(
        self, mock_repo: AsyncMock, task_input: TaskInput
    ) -> None:
        use_case = IntakeTask(mock_repo)
        task = await use_case.execute(task_input)

        assert task.description == "Fix the bug"
        assert task.goals == ["Goal 1"]
        assert task.sources == ["src/"]
        assert task.constraints == ["Constraint 1"]

    @pytest.mark.asyncio
    async def test_calculates_budget_from_input(
        self, mock_repo: AsyncMock, task_input: TaskInput
    ) -> None:
        use_case = IntakeTask(mock_repo)
        task = await use_case.execute(task_input)

        assert task.budget.wall_time_limit_s == 30 * 60
        assert task.budget.max_iterations == 10

    @pytest.mark.asyncio
    async def test_persists_task(self, mock_repo: AsyncMock, task_input: TaskInput) -> None:
        use_case = IntakeTask(mock_repo)
        task = await use_case.execute(task_input)

        mock_repo.save.assert_called_once_with(task)
