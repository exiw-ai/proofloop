"""Comprehensive unit tests for application use cases."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.application.use_cases.build_verification_inventory import BuildVerificationInventory
from src.application.use_cases.create_plan import CreatePlan
from src.application.use_cases.define_conditions import DefineConditions
from src.application.use_cases.finalize_task import FinalizeTask
from src.application.use_cases.run_quality_loop import RunQualityLoop
from src.application.use_cases.select_strategy import SelectStrategy
from src.domain.entities.budget import Budget
from src.domain.entities.condition import Condition
from src.domain.entities.plan import Plan, PlanStep
from src.domain.entities.task import Task
from src.domain.entities.verification_inventory import VerificationInventory
from src.domain.ports.agent_port import AgentResult
from src.domain.ports.diff_port import DiffResult
from src.domain.value_objects.check_types import CheckKind, CheckSpec
from src.domain.value_objects.clarification import ClarificationAnswer
from src.domain.value_objects.condition_enums import CheckStatus, ConditionRole
from src.domain.value_objects.evidence_types import EvidenceRef
from src.domain.value_objects.task_status import TaskStatus

# ===== CreatePlan Tests =====


class TestCreatePlanAskClarifications:
    @pytest.fixture
    def mock_agent(self):
        agent = AsyncMock()
        # Wrap JSON in markdown code block for extract_json to parse correctly
        agent.execute.return_value = AgentResult(
            messages=[],
            final_response="""```json
[
    {
        "id": "q1",
        "question": "Which database?",
        "context": "Need to choose database",
        "options": [
            {"key": "postgres", "label": "PostgreSQL", "description": "Relational DB"},
            {"key": "mongo", "label": "MongoDB", "description": "NoSQL DB"}
        ]
    }
]
```""",
            tools_used=["Read"],
        )
        return agent

    @pytest.fixture
    def mock_task_repo(self):
        return AsyncMock()

    @pytest.fixture
    def task(self, tmp_path):
        task = Task(
            id=uuid4(),
            description="Build a new feature",
            goals=["Goal 1"],
            sources=[str(tmp_path)],
        )
        task.verification_inventory = VerificationInventory(
            checks=[],
            baseline=None,
            project_structure={"frameworks": ["FastAPI"]},
            conventions=["Use pytest"],
        )
        return task

    @pytest.mark.asyncio
    async def test_ask_clarifications_returns_questions(self, mock_agent, mock_task_repo, task):
        """ask_clarifications should return parsed questions."""
        use_case = CreatePlan(mock_agent, mock_task_repo)

        questions = await use_case.ask_clarifications(task)

        assert len(questions) == 1
        assert questions[0].id == "q1"
        assert questions[0].question == "Which database?"
        assert len(questions[0].options) == 3  # 2 + "decide for me"

    @pytest.mark.asyncio
    async def test_ask_clarifications_handles_invalid_json(self, mock_agent, mock_task_repo, task):
        """ask_clarifications should handle invalid JSON gracefully."""
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="Not valid JSON",
            tools_used=[],
        )
        use_case = CreatePlan(mock_agent, mock_task_repo)

        questions = await use_case.ask_clarifications(task)

        assert questions == []

    @pytest.mark.asyncio
    async def test_ask_clarifications_without_inventory(self, mock_agent, mock_task_repo, tmp_path):
        """ask_clarifications should work without verification inventory."""
        task = Task(
            id=uuid4(),
            description="Build feature",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="[]",
            tools_used=[],
        )
        use_case = CreatePlan(mock_agent, mock_task_repo)

        questions = await use_case.ask_clarifications(task)

        assert questions == []

    @pytest.mark.asyncio
    async def test_ask_clarifications_with_callback(self, mock_agent, mock_task_repo, task):
        """ask_clarifications should pass callback to agent."""
        callback = MagicMock()
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="[]",
            tools_used=[],
        )
        use_case = CreatePlan(mock_agent, mock_task_repo)

        await use_case.ask_clarifications(task, on_message=callback)

        mock_agent.execute.assert_called_once()
        assert mock_agent.execute.call_args.kwargs["on_message"] == callback


class TestCreatePlanExecute:
    @pytest.fixture
    def mock_agent(self):
        agent = AsyncMock()
        agent.execute.return_value = AgentResult(
            messages=[],
            final_response=json.dumps(
                {
                    "goal": "Implement feature",
                    "boundaries": ["No breaking changes"],
                    "steps": [
                        {"number": 1, "description": "Step 1", "target_files": ["file.py"]},
                        {"number": 2, "description": "Step 2", "target_files": ["test.py"]},
                    ],
                    "risks": ["May break tests"],
                    "assumptions": ["FastAPI is installed"],
                    "replan_conditions": ["If tests fail"],
                }
            ),
            tools_used=["Read", "Grep"],
        )
        return agent

    @pytest.fixture
    def mock_task_repo(self):
        return AsyncMock()

    @pytest.fixture
    def task(self, tmp_path):
        return Task(
            id=uuid4(),
            description="Build feature",
            goals=["Goal 1"],
            sources=[str(tmp_path)],
        )

    @pytest.mark.asyncio
    async def test_execute_creates_plan(self, mock_agent, mock_task_repo, task):
        """Execute should create a plan from agent response."""
        use_case = CreatePlan(mock_agent, mock_task_repo)

        plan = await use_case.execute(task)

        assert plan.goal == "Implement feature"
        assert len(plan.steps) == 2
        assert plan.boundaries == ["No breaking changes"]
        assert task.status == TaskStatus.PLANNING
        mock_task_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_clarifications(self, mock_agent, mock_task_repo, task):
        """Execute should include clarification answers in prompt."""
        clarifications = [
            ClarificationAnswer(question_id="q1", selected_option="postgres"),
            ClarificationAnswer(question_id="q2", selected_option="_auto"),
            ClarificationAnswer(
                question_id="q3", selected_option="custom", custom_value="Custom answer"
            ),
        ]
        use_case = CreatePlan(mock_agent, mock_task_repo)

        await use_case.execute(task, clarifications=clarifications)

        call_args = mock_agent.execute.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "postgres" in prompt
        assert "best practices" in prompt  # _auto option
        assert "Custom answer" in prompt

    @pytest.mark.asyncio
    async def test_execute_with_verification_inventory(self, mock_agent, mock_task_repo, task):
        """Execute should include project context in prompt."""
        task.verification_inventory = VerificationInventory(
            checks=[],
            baseline=None,
            project_structure={
                "root_files": ["README.md", "pyproject.toml"],
                "src_dirs": ["src"],
                "test_dirs": ["tests"],
                "frameworks": ["FastAPI", "pytest"],
            },
            conventions=["Use type hints"],
        )
        use_case = CreatePlan(mock_agent, mock_task_repo)

        await use_case.execute(task)

        call_args = mock_agent.execute.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "Root files" in prompt
        assert "FastAPI" in prompt
        assert "Use type hints" in prompt


class TestCreatePlanRefine:
    @pytest.fixture
    def mock_agent(self):
        agent = AsyncMock()
        agent.execute.return_value = AgentResult(
            messages=[],
            final_response=json.dumps(
                {
                    "goal": "Refined goal",
                    "boundaries": [],
                    "steps": [{"number": 1, "description": "Refined step"}],
                    "risks": [],
                    "assumptions": [],
                    "replan_conditions": [],
                }
            ),
            tools_used=["Read"],
        )
        return agent

    @pytest.fixture
    def mock_task_repo(self):
        return AsyncMock()

    @pytest.fixture
    def task_with_plan(self, tmp_path):
        task = Task(
            id=uuid4(),
            description="Build feature",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )
        task.plan = Plan(
            goal="Original goal",
            boundaries=[],
            steps=[PlanStep(number=1, description="Original step")],
        )
        return task

    @pytest.mark.asyncio
    async def test_refine_updates_plan(self, mock_agent, mock_task_repo, task_with_plan):
        """Refine should update the plan based on feedback."""
        use_case = CreatePlan(mock_agent, mock_task_repo)

        plan = await use_case.refine(task_with_plan, "Add more detail")

        assert plan.goal == "Refined goal"
        assert plan.version == 2  # Version incremented
        mock_task_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_refine_without_existing_plan(self, mock_agent, mock_task_repo, tmp_path):
        """Refine should create new plan if none exists."""
        task = Task(
            id=uuid4(),
            description="Build feature",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )
        use_case = CreatePlan(mock_agent, mock_task_repo)

        plan = await use_case.refine(task, "Feedback")

        assert plan is not None
        # Should call execute instead
        assert task.status == TaskStatus.PLANNING

    @pytest.mark.asyncio
    async def test_refine_includes_feedback_in_prompt(
        self, mock_agent, mock_task_repo, task_with_plan
    ):
        """Refine should include user feedback in prompt."""
        use_case = CreatePlan(mock_agent, mock_task_repo)

        await use_case.refine(task_with_plan, "Please add security considerations")

        call_args = mock_agent.execute.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "security considerations" in prompt
        assert "Original goal" in prompt


# ===== FinalizeTask Tests =====


class TestFinalizeTask:
    @pytest.fixture
    def mock_diff_port(self):
        port = AsyncMock()
        port.get_worktree_diff.return_value = DiffResult(
            diff="+ new line",
            patch="patch content",
            files_changed=["file.py"],
            insertions=5,
            deletions=2,
        )
        return port

    @pytest.fixture
    def mock_task_repo(self):
        return AsyncMock()

    @pytest.fixture
    def finalize_use_case(self, mock_diff_port, mock_task_repo):
        return FinalizeTask(mock_diff_port, mock_task_repo)

    @pytest.fixture
    def task_can_mark_done(self, tmp_path):
        """Task with all conditions passing."""
        task = Task(
            id=uuid4(),
            description="Test task",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )
        cond = Condition(
            id=uuid4(),
            description="Test passes",
            role=ConditionRole.BLOCKING,
        )
        cond.check_status = CheckStatus.PASS
        cond.approve()
        cond.evidence_ref = EvidenceRef(
            task_id=task.id,
            condition_id=cond.id,
            check_id=None,
            artifact_path_rel="artifact.json",
            log_path_rel="log.txt",
        )
        task.conditions = [cond]
        return task

    @pytest.fixture
    def task_blocked(self, tmp_path):
        """Task that is blocked."""
        task = Task(
            id=uuid4(),
            description="Test task",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )
        task.status = TaskStatus.BLOCKED
        cond = Condition(
            id=uuid4(),
            description="Manual approval",
            role=ConditionRole.BLOCKING,
        )
        # Not approved
        task.conditions = [cond]
        return task

    @pytest.fixture
    def task_stopped(self, tmp_path):
        """Task that is stopped."""
        task = Task(
            id=uuid4(),
            description="Test task",
            goals=["Goal"],
            sources=[str(tmp_path)],
            budget=Budget(max_iterations=10, iteration_count=10),  # Exhausted
        )
        cond = Condition(
            id=uuid4(),
            description="Test passes",
            role=ConditionRole.BLOCKING,
        )
        cond.check_status = CheckStatus.FAIL
        task.conditions = [cond]
        return task

    @pytest.mark.asyncio
    async def test_execute_done(self, finalize_use_case, task_can_mark_done, mock_task_repo):
        """Execute should return DONE when task can be marked done."""
        result = await finalize_use_case.execute(task_can_mark_done)

        assert result.status == TaskStatus.DONE
        assert result.summary == "Task completed successfully"
        assert result.diff == "+ new line"
        mock_task_repo.save.assert_called()

    @pytest.mark.asyncio
    async def test_execute_blocked(self, finalize_use_case, task_blocked, mock_task_repo):
        """Execute should return BLOCKED when task is blocked."""
        result = await finalize_use_case.execute(task_blocked)

        assert result.status == TaskStatus.BLOCKED
        assert result.blocked_reason is not None
        assert "approval" in result.blocked_reason.lower()

    @pytest.mark.asyncio
    async def test_execute_stopped_max_iterations(
        self, finalize_use_case, task_stopped, mock_task_repo
    ):
        """Execute should return STOPPED with reason when budget exhausted."""
        result = await finalize_use_case.execute(task_stopped)

        assert result.status == TaskStatus.STOPPED
        assert result.stopped_reason is not None
        assert "iteration" in result.stopped_reason.lower()

    @pytest.mark.asyncio
    async def test_execute_stopped_stagnation(self, finalize_use_case, mock_task_repo, tmp_path):
        """Execute should return STOPPED with stagnation reason."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
            budget=Budget(stagnation_limit=3, stagnation_count=3),
        )
        cond = Condition(
            id=uuid4(),
            description="Test",
            role=ConditionRole.BLOCKING,
        )
        cond.check_status = CheckStatus.FAIL
        task.conditions = [cond]

        result = await finalize_use_case.execute(task)

        assert result.status == TaskStatus.STOPPED
        assert "stagnation" in result.stopped_reason.lower()

    @pytest.mark.asyncio
    async def test_execute_stopped_wall_time(self, finalize_use_case, mock_task_repo, tmp_path):
        """Execute should return STOPPED with wall time reason."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
            budget=Budget(wall_time_limit_s=100, elapsed_s=100),
        )
        cond = Condition(
            id=uuid4(),
            description="Test",
            role=ConditionRole.BLOCKING,
        )
        cond.check_status = CheckStatus.FAIL
        task.conditions = [cond]

        result = await finalize_use_case.execute(task)

        assert result.status == TaskStatus.STOPPED
        assert "time" in result.stopped_reason.lower()

    @pytest.mark.asyncio
    async def test_execute_collects_conditions(
        self, finalize_use_case, task_can_mark_done, mock_task_repo
    ):
        """Execute should collect condition outputs."""
        result = await finalize_use_case.execute(task_can_mark_done)

        assert len(result.conditions) == 1
        assert result.conditions[0].description == "Test passes"
        assert result.conditions[0].check_status == CheckStatus.PASS

    @pytest.mark.asyncio
    async def test_execute_collects_evidence_refs(
        self, finalize_use_case, mock_task_repo, tmp_path
    ):
        """Execute should collect evidence refs."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )
        cond = Condition(
            id=uuid4(),
            description="Test",
            role=ConditionRole.BLOCKING,
        )
        cond.check_status = CheckStatus.PASS
        cond.approve()
        cond.evidence_ref = EvidenceRef(
            task_id=task.id,
            condition_id=cond.id,
            check_id=None,
            artifact_path_rel="path/to/artifact",
            log_path_rel="path/to/log",
        )
        task.conditions = [cond]

        result = await finalize_use_case.execute(task)

        assert len(result.evidence_refs) == 1


