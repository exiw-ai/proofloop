"""Tests for CLI runner module."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.application.dto.final_result import FinalResult
from src.domain.entities.condition import Condition
from src.domain.entities.plan import Plan, PlanStep
from src.domain.value_objects.clarification import (
    ClarificationOption,
    ClarificationQuestion,
)
from src.domain.value_objects.condition_enums import ConditionRole
from src.domain.value_objects.task_status import TaskStatus


class TestInteractiveClarifications:
    """Tests for interactive_clarifications function."""

    def test_empty_questions_returns_empty(self) -> None:
        """Test that empty questions returns empty list."""
        from src.cli.runner import interactive_clarifications

        result = interactive_clarifications([])
        assert result == []

    def test_numeric_selection(self) -> None:
        """Test selecting option by number."""
        from src.cli.runner import interactive_clarifications

        question = ClarificationQuestion(
            id="q1",
            question="Which approach?",
            options=[
                ClarificationOption(key="a", label="Option A", description="Desc A"),
                ClarificationOption(key="b", label="Option B", description="Desc B"),
            ],
        )

        with patch("src.cli.runner.console") as mock_console:
            mock_console.input.return_value = "1"
            mock_console.print = MagicMock()

            result = interactive_clarifications([question])

            assert len(result) == 1
            assert result[0].question_id == "q1"
            assert result[0].selected_option == "a"

    def test_custom_selection(self) -> None:
        """Test entering custom answer."""
        from src.cli.runner import interactive_clarifications

        question = ClarificationQuestion(
            id="q1",
            question="Which approach?",
            options=[
                ClarificationOption(key="a", label="Option A", description="Desc A"),
            ],
        )

        with patch("src.cli.runner.console") as mock_console:
            mock_console.input.side_effect = ["c", "my custom answer"]
            mock_console.print = MagicMock()

            result = interactive_clarifications([question])

            assert len(result) == 1
            assert result[0].selected_option == "custom"
            assert result[0].custom_value == "my custom answer"

    def test_auto_selection(self) -> None:
        """Test auto selection."""
        from src.cli.runner import interactive_clarifications

        question = ClarificationQuestion(
            id="q1",
            question="Which approach?",
            options=[
                ClarificationOption(key="a", label="Option A", description="Desc A"),
            ],
        )

        with patch("src.cli.runner.console") as mock_console:
            mock_console.input.return_value = "auto"
            mock_console.print = MagicMock()

            result = interactive_clarifications([question])

            assert len(result) == 1
            assert result[0].selected_option == "_auto"

    def test_empty_enter_defaults_to_auto(self) -> None:
        """Test that empty Enter defaults to auto."""
        from src.cli.runner import interactive_clarifications

        question = ClarificationQuestion(
            id="q1",
            question="Which approach?",
            options=[
                ClarificationOption(key="a", label="Option A", description="Desc A"),
            ],
        )

        with patch("src.cli.runner.console") as mock_console:
            mock_console.input.return_value = ""
            mock_console.print = MagicMock()

            result = interactive_clarifications([question])

            assert result[0].selected_option == "_auto"

    def test_key_matching(self) -> None:
        """Test selecting option by key."""
        from src.cli.runner import interactive_clarifications

        question = ClarificationQuestion(
            id="q1",
            question="Which approach?",
            options=[
                ClarificationOption(key="opt_a", label="Option A", description="Desc A"),
                ClarificationOption(key="opt_b", label="Option B", description="Desc B"),
            ],
        )

        with patch("src.cli.runner.console") as mock_console:
            mock_console.input.return_value = "opt_b"
            mock_console.print = MagicMock()

            result = interactive_clarifications([question])

            assert result[0].selected_option == "opt_b"


class TestInteractiveConditionsEditor:
    """Tests for interactive_conditions_editor function."""

    def test_done_without_changes(self) -> None:
        """Test pressing done without any changes."""
        from src.cli.runner import interactive_conditions_editor

        conditions = [
            Condition(
                id=uuid4(),
                description="Test condition",
                role=ConditionRole.BLOCKING,
            )
        ]

        with patch("src.cli.runner.console") as mock_console:
            mock_console.input.return_value = "done"
            mock_console.print = MagicMock()

            result = interactive_conditions_editor(conditions)

            assert len(result) == 1
            assert result[0].description == "Test condition"

    def test_add_condition(self) -> None:
        """Test adding a new condition."""
        from src.cli.runner import interactive_conditions_editor

        conditions: list[Condition] = []

        with patch("src.cli.runner.console") as mock_console:
            mock_console.input.side_effect = ["a", "New condition", "1", "done"]
            mock_console.print = MagicMock()

            result = interactive_conditions_editor(conditions)

            assert len(result) == 1
            assert result[0].description == "New condition"
            assert result[0].role == ConditionRole.BLOCKING

    def test_add_signal_condition(self) -> None:
        """Test adding a signal condition."""
        from src.cli.runner import interactive_conditions_editor

        conditions: list[Condition] = []

        with patch("src.cli.runner.console") as mock_console:
            mock_console.input.side_effect = ["a", "Signal condition", "2", "done"]
            mock_console.print = MagicMock()

            result = interactive_conditions_editor(conditions)

            assert len(result) == 1
            assert result[0].role == ConditionRole.SIGNAL

    def test_delete_condition(self) -> None:
        """Test deleting a condition."""
        from src.cli.runner import interactive_conditions_editor

        conditions = [
            Condition(id=uuid4(), description="Cond 1", role=ConditionRole.BLOCKING),
            Condition(id=uuid4(), description="Cond 2", role=ConditionRole.BLOCKING),
        ]

        with patch("src.cli.runner.console") as mock_console:
            mock_console.input.side_effect = ["d 1", "done"]
            mock_console.print = MagicMock()

            result = interactive_conditions_editor(conditions)

            assert len(result) == 1
            assert result[0].description == "Cond 2"

    def test_edit_condition(self) -> None:
        """Test editing a condition."""
        from src.cli.runner import interactive_conditions_editor

        conditions = [
            Condition(id=uuid4(), description="Old description", role=ConditionRole.BLOCKING),
        ]

        with patch("src.cli.runner.console") as mock_console:
            mock_console.input.side_effect = ["e 1", "New description", "done"]
            mock_console.print = MagicMock()

            result = interactive_conditions_editor(conditions)

            assert result[0].description == "New description"

    def test_toggle_role(self) -> None:
        """Test toggling condition role."""
        from src.cli.runner import interactive_conditions_editor

        conditions = [
            Condition(id=uuid4(), description="Test", role=ConditionRole.BLOCKING),
        ]

        with patch("src.cli.runner.console") as mock_console:
            mock_console.input.side_effect = ["t 1", "done"]
            mock_console.print = MagicMock()

            result = interactive_conditions_editor(conditions)

            assert result[0].role == ConditionRole.SIGNAL

    def test_cyrillic_normalization(self) -> None:
        """Test that Cyrillic lookalikes are normalized."""
        from src.cli.runner import interactive_conditions_editor

        conditions: list[Condition] = []

        with patch("src.cli.runner.console") as mock_console:
            # Using Cyrillic 'а' instead of Latin 'a'
            mock_console.input.side_effect = ["а", "Test", "1", "done"]
            mock_console.print = MagicMock()

            result = interactive_conditions_editor(conditions)

            assert len(result) == 1


class TestInteractivePlanAndConditionsReview:
    """Tests for interactive_plan_and_conditions_review function."""

    def test_approve_with_y(self) -> None:
        """Test approving with 'y'."""
        from src.cli.runner import interactive_plan_and_conditions_review

        plan = Plan(
            goal="Test goal", boundaries=[], steps=[PlanStep(number=1, description="Step 1")]
        )
        conditions = [Condition(id=uuid4(), description="Test", role=ConditionRole.BLOCKING)]

        with (
            patch("src.cli.runner.console") as mock_console,
            patch("src.cli.runner.format_plan"),
            patch("src.cli.runner.format_conditions"),
        ):
            mock_console.input.return_value = "y"
            mock_console.print = MagicMock()

            approved, feedback, result_conditions = interactive_plan_and_conditions_review(
                plan, conditions
            )

            assert approved is True
            assert feedback is None
            assert result_conditions == conditions

    def test_reject_with_n(self) -> None:
        """Test rejecting with 'n'."""
        from src.cli.runner import interactive_plan_and_conditions_review

        plan = Plan(
            goal="Test goal", boundaries=[], steps=[PlanStep(number=1, description="Step 1")]
        )
        conditions: list[Condition] = []

        with (
            patch("src.cli.runner.console") as mock_console,
            patch("src.cli.runner.format_plan"),
            patch("src.cli.runner.format_conditions"),
        ):
            mock_console.input.return_value = "n"
            mock_console.print = MagicMock()

            approved, feedback, result_conditions = interactive_plan_and_conditions_review(
                plan, conditions
            )

            assert approved is False
            assert feedback is None

    def test_feedback_with_f(self) -> None:
        """Test providing feedback with 'f'."""
        from src.cli.runner import interactive_plan_and_conditions_review

        plan = Plan(
            goal="Test goal", boundaries=[], steps=[PlanStep(number=1, description="Step 1")]
        )
        conditions: list[Condition] = []

        with (
            patch("src.cli.runner.console") as mock_console,
            patch("src.cli.runner.format_plan"),
            patch("src.cli.runner.format_conditions"),
        ):
            mock_console.input.side_effect = ["f", "Please add tests", ""]
            mock_console.print = MagicMock()

            approved, feedback, result_conditions = interactive_plan_and_conditions_review(
                plan, conditions
            )

            assert approved is False
            assert feedback == "Please add tests"


class TestInteractivePlanApproval:
    """Tests for interactive_plan_approval function."""

    def test_approve_with_y(self) -> None:
        """Test approving with 'y'."""
        from src.cli.runner import interactive_plan_approval

        plan = Plan(
            goal="Test goal", boundaries=[], steps=[PlanStep(number=1, description="Step 1")]
        )

        with (
            patch("src.cli.runner.console") as mock_console,
            patch("src.cli.runner.format_plan"),
        ):
            mock_console.input.return_value = "y"
            mock_console.print = MagicMock()

            approved, feedback = interactive_plan_approval(plan)

            assert approved is True
            assert feedback is None

    def test_approve_with_empty_enter(self) -> None:
        """Test approving with empty Enter."""
        from src.cli.runner import interactive_plan_approval

        plan = Plan(
            goal="Test goal", boundaries=[], steps=[PlanStep(number=1, description="Step 1")]
        )

        with (
            patch("src.cli.runner.console") as mock_console,
            patch("src.cli.runner.format_plan"),
        ):
            mock_console.input.return_value = ""
            mock_console.print = MagicMock()

            approved, feedback = interactive_plan_approval(plan)

            assert approved is True


class TestRunTaskAsync:
    """Tests for run_task_async function."""

    @pytest.mark.asyncio
    async def test_run_task_async_success(self, tmp_path: Path) -> None:
        """Test successful task run."""
        from src.cli.runner import run_task_async

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state_dir = tmp_path / ".proofloop"
        state_dir.mkdir()

        final_result = FinalResult(
            task_id=uuid4(),
            status=TaskStatus.DONE,
            diff="",
            patch="",
            summary="Done",
            conditions=[],
            evidence_refs=[],
        )

        with (
            patch("src.cli.runner.get_default_state_dir") as mock_state_dir,
            patch("src.cli.runner.create_agent"),
            patch("src.cli.runner.CommandCheckRunner"),
            patch("src.cli.runner.GitDiffAdapter"),
            patch("src.cli.runner.JsonTaskRepo"),
            patch("src.cli.runner.ProjectAnalyzer"),
            patch("src.cli.runner.get_default_registry"),
            patch("src.cli.runner.Orchestrator") as mock_orchestrator_class,
            patch("src.cli.runner.format_result") as mock_format,
        ):
            mock_state_dir.return_value = state_dir
            mock_orchestrator = AsyncMock()
            mock_orchestrator.run.return_value = final_result
            mock_orchestrator_class.return_value = mock_orchestrator

            await run_task_async(
                description="Fix the bug",
                path=workspace,
                auto_approve=True,
                baseline=False,
                timeout=60,
                state_dir=state_dir,
            )

            mock_orchestrator.run.assert_called_once()
            mock_format.assert_called_once()


class TestResumeTaskAsync:
    """Tests for resume_task_async function."""

    @pytest.mark.asyncio
    async def test_resume_task_not_found(self, tmp_path: Path) -> None:
        """Test resuming non-existent task."""
        import typer

        from src.cli.runner import resume_task_async

        state_dir = tmp_path / ".proofloop"
        state_dir.mkdir()

        with (
            patch("src.cli.runner.create_agent"),
            patch("src.cli.runner.CommandCheckRunner"),
            patch("src.cli.runner.GitDiffAdapter"),
            patch("src.cli.runner.JsonTaskRepo") as mock_repo_class,
            patch("src.cli.runner.ProjectAnalyzer"),
            pytest.raises(typer.Exit),
        ):
            mock_repo = AsyncMock()
            mock_repo.load.return_value = None
            mock_repo_class.return_value = mock_repo

            await resume_task_async(uuid4(), state_dir)


class TestRunResearchAsync:
    """Tests for run_research_async function."""

    @pytest.mark.asyncio
    async def test_run_research_async_success(self, tmp_path: Path) -> None:
        """Test successful research run."""
        from src.cli.runner import run_research_async
        from src.domain.entities.research_result import ResearchResult

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state_dir = tmp_path / ".proofloop"
        state_dir.mkdir()

        research_result = ResearchResult(
            task_id=uuid4(),
            status=TaskStatus.DONE,
            report_pack_path=str(tmp_path / "reports"),
            handoff_payload_path=str(tmp_path / "derive_payload.json"),
            iterations_count=3,
            metrics={"sources_count": 5, "findings_count": 10, "coverage_score": 0.8},
        )

        with (
            patch("src.cli.runner.get_default_state_dir") as mock_state_dir,
            patch("src.cli.runner.create_agent"),
            patch("src.cli.runner.CommandCheckRunner"),
            patch("src.cli.runner.GitDiffAdapter"),
            patch("src.cli.runner.JsonTaskRepo"),
            patch("src.cli.runner.ProjectAnalyzer"),
            patch("src.cli.runner.Orchestrator") as mock_orchestrator_class,
            patch("src.cli.runner.console") as mock_console,
        ):
            mock_state_dir.return_value = state_dir
            mock_orchestrator = AsyncMock()
            mock_orchestrator.run_research.return_value = research_result
            mock_orchestrator_class.return_value = mock_orchestrator
            mock_console.print = MagicMock()

            await run_research_async(
                description="Research AI trends",
                path=workspace,
                preset="minimal",
                research_type="general",
                repo_context="off",
                template="general_default",
                auto_approve=True,
                verbose=False,
                state_dir=state_dir,
            )

            mock_orchestrator.run_research.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_research_async_invalid_preset(self, tmp_path: Path) -> None:
        """Test research with invalid preset."""
        import typer

        from src.cli.runner import run_research_async

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state_dir = tmp_path / ".proofloop"
        state_dir.mkdir()

        with (
            patch("src.cli.runner.get_default_state_dir") as mock_state_dir,
            patch("src.cli.runner.create_agent"),
            patch("src.cli.runner.CommandCheckRunner"),
            patch("src.cli.runner.GitDiffAdapter"),
            patch("src.cli.runner.JsonTaskRepo"),
            patch("src.cli.runner.ProjectAnalyzer"),
            patch("src.cli.runner.console") as mock_console,
            pytest.raises(typer.Exit),
        ):
            mock_state_dir.return_value = state_dir
            mock_console.print = MagicMock()

            await run_research_async(
                description="Test",
                path=workspace,
                preset="invalid_preset",  # Invalid
                research_type="general",
                repo_context="off",
                template="general_default",
                auto_approve=True,
                state_dir=state_dir,
            )

    @pytest.mark.asyncio
    async def test_run_research_async_invalid_research_type(self, tmp_path: Path) -> None:
        """Test research with invalid research type."""
        import typer

        from src.cli.runner import run_research_async

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state_dir = tmp_path / ".proofloop"
        state_dir.mkdir()

        with (
            patch("src.cli.runner.get_default_state_dir") as mock_state_dir,
            patch("src.cli.runner.create_agent"),
            patch("src.cli.runner.CommandCheckRunner"),
            patch("src.cli.runner.GitDiffAdapter"),
            patch("src.cli.runner.JsonTaskRepo"),
            patch("src.cli.runner.ProjectAnalyzer"),
            patch("src.cli.runner.console") as mock_console,
            pytest.raises(typer.Exit),
        ):
            mock_state_dir.return_value = state_dir
            mock_console.print = MagicMock()

            await run_research_async(
                description="Test",
                path=workspace,
                preset="minimal",
                research_type="invalid_type",  # Invalid
                repo_context="off",
                template="general_default",
                auto_approve=True,
                state_dir=state_dir,
            )

    @pytest.mark.asyncio
    async def test_run_research_async_invalid_template(self, tmp_path: Path) -> None:
        """Test research with invalid template."""
        import typer

        from src.cli.runner import run_research_async

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state_dir = tmp_path / ".proofloop"
        state_dir.mkdir()

        with (
            patch("src.cli.runner.get_default_state_dir") as mock_state_dir,
            patch("src.cli.runner.create_agent"),
            patch("src.cli.runner.CommandCheckRunner"),
            patch("src.cli.runner.GitDiffAdapter"),
            patch("src.cli.runner.JsonTaskRepo"),
            patch("src.cli.runner.ProjectAnalyzer"),
            patch("src.cli.runner.console") as mock_console,
            pytest.raises(typer.Exit),
        ):
            mock_state_dir.return_value = state_dir
            mock_console.print = MagicMock()

            await run_research_async(
                description="Test",
                path=workspace,
                preset="minimal",
                research_type="general",
                repo_context="off",
                template="invalid_template",  # Invalid
                auto_approve=True,
                state_dir=state_dir,
            )

    @pytest.mark.asyncio
    async def test_run_research_async_displays_result(self, tmp_path: Path) -> None:
        """Test that research results are displayed."""
        from src.cli.runner import run_research_async
        from src.domain.entities.research_result import ResearchResult

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state_dir = tmp_path / ".proofloop"
        state_dir.mkdir()

        research_result = ResearchResult(
            task_id=uuid4(),
            status=TaskStatus.DONE,
            report_pack_path=str(tmp_path / "reports"),
            handoff_payload_path=str(tmp_path / "derive_payload.json"),
            iterations_count=2,
            metrics={"sources_count": 3, "findings_count": 5, "coverage_score": 0.7},
            conditions_failed=["Coverage below 80%"],
        )

        with (
            patch("src.cli.runner.get_default_state_dir") as mock_state_dir,
            patch("src.cli.runner.create_agent"),
            patch("src.cli.runner.CommandCheckRunner"),
            patch("src.cli.runner.GitDiffAdapter"),
            patch("src.cli.runner.JsonTaskRepo"),
            patch("src.cli.runner.ProjectAnalyzer"),
            patch("src.cli.runner.Orchestrator") as mock_orchestrator_class,
            patch("src.cli.runner.console") as mock_console,
        ):
            mock_state_dir.return_value = state_dir
            mock_orchestrator = AsyncMock()
            mock_orchestrator.run_research.return_value = research_result
            mock_orchestrator_class.return_value = mock_orchestrator
            mock_console.print = MagicMock()

            await run_research_async(
                description="Research",
                path=workspace,
                preset="minimal",
                research_type="general",
                repo_context="off",
                template="general_default",
                auto_approve=True,
                state_dir=state_dir,
            )

            # Verify console.print was called multiple times
            assert mock_console.print.call_count > 5


class TestResumeTaskAsyncSuccess:
    """Additional tests for resume_task_async success cases."""

    @pytest.mark.asyncio
    async def test_resume_task_async_success(self, tmp_path: Path) -> None:
        """Test resuming an existing task."""
        from src.cli.runner import resume_task_async
        from src.domain.entities.budget import Budget
        from src.domain.entities.task import Task

        state_dir = tmp_path / ".proofloop"
        state_dir.mkdir()

        task_id = uuid4()
        task = Task(
            id=task_id,
            description="Existing task",
            goals=["Goal"],
            sources=[str(tmp_path)],
            budget=Budget(max_iterations=10),
        )
        task.status = TaskStatus.EXECUTING

        final_result = FinalResult(
            task_id=task_id,
            status=TaskStatus.DONE,
            diff="",
            patch="",
            summary="Resumed and completed",
            conditions=[],
            evidence_refs=[],
        )

        with (
            patch("src.cli.runner.create_agent"),
            patch("src.cli.runner.CommandCheckRunner"),
            patch("src.cli.runner.GitDiffAdapter"),
            patch("src.cli.runner.JsonTaskRepo") as mock_repo_class,
            patch("src.cli.runner.ProjectAnalyzer"),
            patch("src.cli.runner.Orchestrator") as mock_orchestrator_class,
            patch("src.cli.runner.format_result") as mock_format,
            patch("src.cli.runner.console") as mock_console,
        ):
            mock_repo = AsyncMock()
            mock_repo.load.return_value = task
            mock_repo_class.return_value = mock_repo

            mock_orchestrator = AsyncMock()
            mock_orchestrator.resume.return_value = final_result
            mock_orchestrator_class.return_value = mock_orchestrator

            mock_console.print = MagicMock()

            await resume_task_async(task_id, state_dir)

            mock_orchestrator.resume.assert_called_once()
            mock_format.assert_called_once()
