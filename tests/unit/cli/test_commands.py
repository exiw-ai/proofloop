"""Tests for CLI commands."""

from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domain.entities.budget import Budget
from src.domain.entities.task import Task


class TestListTasks:
    """Tests for list_tasks command."""

    @pytest.mark.asyncio
    async def test_list_tasks_empty(self, tmp_path: Path) -> None:
        """Test listing tasks when none exist."""
        from src.cli.commands.list_tasks import _list_tasks

        with (
            patch("src.cli.commands.list_tasks.get_default_state_dir") as mock_state_dir,
            patch("src.cli.commands.list_tasks.JsonTaskRepo") as mock_repo_class,
            patch("src.cli.commands.list_tasks.console") as mock_console,
        ):
            mock_state_dir.return_value = tmp_path
            mock_repo = AsyncMock()
            mock_repo.list_tasks.return_value = []
            mock_repo_class.return_value = mock_repo

            await _list_tasks(None)

            mock_console.print.assert_called_once()
            call_args = str(mock_console.print.call_args)
            assert "No tasks found" in call_args

    @pytest.mark.asyncio
    async def test_list_tasks_with_tasks(self, tmp_path: Path) -> None:
        """Test listing tasks when tasks exist."""
        from src.cli.commands.list_tasks import _list_tasks

        task_id = uuid4()
        task = Task(
            id=task_id,
            description="Test task",
            goals=["Goal 1"],
            sources=["/tmp/test"],
            budget=Budget(max_iterations=10),
        )

        with (
            patch("src.cli.commands.list_tasks.get_default_state_dir") as mock_state_dir,
            patch("src.cli.commands.list_tasks.JsonTaskRepo") as mock_repo_class,
            patch("src.cli.commands.list_tasks.console") as mock_console,
        ):
            mock_state_dir.return_value = tmp_path
            mock_repo = AsyncMock()
            mock_repo.list_tasks.return_value = [task_id]
            mock_repo.load.return_value = task
            mock_repo_class.return_value = mock_repo

            await _list_tasks(None)

            mock_console.print.assert_called_once()


class TestTaskStatus:
    """Tests for task_status command."""

    @pytest.mark.asyncio
    async def test_status_not_found(self, tmp_path: Path) -> None:
        """Test status when task not found."""
        import typer

        from src.cli.commands.status import _show_status

        task_id = uuid4()

        with (
            patch("src.cli.commands.status.get_default_state_dir") as mock_state_dir,
            patch("src.cli.commands.status.JsonTaskRepo") as mock_repo_class,
            patch("src.cli.commands.status.console"),
            pytest.raises(typer.Exit),
        ):
            mock_state_dir.return_value = tmp_path
            mock_repo = AsyncMock()
            mock_repo.list_tasks.return_value = [task_id]  # For resolve_task_id
            mock_repo.load.return_value = None
            mock_repo_class.return_value = mock_repo

            await _show_status(str(task_id), None)

    @pytest.mark.asyncio
    async def test_status_found(self, tmp_path: Path) -> None:
        """Test status when task exists."""
        from src.cli.commands.status import _show_status

        task_id = uuid4()
        task = Task(
            id=task_id,
            description="Test task",
            goals=["Goal 1"],
            sources=["/tmp/test"],
            budget=Budget(max_iterations=10),
        )

        with (
            patch("src.cli.commands.status.get_default_state_dir") as mock_state_dir,
            patch("src.cli.commands.status.JsonTaskRepo") as mock_repo_class,
            patch("src.cli.commands.status.console") as mock_console,
        ):
            mock_state_dir.return_value = tmp_path
            mock_repo = AsyncMock()
            mock_repo.list_tasks.return_value = [task_id]  # For resolve_task_id
            mock_repo.load.return_value = task
            mock_repo_class.return_value = mock_repo

            await _show_status(str(task_id), None)

            mock_console.print.assert_called_once()


class TestResumeCommand:
    """Tests for resume command."""

    def test_resume_calls_async(self, tmp_path: Path) -> None:
        """Test resume command calls async function."""
        from src.cli.commands.resume import resume_task

        with (
            patch("src.cli.commands.resume.validate_provider_setup"),
            patch("src.cli.commands.resume.asyncio.run") as mock_run,
        ):
            resume_task(
                task_id=str(uuid4()),
                state_dir=tmp_path,
                auto_approve=False,
                show_thoughts=True,
                provider="claude",
            )

            mock_run.assert_called_once()


class TestRunCommand:
    """Tests for run command."""

    def test_run_calls_async(self, tmp_path: Path) -> None:
        """Test run command calls async function."""
        from src.cli.commands.run import run_task

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with (
            patch("src.cli.commands.run.validate_provider_setup"),
            patch("src.cli.commands.run.asyncio.run") as mock_run,
        ):
            run_task(
                description="Test task",
                path=workspace,
                auto_approve=True,
                baseline=False,
                timeout=4.0,  # hours
                verbose=False,
                show_hints=True,
                state_dir=None,
                task_id=None,
                allow_mcp=False,
                mcp_server=[],
                provider="claude",
            )

            mock_run.assert_called_once()
