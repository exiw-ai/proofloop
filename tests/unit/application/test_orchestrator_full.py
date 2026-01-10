"""Comprehensive unit tests for Orchestrator methods."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.application.dto.final_result import FinalResult
from src.application.dto.task_input import TaskInput
from src.application.orchestrator import Orchestrator
from src.domain.entities.budget import Budget
from src.domain.entities.condition import Condition
from src.domain.entities.iteration import Iteration, IterationDecision
from src.domain.entities.plan import Plan, PlanStep
from src.domain.entities.task import Task
from src.domain.entities.verification_inventory import VerificationInventory
from src.domain.ports.agent_port import AgentResult
from src.domain.ports.diff_port import DiffResult
from src.domain.services.multi_repo_manager import WorkspaceInfo
from src.domain.value_objects.check_types import CheckKind, CheckSpec
from src.domain.value_objects.condition_enums import CheckStatus, ConditionRole
from src.domain.value_objects.mcp_types import (
    MCPInstallSource,
    MCPServerConfig,
    MCPServerRegistry,
    MCPServerTemplate,
    MCPServerType,
)
from src.domain.value_objects.task_status import TaskStatus


@pytest.fixture
def mock_agent():
    agent = AsyncMock()
    agent.execute.return_value = AgentResult(
        messages=[],
        final_response='{"goal": "Test", "steps": [{"number": 1, "description": "Step 1"}]}',
        tools_used=["Read"],
    )
    return agent


@pytest.fixture
def mock_verification_port():
    port = AsyncMock()
    port.analyze_project.return_value = MagicMock(
        commands={"test": "pytest"},
        structure={"root_files": ["README.md"]},
        conventions=["Use pytest"],
    )
    return port


@pytest.fixture
def mock_check_runner():
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
def mock_diff_port():
    port = AsyncMock()
    port.get_worktree_diff.return_value = DiffResult(
        diff="",
        patch="",
        files_changed=["file.py"],
        insertions=10,
        deletions=5,
    )
    port.stash_all_repos.return_value = [MagicMock(repo_path="/repo", success=True, error=None)]
    port.rollback_all.return_value = []
    return port


@pytest.fixture
def mock_task_repo():
    repo = AsyncMock()
    repo.save.return_value = None
    repo.save_inventory.return_value = None
    repo.save_plan_approval.return_value = None
    repo.save_conditions_approval.return_value = None
    return repo


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
def task_input(tmp_path):
    return TaskInput(
        description="Test task",
        goals=["Goal 1"],
        workspace_path=tmp_path,
        auto_approve=True,
    )


class TestDiscoverWorkspace:
    @pytest.mark.asyncio
    async def test_discover_workspace_sets_workspace_info(self, orchestrator, tmp_path):
        """_discover_workspace should set _workspace_info."""
        with patch.object(
            orchestrator.multi_repo_manager,
            "discover_repos",
            new_callable=AsyncMock,
        ) as mock_discover:
            mock_discover.return_value = WorkspaceInfo(
                is_workspace=False,
                repos=[tmp_path],
                root=tmp_path,
            )

            result = await orchestrator._discover_workspace(tmp_path)

            assert result.is_workspace is False
            assert result.root == tmp_path
            assert orchestrator._workspace_info == result

    @pytest.mark.asyncio
    async def test_discover_workspace_multiple_repos(self, orchestrator, tmp_path):
        """_discover_workspace should handle multiple repos."""
        repo1 = tmp_path / "repo1"
        repo2 = tmp_path / "repo2"

        with patch.object(
            orchestrator.multi_repo_manager,
            "discover_repos",
            new_callable=AsyncMock,
        ) as mock_discover:
            mock_discover.return_value = WorkspaceInfo(
                is_workspace=True,
                repos=[repo1, repo2],
                root=tmp_path,
            )

            result = await orchestrator._discover_workspace(tmp_path)

            assert result.is_workspace is True
            assert len(result.repos) == 2


class TestStashAllRepos:
    @pytest.mark.asyncio
    async def test_stash_all_repos_calls_diff_port(self, orchestrator, mock_diff_port, tmp_path):
        """_stash_all_repos should call diff_port.stash_all_repos."""
        orchestrator._workspace_info = WorkspaceInfo(
            is_workspace=False,
            repos=[tmp_path],
            root=tmp_path,
        )

        await orchestrator._stash_all_repos("Test stash")

        mock_diff_port.stash_all_repos.assert_called_once()

    @pytest.mark.asyncio
    async def test_stash_all_repos_no_workspace_info(self, orchestrator, mock_diff_port):
        """_stash_all_repos should do nothing if no workspace_info."""
        orchestrator._workspace_info = None

        await orchestrator._stash_all_repos("Test stash")

        mock_diff_port.stash_all_repos.assert_not_called()

    @pytest.mark.asyncio
    async def test_stash_all_repos_handles_failure(self, orchestrator, mock_diff_port, tmp_path):
        """_stash_all_repos should handle stash failures gracefully."""
        orchestrator._workspace_info = WorkspaceInfo(
            is_workspace=False,
            repos=[tmp_path],
            root=tmp_path,
        )
        mock_diff_port.stash_all_repos.return_value = [
            MagicMock(repo_path=str(tmp_path), success=False, error="No changes")
        ]

        # Should not raise
        await orchestrator._stash_all_repos("Test stash")


class TestRollbackAllRepos:
    @pytest.mark.asyncio
    async def test_rollback_all_repos_calls_diff_port(self, orchestrator, mock_diff_port, tmp_path):
        """_rollback_all_repos should call diff_port.rollback_all."""
        orchestrator._workspace_info = WorkspaceInfo(
            is_workspace=False,
            repos=[tmp_path],
            root=tmp_path,
        )

        await orchestrator._rollback_all_repos("Rollback message")

        mock_diff_port.rollback_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_rollback_all_repos_no_workspace_info(self, orchestrator, mock_diff_port):
        """_rollback_all_repos should do nothing if no workspace_info."""
        orchestrator._workspace_info = None

        await orchestrator._rollback_all_repos("Rollback message")

        mock_diff_port.rollback_all.assert_not_called()


class TestSetupMcpServers:
    def test_setup_mcp_servers_with_pre_configured(self, orchestrator, task_input):
        """_setup_mcp_servers should add pre-configured servers."""
        config = MCPServerConfig(
            name="test-server",
            type=MCPServerType.STDIO,
            command="npx",
            args=["-y", "test-server"],
            env={},
        )
        mcp_configs = {"test-server": config}

        result = orchestrator._setup_mcp_servers(task_input, [], mcp_configs)

        assert "test-server" in result
        assert result["test-server"] == config
        assert orchestrator._active_mcp_servers == result

    def test_setup_mcp_servers_with_registry(self, task_input, tmp_path):
        """_setup_mcp_servers should use registry for
        task_input.mcp_servers."""
        registry = MCPServerRegistry()
        registry.register(
            MCPServerTemplate(
                name="registry-server",
                description="Test server",
                type=MCPServerType.STDIO,
                install_source=MCPInstallSource.NPM,
                command="npx",
                default_args=["-y", "registry-server"],
            )
        )

        orchestrator = Orchestrator(
            agent=AsyncMock(),
            verification_port=AsyncMock(),
            check_runner=AsyncMock(),
            diff_port=AsyncMock(),
            task_repo=AsyncMock(),
            state_dir=tmp_path,
            mcp_registry=registry,
        )

        task_input_with_mcp = TaskInput(
            description="Test",
            goals=["Goal"],
            workspace_path=tmp_path,
            mcp_servers=["registry-server"],
        )

        result = orchestrator._setup_mcp_servers(task_input_with_mcp, [], None)

        assert "registry-server" in result

    def test_setup_mcp_servers_with_selected_servers(self, task_input, tmp_path):
        """_setup_mcp_servers should add servers selected during planning."""
        registry = MCPServerRegistry()
        registry.register(
            MCPServerTemplate(
                name="selected-server",
                description="Selected server",
                type=MCPServerType.STDIO,
                install_source=MCPInstallSource.NPM,
                command="npx",
                default_args=["-y", "selected-server"],
            )
        )

        orchestrator = Orchestrator(
            agent=AsyncMock(),
            verification_port=AsyncMock(),
            check_runner=AsyncMock(),
            diff_port=AsyncMock(),
            task_repo=AsyncMock(),
            state_dir=tmp_path,
            mcp_registry=registry,
        )

        result = orchestrator._setup_mcp_servers(task_input, ["selected-server"], None)

        assert "selected-server" in result

    def test_setup_mcp_servers_empty(self, orchestrator, task_input):
        """_setup_mcp_servers should return empty dict when no servers."""
        result = orchestrator._setup_mcp_servers(task_input, [], None)

        assert result == {}


class TestOrchestratorRun:
    @pytest.mark.asyncio
    async def test_run_full_pipeline_auto_approve(
        self, orchestrator, task_input, mock_agent, mock_diff_port, mock_task_repo, tmp_path
    ):
        """Run() should complete full pipeline with auto_approve."""
        # Setup workspace discovery
        with patch.object(
            orchestrator.multi_repo_manager,
            "discover_repos",
            new_callable=AsyncMock,
        ) as mock_discover:
            mock_discover.return_value = WorkspaceInfo(
                is_workspace=False,
                repos=[tmp_path],
                root=tmp_path,
            )

            # Setup intake to return task
            task = Task(
                id=uuid4(),
                description="Test task",
                goals=["Goal 1"],
                sources=[str(tmp_path)],
                budget=Budget(max_iterations=10),
            )

            with patch.object(
                orchestrator.intake, "execute", new_callable=AsyncMock
            ) as mock_intake:
                mock_intake.return_value = task

                # Setup build_inventory
                inventory = VerificationInventory(
                    checks=[
                        CheckSpec(
                            id=uuid4(),
                            name="test_check",
                            kind=CheckKind.TEST,
                            command="pytest",
                            cwd=str(tmp_path),
                        )
                    ],
                    baseline=None,
                    project_structure={},
                    conventions=[],
                )
                with patch.object(
                    orchestrator.build_inventory, "execute", new_callable=AsyncMock
                ) as mock_build:
                    mock_build.return_value = inventory
                    task.verification_inventory = inventory

                    # Setup create_plan
                    plan = Plan(
                        goal="Test goal",
                        boundaries=[],
                        steps=[PlanStep(number=1, description="Step 1")],
                    )
                    with patch.object(
                        orchestrator.create_plan, "execute", new_callable=AsyncMock
                    ) as mock_plan:
                        mock_plan.return_value = plan
                        task.plan = plan

                        # Setup execute_delivery
                        iteration = Iteration(
                            number=1,
                            goal="Execute",
                            changes=["file.py"],
                            check_results={},
                            decision=IterationDecision.DONE,
                            decision_reason="Done",
                            timestamp=datetime.now(UTC),
                        )
                        with patch.object(
                            orchestrator.execute_delivery, "execute", new_callable=AsyncMock
                        ) as mock_exec:
                            mock_exec.return_value = iteration

                            # Make task done
                            for cond in task.conditions:
                                cond.check_status = CheckStatus.PASS
                                cond.approve()
                                cond.evidence_ref = MagicMock()

                            # Setup finalize
                            final_result = FinalResult(
                                task_id=task.id,
                                status=TaskStatus.DONE,
                                diff="",
                                patch="",
                                summary="Done",
                                conditions=[],
                                evidence_refs=[],
                            )
                            with patch.object(
                                orchestrator.finalize, "execute", new_callable=AsyncMock
                            ) as mock_finalize:
                                mock_finalize.return_value = final_result

                                result = await orchestrator.run(task_input)

                                assert result.status == TaskStatus.DONE

    @pytest.mark.asyncio
    async def test_run_with_stage_callback(self, orchestrator, task_input, tmp_path):
        """Run() should call stage callback."""
        stage_calls = []

        def on_stage(name: str, is_starting: bool, duration: float) -> None:
            stage_calls.append((name, is_starting, duration))

        with patch.object(
            orchestrator.multi_repo_manager, "discover_repos", new_callable=AsyncMock
        ) as mock_discover:
            mock_discover.return_value = WorkspaceInfo(
                is_workspace=False, repos=[tmp_path], root=tmp_path
            )

            task = Task(
                id=uuid4(),
                description="Test",
                goals=["Goal"],
                sources=[str(tmp_path)],
            )

            with patch.object(
                orchestrator.intake, "execute", new_callable=AsyncMock
            ) as mock_intake:
                mock_intake.return_value = task

                with (
                    patch.object(orchestrator.build_inventory, "execute", new_callable=AsyncMock),
                    patch.object(orchestrator.create_plan, "execute", new_callable=AsyncMock),
                ):
                    task.plan = Plan(
                        goal="Test",
                        boundaries=[],
                        steps=[PlanStep(number=1, description="Step")],
                    )

                    final_result = FinalResult(
                        task_id=task.id,
                        status=TaskStatus.BLOCKED,
                        diff="",
                        patch="",
                        summary="Blocked",
                        conditions=[],
                        evidence_refs=[],
                    )
                    with patch.object(
                        orchestrator.finalize, "execute", new_callable=AsyncMock
                    ) as mock_finalize:
                        mock_finalize.return_value = final_result

                        await orchestrator.run(task_input, on_stage=on_stage)

                        # Should have stage calls for inventory and planning
                        assert len(stage_calls) >= 2


class TestOrchestratorResume:
    @pytest.mark.asyncio
    async def test_resume_from_intake_status(self, orchestrator, task_input, tmp_path):
        """Resume() should handle INTAKE status."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
            budget=Budget(max_iterations=10),
        )
        task.status = TaskStatus.INTAKE

        with patch.object(
            orchestrator.select_strategy, "execute", new_callable=AsyncMock
        ) as mock_strategy:
            mock_strategy.return_value = MagicMock(include_baseline=False)

            with patch.object(
                orchestrator, "_continue_from_inventory", new_callable=AsyncMock
            ) as mock_continue:
                mock_continue.return_value = FinalResult(
                    task_id=task.id,
                    status=TaskStatus.DONE,
                    diff="",
                    patch="",
                    summary="Done",
                    conditions=[],
                    evidence_refs=[],
                )

                result = await orchestrator.resume(task, task_input)

                mock_continue.assert_called_once()
                assert result.status == TaskStatus.DONE

    @pytest.mark.asyncio
    async def test_resume_from_strategy_status(self, orchestrator, task_input, tmp_path):
        """Resume() should handle STRATEGY status."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )
        task.status = TaskStatus.STRATEGY

        with patch.object(
            orchestrator.select_strategy, "execute", new_callable=AsyncMock
        ) as mock_strategy:
            mock_strategy.return_value = MagicMock(include_baseline=False)

            with patch.object(
                orchestrator, "_continue_from_inventory", new_callable=AsyncMock
            ) as mock_continue:
                mock_continue.return_value = FinalResult(
                    task_id=task.id,
                    status=TaskStatus.DONE,
                    diff="",
                    patch="",
                    summary="Done",
                    conditions=[],
                    evidence_refs=[],
                )

                await orchestrator.resume(task, task_input)

                mock_continue.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_from_verification_inventory_status(
        self, orchestrator, task_input, tmp_path
    ):
        """Resume() should handle VERIFICATION_INVENTORY status."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )
        task.status = TaskStatus.VERIFICATION_INVENTORY

        with patch.object(orchestrator.create_plan, "execute", new_callable=AsyncMock) as mock_plan:
            task.plan = Plan(
                goal="Test",
                boundaries=[],
                steps=[PlanStep(number=1, description="Step")],
            )

            with (
                patch.object(orchestrator.define_conditions, "execute", new_callable=AsyncMock),
                patch.object(
                    orchestrator, "_continue_from_approval", new_callable=AsyncMock
                ) as mock_continue,
            ):
                mock_continue.return_value = FinalResult(
                    task_id=task.id,
                    status=TaskStatus.DONE,
                    diff="",
                    patch="",
                    summary="Done",
                    conditions=[],
                    evidence_refs=[],
                )

                await orchestrator.resume(task, task_input)

                mock_plan.assert_called_once()
                mock_continue.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_from_planning_status(self, orchestrator, task_input, tmp_path):
        """Resume() should handle PLANNING status."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )
        task.status = TaskStatus.PLANNING

        with (
            patch.object(orchestrator.define_conditions, "execute", new_callable=AsyncMock),
            patch.object(
                orchestrator, "_continue_from_approval", new_callable=AsyncMock
            ) as mock_continue,
        ):
            mock_continue.return_value = FinalResult(
                task_id=task.id,
                status=TaskStatus.DONE,
                diff="",
                patch="",
                summary="Done",
                conditions=[],
                evidence_refs=[],
            )

            await orchestrator.resume(task, task_input)

            mock_continue.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_from_conditions_status(self, orchestrator, task_input, tmp_path):
        """Resume() should handle CONDITIONS status."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )
        task.status = TaskStatus.CONDITIONS

        with patch.object(
            orchestrator, "_continue_from_approval", new_callable=AsyncMock
        ) as mock_continue:
            mock_continue.return_value = FinalResult(
                task_id=task.id,
                status=TaskStatus.DONE,
                diff="",
                patch="",
                summary="Done",
                conditions=[],
                evidence_refs=[],
            )

            await orchestrator.resume(task, task_input)

            mock_continue.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_from_approval_conditions_status(self, orchestrator, task_input, tmp_path):
        """Resume() should handle APPROVAL_CONDITIONS status."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )
        task.status = TaskStatus.APPROVAL_CONDITIONS

        with patch.object(
            orchestrator, "_continue_from_approval", new_callable=AsyncMock
        ) as mock_continue:
            mock_continue.return_value = FinalResult(
                task_id=task.id,
                status=TaskStatus.DONE,
                diff="",
                patch="",
                summary="Done",
                conditions=[],
                evidence_refs=[],
            )

            await orchestrator.resume(task, task_input)

            mock_continue.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_from_approval_plan_status(self, orchestrator, task_input, tmp_path):
        """Resume() should handle APPROVAL_PLAN status."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )
        task.status = TaskStatus.APPROVAL_PLAN

        with patch.object(
            orchestrator, "_continue_from_approval", new_callable=AsyncMock
        ) as mock_continue:
            mock_continue.return_value = FinalResult(
                task_id=task.id,
                status=TaskStatus.DONE,
                diff="",
                patch="",
                summary="Done",
                conditions=[],
                evidence_refs=[],
            )

            await orchestrator.resume(task, task_input)

            mock_continue.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_from_executing_status(self, orchestrator, task_input, tmp_path):
        """Resume() should handle EXECUTING status."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )
        task.status = TaskStatus.EXECUTING

        with patch.object(
            orchestrator, "_continue_from_delivery", new_callable=AsyncMock
        ) as mock_continue:
            mock_continue.return_value = FinalResult(
                task_id=task.id,
                status=TaskStatus.DONE,
                diff="",
                patch="",
                summary="Done",
                conditions=[],
                evidence_refs=[],
            )

            await orchestrator.resume(task, task_input)

            mock_continue.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_from_quality_status(self, orchestrator, task_input, tmp_path):
        """Resume() should handle QUALITY status."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )
        task.status = TaskStatus.QUALITY

        with patch.object(
            orchestrator, "_continue_from_delivery", new_callable=AsyncMock
        ) as mock_continue:
            mock_continue.return_value = FinalResult(
                task_id=task.id,
                status=TaskStatus.DONE,
                diff="",
                patch="",
                summary="Done",
                conditions=[],
                evidence_refs=[],
            )

            await orchestrator.resume(task, task_input)

            mock_continue.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_from_done_status(self, orchestrator, task_input, tmp_path):
        """Resume() should finalize DONE status tasks."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )
        task.status = TaskStatus.DONE

        with patch.object(
            orchestrator.finalize, "execute", new_callable=AsyncMock
        ) as mock_finalize:
            mock_finalize.return_value = FinalResult(
                task_id=task.id,
                status=TaskStatus.DONE,
                diff="",
                patch="",
                summary="Done",
                conditions=[],
                evidence_refs=[],
            )

            await orchestrator.resume(task, task_input)

            mock_finalize.assert_called_once()


class TestContinueFromInventory:
    @pytest.mark.asyncio
    async def test_continue_from_inventory(self, orchestrator, task_input, tmp_path):
        """_continue_from_inventory should run inventory, plan, conditions,
        approval."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )
        strategy = MagicMock(include_baseline=True)

        with (
            patch.object(
                orchestrator.build_inventory, "execute", new_callable=AsyncMock
            ) as mock_build,
            patch.object(orchestrator.create_plan, "execute", new_callable=AsyncMock) as mock_plan,
        ):
            task.plan = Plan(
                goal="Test",
                boundaries=[],
                steps=[PlanStep(number=1, description="Step")],
            )

            with (
                patch.object(orchestrator.define_conditions, "execute", new_callable=AsyncMock),
                patch.object(
                    orchestrator, "_continue_from_approval", new_callable=AsyncMock
                ) as mock_continue,
            ):
                mock_continue.return_value = FinalResult(
                    task_id=task.id,
                    status=TaskStatus.DONE,
                    diff="",
                    patch="",
                    summary="Done",
                    conditions=[],
                    evidence_refs=[],
                )

                await orchestrator._continue_from_inventory(task, strategy, task_input)

                mock_build.assert_called_once()
                # include_baseline should be True from strategy
                assert mock_build.call_args.args[1] is True
                mock_plan.assert_called_once()