# ===== DefineConditions Tests =====


class TestDefineConditions:
    @pytest.fixture
    def mock_task_repo(self):
        return AsyncMock()

    @pytest.fixture
    def task_with_inventory(self, tmp_path):
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )
        check_id = uuid4()
        task.verification_inventory = VerificationInventory(
            checks=[
                CheckSpec(
                    id=check_id,
                    name="pytest",
                    kind=CheckKind.TEST,
                    command="pytest",
                    cwd=str(tmp_path),
                )
            ],
            baseline=None,
            project_structure={},
            conventions=[],
        )
        return task

    @pytest.mark.asyncio
    async def test_execute_creates_conditions_from_inventory(
        self, mock_task_repo, task_with_inventory
    ):
        """Execute should create conditions from verification inventory."""
        use_case = DefineConditions(mock_task_repo)

        conditions = await use_case.execute(task_with_inventory)

        assert len(conditions) == 1
        assert conditions[0].role == ConditionRole.BLOCKING
        assert conditions[0].check_id is not None
        assert task_with_inventory.status == TaskStatus.CONDITIONS

    @pytest.mark.asyncio
    async def test_execute_adds_user_conditions(self, mock_task_repo, task_with_inventory):
        """Execute should add user-defined conditions as SIGNAL."""
        user_conditions = ["Coverage must be >80%", "No new warnings"]
        use_case = DefineConditions(mock_task_repo)

        conditions = await use_case.execute(task_with_inventory, user_conditions)

        assert len(conditions) == 3  # 1 from inventory + 2 user
        signal_conditions = [c for c in conditions if c.role == ConditionRole.SIGNAL]
        assert len(signal_conditions) == 2

    @pytest.mark.asyncio
    async def test_execute_without_inventory(self, mock_task_repo, tmp_path):
        """Execute should work without verification inventory."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )
        use_case = DefineConditions(mock_task_repo)

        conditions = await use_case.execute(task, ["Manual check"])

        assert len(conditions) == 1
        assert conditions[0].role == ConditionRole.SIGNAL

    @pytest.mark.asyncio
    async def test_execute_with_none_user_conditions(self, mock_task_repo, task_with_inventory):
        """Execute should handle None user_conditions."""
        use_case = DefineConditions(mock_task_repo)

        conditions = await use_case.execute(task_with_inventory, None)

        assert len(conditions) == 1  # Only from inventory


# ===== BuildVerificationInventory Tests =====


class TestBuildVerificationInventory:
    @pytest.fixture
    def mock_verification_port(self):
        port = AsyncMock()
        port.analyze_project.return_value = MagicMock(
            commands={
                "test": "pytest",
                "lint": "ruff check",
                "typecheck": "mypy",
                "build": "python -m build",
            },
            structure={"root_files": ["pyproject.toml"]},
            conventions=["Use pytest"],
        )
        return port

    @pytest.fixture
    def mock_check_runner(self):
        runner = AsyncMock()
        runner.run_check.return_value = MagicMock(
            check_id=uuid4(),
            status=CheckStatus.PASS,
            exit_code=0,
            stdout="OK",
            stderr="",
            duration_ms=1000,
            timestamp=datetime.now(UTC),
        )
        return runner

    @pytest.fixture
    def mock_task_repo(self):
        return AsyncMock()

    @pytest.fixture
    def task(self, tmp_path):
        return Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )

    @pytest.mark.asyncio
    async def test_execute_creates_inventory(
        self, mock_verification_port, mock_check_runner, mock_task_repo, task
    ):
        """Execute should create verification inventory."""
        use_case = BuildVerificationInventory(
            mock_verification_port, mock_check_runner, mock_task_repo
        )

        inventory = await use_case.execute(task)

        assert len(inventory.checks) == 4  # test, lint, typecheck, build
        assert inventory.project_structure == {"root_files": ["pyproject.toml"]}
        assert task.status == TaskStatus.VERIFICATION_INVENTORY

    @pytest.mark.asyncio
    async def test_execute_with_baseline(
        self, mock_verification_port, mock_check_runner, mock_task_repo, task
    ):
        """Execute should run baseline checks when requested."""
        use_case = BuildVerificationInventory(
            mock_verification_port, mock_check_runner, mock_task_repo
        )

        inventory = await use_case.execute(task, run_baseline=True)

        assert mock_check_runner.run_check.call_count == 4  # All checks run
        assert inventory.baseline is not None

    @pytest.mark.asyncio
    async def test_execute_without_baseline(
        self, mock_verification_port, mock_check_runner, mock_task_repo, task
    ):
        """Execute should not run baseline by default."""
        use_case = BuildVerificationInventory(
            mock_verification_port, mock_check_runner, mock_task_repo
        )

        inventory = await use_case.execute(task, run_baseline=False)

        mock_check_runner.run_check.assert_not_called()
        assert inventory.baseline is None

    @pytest.mark.asyncio
    async def test_execute_maps_check_kinds(
        self, mock_verification_port, mock_check_runner, mock_task_repo, task
    ):
        """Execute should map check kinds correctly."""
        use_case = BuildVerificationInventory(
            mock_verification_port, mock_check_runner, mock_task_repo
        )

        inventory = await use_case.execute(task)

        kinds = {c.kind for c in inventory.checks}
        assert CheckKind.TEST in kinds
        assert CheckKind.LINT in kinds
        assert CheckKind.TYPECHECK in kinds
        assert CheckKind.BUILD in kinds

    @pytest.mark.asyncio
    async def test_execute_with_empty_commands(
        self, mock_verification_port, mock_check_runner, mock_task_repo, task
    ):
        """Execute should skip empty commands."""
        mock_verification_port.analyze_project.return_value = MagicMock(
            commands={"test": "pytest", "lint": "", "build": None},
            structure={},
            conventions=[],
        )
        use_case = BuildVerificationInventory(
            mock_verification_port, mock_check_runner, mock_task_repo
        )

        inventory = await use_case.execute(task)

        assert len(inventory.checks) == 1  # Only test

    def test_map_kind_custom(self, mock_verification_port, mock_check_runner, mock_task_repo):
        """_map_kind should return CUSTOM for unknown kinds."""
        use_case = BuildVerificationInventory(
            mock_verification_port, mock_check_runner, mock_task_repo
        )

        result = use_case._map_kind("unknown_check")

        assert result == CheckKind.CUSTOM


# ===== RunQualityLoop Tests =====


class TestRunQualityLoop:
    @pytest.fixture
    def mock_agent(self):
        return AsyncMock()

    @pytest.fixture
    def mock_check_runner(self):
        return AsyncMock()

    @pytest.fixture
    def mock_task_repo(self):
        return AsyncMock()

    @pytest.fixture
    def task(self, tmp_path):
        return Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )

    @pytest.mark.asyncio
    async def test_execute_returns_true_on_quality_ok(
        self, mock_agent, mock_check_runner, mock_task_repo, task
    ):
        """Execute should return True when agent says QUALITY_OK."""
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="Everything looks good. QUALITY_OK",
            tools_used=[],
        )
        use_case = RunQualityLoop(mock_agent, mock_check_runner, mock_task_repo)

        result = await use_case.execute(task)

        assert result is True
        assert task.status == TaskStatus.QUALITY

    @pytest.mark.asyncio
    async def test_execute_loops_until_quality_ok(
        self, mock_agent, mock_check_runner, mock_task_repo, task
    ):
        """Execute should loop until QUALITY_OK or max iterations."""
        call_count = 0

        async def mock_execute(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return AgentResult(
                    messages=[],
                    final_response="Made improvements, checking again",
                    tools_used=["Edit"],
                )
            return AgentResult(
                messages=[],
                final_response="QUALITY_OK",
                tools_used=[],
            )

        mock_agent.execute.side_effect = mock_execute
        use_case = RunQualityLoop(mock_agent, mock_check_runner, mock_task_repo)

        result = await use_case.execute(task, max_iterations=3)

        assert result is True
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_execute_respects_budget_limit(
        self, mock_agent, mock_check_runner, mock_task_repo, tmp_path
    ):
        """Execute should respect quality_loop_limit budget."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
            budget=Budget(quality_loop_limit=1, quality_loop_count=0),
        )
        mock_agent.execute.return_value = AgentResult(
            messages=[],
            final_response="Making improvements",
            tools_used=["Edit"],
        )
        use_case = RunQualityLoop(mock_agent, mock_check_runner, mock_task_repo)

        result = await use_case.execute(task, max_iterations=5)

        # Should stop after budget limit
        assert result is True
        mock_task_repo.save.assert_called()


