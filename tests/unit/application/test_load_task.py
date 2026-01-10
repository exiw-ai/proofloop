"""Tests for LoadTask use case."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.use_cases.load_task import LoadTask
from src.domain.entities import Task
from src.domain.value_objects import TaskStatus


@pytest.fixture
def mock_repo() -> AsyncMock:
    return AsyncMock()


class TestLoadTask:
    @pytest.mark.asyncio
    async def test_returns_task_when_exists(self, mock_repo: AsyncMock) -> None:
        task_id = uuid4()
        expected_task = Task(
            id=task_id,
            description="Test task",
            goals=[],
            sources=[],
            status=TaskStatus.PLANNING,
        )
        mock_repo.load.return_value = expected_task

        use_case = LoadTask(mock_repo)
        result = await use_case.execute(task_id)

        assert result is expected_task
        mock_repo.load.assert_called_once_with(task_id)

    @pytest.mark.asyncio
    async def test_returns_none_when_not_exists(self, mock_repo: AsyncMock) -> None:
        task_id = uuid4()
        mock_repo.load.return_value = None

        use_case = LoadTask(mock_repo)
        result = await use_case.execute(task_id)

        assert result is None
        mock_repo.load.assert_called_once_with(task_id)