class TestContinueFromApproval:
    @pytest.mark.asyncio
    async def test_continue_from_approval_conditions_not_approved(
        self, orchestrator, task_input, tmp_path
    ):
        """_continue_from_approval should block if conditions not approved."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )

        with patch.object(
            orchestrator.approve_conditions, "execute", new_callable=AsyncMock
        ) as mock_approve:
            mock_approve.return_value = False

            with patch.object(
                orchestrator.finalize, "execute", new_callable=AsyncMock
            ) as mock_finalize:
                mock_finalize.return_value = FinalResult(
                    task_id=task.id,
                    status=TaskStatus.BLOCKED,
                    diff="",
                    patch="",
                    summary="Blocked",
                    conditions=[],
                    evidence_refs=[],
                )

                result = await orchestrator._continue_from_approval(task, task_input)

                assert task.status == TaskStatus.BLOCKED
                assert result.status == TaskStatus.BLOCKED

    @pytest.mark.asyncio
    async def test_continue_from_approval_plan_not_approved(
        self, orchestrator, task_input, tmp_path
    ):
        """_continue_from_approval should block if plan not approved."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )

        with patch.object(
            orchestrator.approve_conditions, "execute", new_callable=AsyncMock
        ) as mock_approve_cond:
            mock_approve_cond.return_value = True

            with patch.object(
                orchestrator.approve_plan, "execute", new_callable=AsyncMock
            ) as mock_approve_plan:
                mock_approve_plan.return_value = False

                with patch.object(
                    orchestrator.finalize, "execute", new_callable=AsyncMock
                ) as mock_finalize:
                    mock_finalize.return_value = FinalResult(
                        task_id=task.id,
                        status=TaskStatus.BLOCKED,
                        diff="",
                        patch="",
                        summary="Blocked",
                        conditions=[],
                        evidence_refs=[],
                    )

                    result = await orchestrator._continue_from_approval(task, task_input)

                    assert task.status == TaskStatus.BLOCKED
                    assert result.status == TaskStatus.BLOCKED

    @pytest.mark.asyncio
    async def test_continue_from_approval_success(self, orchestrator, task_input, tmp_path):
        """_continue_from_approval should continue to delivery if approved."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
        )

        with patch.object(
            orchestrator.approve_conditions, "execute", new_callable=AsyncMock
        ) as mock_approve_cond:
            mock_approve_cond.return_value = True

            with patch.object(
                orchestrator.approve_plan, "execute", new_callable=AsyncMock
            ) as mock_approve_plan:
                mock_approve_plan.return_value = True

                with patch.object(
                    orchestrator, "_continue_from_delivery", new_callable=AsyncMock
                ) as mock_continue:
                    mock_continue.return_value = FinalResult(
                        task_id=task.id,
                        status=TaskStatus.DONE,
                        diff="",
                        patch="",
                        summary="Done",
                        conditions=[],
                        evidence_refs=[],
                    )

                    result = await orchestrator._continue_from_approval(task, task_input)

                    mock_continue.assert_called_once()
                    assert result.status == TaskStatus.DONE


class TestContinueFromDelivery:
    @pytest.mark.asyncio
    async def test_continue_from_delivery_already_done(self, orchestrator, task_input, tmp_path):
        """_continue_from_delivery should skip execution if task already
        done."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
            budget=Budget(max_iterations=10),
        )
        # Mark all conditions as passed
        cond = Condition(
            id=uuid4(),
            description="Test",
            role=ConditionRole.BLOCKING,
        )
        cond.check_status = CheckStatus.PASS
        cond.approve()
        cond.evidence_ref = MagicMock()
        task.conditions = [cond]

        with (
            patch.object(
                orchestrator.execute_delivery, "execute", new_callable=AsyncMock
            ) as mock_exec,
            patch.object(
                orchestrator.run_quality, "execute", new_callable=AsyncMock
            ) as mock_quality,
            patch.object(orchestrator.finalize, "execute", new_callable=AsyncMock) as mock_finalize,
        ):
            mock_finalize.return_value = FinalResult(
                task_id=task.id,
                status=TaskStatus.DONE,
                diff="",
                patch="",
                summary="Done",
                conditions=[],
                evidence_refs=[],
            )

            await orchestrator._continue_from_delivery(task, task_input)

            # Should not execute since task is already done
            mock_exec.assert_not_called()
            mock_quality.assert_called_once()

    @pytest.mark.asyncio
    async def test_continue_from_delivery_budget_exhausted(
        self, orchestrator, task_input, tmp_path
    ):
        """_continue_from_delivery should skip execution if budget
        exhausted."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
            budget=Budget(max_iterations=10, iteration_count=10),
        )

        with (
            patch.object(
                orchestrator.execute_delivery, "execute", new_callable=AsyncMock
            ) as mock_exec,
            patch.object(orchestrator.finalize, "execute", new_callable=AsyncMock) as mock_finalize,
        ):
            mock_finalize.return_value = FinalResult(
                task_id=task.id,
                status=TaskStatus.STOPPED,
                diff="",
                patch="",
                summary="Stopped",
                conditions=[],
                evidence_refs=[],
            )

            await orchestrator._continue_from_delivery(task, task_input)

            mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_continue_from_delivery_starts_budget_tracking(
        self, orchestrator, task_input, tmp_path
    ):
        """_continue_from_delivery should start budget tracking if not
        started."""
        task = Task(
            id=uuid4(),
            description="Test",
            goals=["Goal"],
            sources=[str(tmp_path)],
            budget=Budget(max_iterations=10),
        )
        task.budget.start_timestamp = 0  # Not started

        # Add a failing condition so delivery actually runs
        cond = Condition(
            id=uuid4(),
            description="Test",
            role=ConditionRole.BLOCKING,
        )
        cond.check_status = CheckStatus.FAIL  # Failing initially
        task.conditions = [cond]

        call_count = 0

        async def mock_execute(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            # After first execution, mark condition as passed
            cond.check_status = CheckStatus.PASS
            cond.approve()
            cond.evidence_ref = MagicMock()
            return Iteration(
                number=call_count,
                goal="Test",
                changes=["file.py"],
                check_results={},
                decision=IterationDecision.DONE,
                decision_reason="Done",
                timestamp=datetime.now(UTC),
            )

        with (
            patch.object(orchestrator.execute_delivery, "execute", side_effect=mock_execute),
            patch.object(orchestrator.run_quality, "execute", new_callable=AsyncMock),
            patch.object(orchestrator.finalize, "execute", new_callable=AsyncMock) as mock_finalize,
        ):
            mock_finalize.return_value = FinalResult(
                task_id=task.id,
                status=TaskStatus.DONE,
                diff="",
                patch="",
                summary="Done",
                conditions=[],
                evidence_refs=[],
            )

            await orchestrator._continue_from_delivery(task, task_input)

            # Budget tracking should have started
            assert task.budget.start_timestamp > 0


class TestRunWithCallbacks:
    @pytest.mark.asyncio
    async def test_run_with_plan_and_conditions_callback(self, orchestrator, tmp_path):
        """Run() should handle plan_and_conditions_callback."""
        task_input = TaskInput(
            description="Test",
            goals=["Goal"],
            workspace_path=tmp_path,
            auto_approve=False,  # Not auto-approve to trigger callback
        )

        callback_called = False

        def plan_callback(_plan, conditions):
            nonlocal callback_called
            callback_called = True
            return (True, None, conditions)  # Approve

        with patch.object(
            orchestrator.multi_repo_manager, "discover_repos", new_callable=AsyncMock
        ) as mock_discover:
            mock_discover.return_value = WorkspaceInfo(
                is_workspace=False, repos=[tmp_path], root=tmp_path
            )

            task = Task(
                id=uuid4(),
                description="Test",
                goals=["Goal"],
                sources=[str(tmp_path)],
                budget=Budget(max_iterations=10),
            )

            with patch.object(
                orchestrator.intake, "execute", new_callable=AsyncMock
            ) as mock_intake:
                mock_intake.return_value = task

                with (
                    patch.object(orchestrator.build_inventory, "execute", new_callable=AsyncMock),
                    patch.object(orchestrator.create_plan, "execute", new_callable=AsyncMock),
                ):
                    task.plan = Plan(
                        goal="Test",
                        boundaries=[],
                        steps=[PlanStep(number=1, description="Step")],
                    )

                    with patch.object(
                        orchestrator.execute_delivery, "execute", new_callable=AsyncMock
                    ) as mock_exec:
                        iteration = Iteration(
                            number=1,
                            goal="Test",
                            changes=["file.py"],
                            check_results={},
                            decision=IterationDecision.DONE,
                            decision_reason="Done",
                            timestamp=datetime.now(UTC),
                        )
                        mock_exec.return_value = iteration

                        # Mark task as done
                        cond = Condition(
                            id=uuid4(),
                            description="Test",
                            role=ConditionRole.BLOCKING,
                        )
                        cond.check_status = CheckStatus.PASS
                        cond.approve()
                        cond.evidence_ref = MagicMock()
                        task.conditions = [cond]

                        with patch.object(
                            orchestrator.finalize, "execute", new_callable=AsyncMock
                        ) as mock_finalize:
                            mock_finalize.return_value = FinalResult(
                                task_id=task.id,
                                status=TaskStatus.DONE,
                                diff="",
                                patch="",
                                summary="Done",
                                conditions=[],
                                evidence_refs=[],
                            )

                            await orchestrator.run(
                                task_input,
                                plan_and_conditions_callback=plan_callback,
                            )

                            assert callback_called

    @pytest.mark.asyncio
    async def test_run_with_plan_callback_refine(self, orchestrator, tmp_path):
        """Run() should refine plan when callback provides feedback."""
        task_input = TaskInput(
            description="Test",
            goals=["Goal"],
            workspace_path=tmp_path,
            auto_approve=False,
        )

        call_count = 0

        def plan_callback(_plan, conditions):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (False, "Add more detail", conditions)  # Reject with feedback
            return (True, None, conditions)  # Approve on second call

        with patch.object(
            orchestrator.multi_repo_manager, "discover_repos", new_callable=AsyncMock
        ) as mock_discover:
            mock_discover.return_value = WorkspaceInfo(
                is_workspace=False, repos=[tmp_path], root=tmp_path
            )

            task = Task(
                id=uuid4(),
                description="Test",
                goals=["Goal"],
                sources=[str(tmp_path)],
            )

            with patch.object(
                orchestrator.intake, "execute", new_callable=AsyncMock
            ) as mock_intake:
                mock_intake.return_value = task

                with (
                    patch.object(orchestrator.build_inventory, "execute", new_callable=AsyncMock),
                    patch.object(orchestrator.create_plan, "execute", new_callable=AsyncMock),
                ):
                    task.plan = Plan(
                        goal="Test",
                        boundaries=[],
                        steps=[PlanStep(number=1, description="Step")],
                    )

                    with patch.object(
                        orchestrator.create_plan, "refine", new_callable=AsyncMock
                    ) as mock_refine:
                        mock_refine.return_value = task.plan

                        with patch.object(
                            orchestrator.execute_delivery,
                            "execute",
                            new_callable=AsyncMock,
                        ) as mock_exec:
                            iteration = Iteration(
                                number=1,
                                goal="Test",
                                changes=["file.py"],
                                check_results={},
                                decision=IterationDecision.DONE,
                                decision_reason="Done",
                                timestamp=datetime.now(UTC),
                            )
                            mock_exec.return_value = iteration

                            cond = Condition(
                                id=uuid4(),
                                description="Test",
                                role=ConditionRole.BLOCKING,
                            )
                            cond.check_status = CheckStatus.PASS
                            cond.approve()
                            cond.evidence_ref = MagicMock()
                            task.conditions = [cond]

                            with patch.object(
                                orchestrator.finalize,
                                "execute",
                                new_callable=AsyncMock,
                            ) as mock_finalize:
                                mock_finalize.return_value = FinalResult(
                                    task_id=task.id,
                                    status=TaskStatus.DONE,
                                    diff="",
                                    patch="",
                                    summary="Done",
                                    conditions=[],
                                    evidence_refs=[],
                                )

                                await orchestrator.run(
                                    task_input,
                                    plan_and_conditions_callback=plan_callback,
                                )

                                # refine should have been called once
                                mock_refine.assert_called_once()
                                assert call_count == 2

    @pytest.mark.asyncio
    async def test_run_with_deprecated_plan_approval_callback(self, orchestrator, tmp_path):
        """Run() should handle deprecated plan_approval_callback."""
        task_input = TaskInput(
            description="Test",
            goals=["Goal"],
            workspace_path=tmp_path,
            auto_approve=False,
        )

        def deprecated_callback(_plan):
            return (True, None)  # Approve

        with patch.object(
            orchestrator.multi_repo_manager, "discover_repos", new_callable=AsyncMock
        ) as mock_discover:
            mock_discover.return_value = WorkspaceInfo(
                is_workspace=False, repos=[tmp_path], root=tmp_path
            )

            task = Task(
                id=uuid4(),
                description="Test",
                goals=["Goal"],
                sources=[str(tmp_path)],
            )

            with patch.object(
                orchestrator.intake, "execute", new_callable=AsyncMock
            ) as mock_intake:
                mock_intake.return_value = task

                with (
                    patch.object(orchestrator.build_inventory, "execute", new_callable=AsyncMock),
                    patch.object(orchestrator.create_plan, "execute", new_callable=AsyncMock),
                ):
                    task.plan = Plan(
                        goal="Test",
                        boundaries=[],
                        steps=[PlanStep(number=1, description="Step")],
                    )

                    with patch.object(
                        orchestrator.execute_delivery, "execute", new_callable=AsyncMock
                    ) as mock_exec:
                        iteration = Iteration(
                            number=1,
                            goal="Test",
                            changes=["file.py"],
                            check_results={},
                            decision=IterationDecision.DONE,
                            decision_reason="Done",
                            timestamp=datetime.now(UTC),
                        )
                        mock_exec.return_value = iteration

                        cond = Condition(
                            id=uuid4(),
                            description="Test",
                            role=ConditionRole.BLOCKING,
                        )
                        cond.check_status = CheckStatus.PASS
                        cond.approve()
                        cond.evidence_ref = MagicMock()
                        task.conditions = [cond]

                        with patch.object(
                            orchestrator.finalize, "execute", new_callable=AsyncMock
                        ) as mock_finalize:
                            mock_finalize.return_value = FinalResult(
                                task_id=task.id,
                                status=TaskStatus.DONE,
                                diff="",
                                patch="",
                                summary="Done",
                                conditions=[],
                                evidence_refs=[],
                            )

                            result = await orchestrator.run(
                                task_input,
                                plan_approval_callback=deprecated_callback,
                            )

                            assert result.status == TaskStatus.DONE

    @pytest.mark.asyncio
    async def test_run_plan_rejected_without_feedback(self, orchestrator, tmp_path):
        """Run() should block when plan rejected without feedback."""
        task_input = TaskInput(
            description="Test",
            goals=["Goal"],
            workspace_path=tmp_path,
            auto_approve=False,
        )

        def reject_callback(_plan, conditions):
            return (False, None, conditions)  # Reject without feedback

        with patch.object(
            orchestrator.multi_repo_manager, "discover_repos", new_callable=AsyncMock
        ) as mock_discover:
            mock_discover.return_value = WorkspaceInfo(
                is_workspace=False, repos=[tmp_path], root=tmp_path
            )

            task = Task(
                id=uuid4(),
                description="Test",
                goals=["Goal"],
                sources=[str(tmp_path)],
            )

            with patch.object(
                orchestrator.intake, "execute", new_callable=AsyncMock
            ) as mock_intake:
                mock_intake.return_value = task

                with (
                    patch.object(orchestrator.build_inventory, "execute", new_callable=AsyncMock),
                    patch.object(orchestrator.create_plan, "execute", new_callable=AsyncMock),
                ):
                    task.plan = Plan(
                        goal="Test",
                        boundaries=[],
                        steps=[PlanStep(number=1, description="Step")],
                    )

                    with patch.object(
                        orchestrator.finalize, "execute", new_callable=AsyncMock
                    ) as mock_finalize:
                        mock_finalize.return_value = FinalResult(
                            task_id=task.id,
                            status=TaskStatus.BLOCKED,
                            diff="",
                            patch="",
                            summary="Blocked",
                            conditions=[],
                            evidence_refs=[],
                        )

                        result = await orchestrator.run(
                            task_input,
                            plan_and_conditions_callback=reject_callback,
                        )

                        assert result.status == TaskStatus.BLOCKED