# ===== SelectStrategy Tests =====


class TestSelectStrategy:
    @pytest.fixture
    def simple_task(self, tmp_path):
        return Task(
            id=uuid4(),
            description="Simple feature",
            goals=["Goal 1"],
            sources=[str(tmp_path)],
        )

    @pytest.fixture
    def complex_task(self, tmp_path):
        return Task(
            id=uuid4(),
            description="Multi-step refactor",
            goals=["Goal 1", "Goal 2", "Goal 3", "Goal 4"],
            sources=[str(tmp_path)],
        )

    @pytest.fixture
    def monorepo_task(self, tmp_path):
        return Task(
            id=uuid4(),
            description="Cross-repo change",
            goals=["Goal 1"],
            sources=[str(tmp_path / "repo1"), str(tmp_path / "repo2")],
        )

    @pytest.mark.asyncio
    async def test_execute_simple_task(self, simple_task):
        """Execute should select quick planning for simple tasks."""
        use_case = SelectStrategy()

        strategy = await use_case.execute(simple_task)

        assert strategy.planning_depth == "quick"
        assert strategy.discovery_depth == "standard"
        assert simple_task.status == TaskStatus.STRATEGY

    @pytest.mark.asyncio
    async def test_execute_complex_task(self, complex_task):
        """Execute should select phased planning for complex tasks."""
        use_case = SelectStrategy()

        strategy = await use_case.execute(complex_task)

        assert strategy.planning_depth == "phased"
        assert strategy.discovery_depth == "standard"

    @pytest.mark.asyncio
    async def test_execute_multi_keyword_task(self, tmp_path):
        """Execute should detect multi keyword in description."""
        task = Task(
            id=uuid4(),
            description="Implement multi-database support",
            goals=["Goal 1"],
            sources=[str(tmp_path)],
        )
        use_case = SelectStrategy()

        strategy = await use_case.execute(task)

        assert strategy.planning_depth == "phased"

    @pytest.mark.asyncio
    async def test_execute_monorepo(self, monorepo_task):
        """Execute should select extended discovery for monorepos."""
        use_case = SelectStrategy()

        strategy = await use_case.execute(monorepo_task)

        assert strategy.discovery_depth == "extended"

    @pytest.mark.asyncio
    async def test_execute_with_baseline(self, simple_task):
        """Execute should pass include_baseline flag."""
        use_case = SelectStrategy()

        strategy = await use_case.execute(simple_task, include_baseline=True)

        assert strategy.include_baseline is True

    @pytest.mark.asyncio
    async def test_execute_without_baseline(self, simple_task):
        """Execute should default to no baseline."""
        use_case = SelectStrategy()

        strategy = await use_case.execute(simple_task, include_baseline=False)

        assert strategy.include_baseline is False

    @pytest.mark.asyncio
    async def test_execute_always_includes_quality_loop(self, simple_task):
        """Execute should always enable quality loop."""
        use_case = SelectStrategy()

        strategy = await use_case.execute(simple_task)

        assert strategy.include_quality_loop is True

    @pytest.mark.asyncio
    async def test_execute_provides_rationale(self, simple_task):
        """Execute should provide rationale."""
        use_case = SelectStrategy()

        strategy = await use_case.execute(simple_task)

        assert strategy.rationale is not None
        assert len(strategy.rationale) > 0
