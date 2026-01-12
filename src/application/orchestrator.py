import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from loguru import logger

from src.application.dto.final_result import FinalResult
from src.application.dto.task_input import TaskInput
from src.application.services.supervisor import Supervisor
from src.application.services.tool_gating import (
    DELIVERY_STAGES,
    PRE_DELIVERY_STAGES,
    ToolGatingError,
    get_allowed_tools,
    validate_bash_command,
)
from src.application.use_cases.approve_conditions import ApproveConditions
from src.application.use_cases.approve_plan import ApprovePlan
from src.application.use_cases.build_verification_inventory import BuildVerificationInventory
from src.application.use_cases.create_plan import CreatePlan
from src.application.use_cases.define_conditions import DefineConditions
from src.application.use_cases.execute_delivery import ExecuteDelivery
from src.application.use_cases.finalize_task import FinalizeTask
from src.application.use_cases.intake_task import IntakeTask
from src.application.use_cases.run_quality_loop import RunQualityLoop
from src.application.use_cases.select_mcp_servers import MCPSuggestion, SelectMCPServers
from src.application.use_cases.select_strategy import SelectStrategy
from src.application.workspace_manager import WorkspaceManager
from src.domain.entities.condition import Condition
from src.domain.entities.iteration import Iteration
from src.domain.entities.plan import Plan
from src.domain.entities.task import Task
from src.domain.ports.agent_port import AgentPort, MessageCallback
from src.domain.ports.check_runner_port import CheckRunnerPort
from src.domain.ports.diff_port import DiffPort
from src.domain.ports.task_repo_port import TaskRepoPort
from src.domain.ports.verification_port import VerificationPort
from src.domain.services.multi_repo_manager import MultiRepoManager
from src.domain.value_objects.clarification import ClarificationAnswer, ClarificationQuestion
from src.domain.value_objects.condition_enums import CheckStatus
from src.domain.value_objects.mcp_types import MCPServerConfig, MCPServerRegistry
from src.domain.value_objects.supervision_enums import RetryStrategy
from src.domain.value_objects.task_status import TaskStatus

PlanApprovalCallback = Callable[[Plan], tuple[bool, str | None]]
PlanAndConditionsCallback = Callable[
    [Plan, list[Condition]], tuple[bool, str | None, list[Condition]]
]
ClarificationCallback = Callable[[list[ClarificationQuestion]], list[ClarificationAnswer]]
StageCallback = Callable[[str, bool, float], None]
MCPSelectionCallback = Callable[[list[MCPSuggestion]], list[str]]
TaskCreatedCallback = Callable[[UUID], None]


@dataclass
class OrchestrationCallbacks:
    """Callbacks for orchestration events."""

    plan_approval: PlanApprovalCallback | None = None  # DEPRECATED
    plan_and_conditions: PlanAndConditionsCallback | None = None
    clarification: ClarificationCallback | None = None
    mcp_selection: MCPSelectionCallback | None = None
    on_agent_message: MessageCallback | None = None
    on_stage: StageCallback | None = None
    on_task_created: TaskCreatedCallback | None = None


__all__ = [
    "ClarificationCallback",
    "DELIVERY_STAGES",
    "MCPSelectionCallback",
    "OrchestrationCallbacks",
    "PRE_DELIVERY_STAGES",
    "PlanAndConditionsCallback",
    "PlanApprovalCallback",
    "StageCallback",
    "TaskCreatedCallback",
    "ToolGatingError",
    "get_allowed_tools",
    "validate_bash_command",
    "Orchestrator",
]


class Orchestrator:
    """Pipeline orchestrator that coordinates all use cases. Enforces tool
    gating per contract 1.5.

    Pipeline:
    Intake -> Strategy -> VerificationInventory -> [MCP Selection] -> Plan -> Conditions ->
    ApproveConditions -> ApprovePlan -> Delivery Loop -> [Quality Loop] -> Finalize
    """

    def __init__(
        self,
        agent: AgentPort,
        verification_port: VerificationPort,
        check_runner: CheckRunnerPort,
        diff_port: DiffPort,
        task_repo: TaskRepoPort,
        state_dir: Path,
        mcp_registry: MCPServerRegistry | None = None,
    ) -> None:
        self.agent = agent
        self.verification_port = verification_port
        self.check_runner = check_runner
        self.diff_port = diff_port
        self.task_repo = task_repo
        self.state_dir = state_dir
        self.mcp_registry = mcp_registry

        # Initialize services
        self.supervisor = Supervisor()
        self.multi_repo_manager = MultiRepoManager()
        self._workspace_manager = WorkspaceManager(self.multi_repo_manager, self.diff_port)
        self._last_iteration: Iteration | None = None  # For stop detection in retry loop
        self._active_mcp_servers: dict[str, MCPServerConfig] = {}

        # Initialize use cases
        self.intake = IntakeTask(task_repo)
        self.select_strategy = SelectStrategy()
        self.build_inventory = BuildVerificationInventory(
            verification_port, check_runner, task_repo
        )
        self.create_plan = CreatePlan(agent, task_repo)
        self.define_conditions = DefineConditions(agent, task_repo)
        self.approve_conditions = ApproveConditions(task_repo)
        self.approve_plan = ApprovePlan(task_repo)
        self.execute_delivery = ExecuteDelivery(
            agent, check_runner, diff_port, task_repo, state_dir
        )
        self.run_quality = RunQualityLoop(agent, check_runner, task_repo)
        self.finalize = FinalizeTask(diff_port, task_repo)

        # MCP use case (initialized lazily if registry provided)
        self.select_mcp: SelectMCPServers | None = None
        if mcp_registry:
            self.select_mcp = SelectMCPServers(agent, mcp_registry)

    def _setup_mcp_servers(
        self,
        task_input: TaskInput,
        selected_servers: list[str],
        mcp_configs: dict[str, MCPServerConfig] | None = None,
    ) -> dict[str, MCPServerConfig]:
        """Setup MCP servers from selection and pre-provided configs.

        Args:
            task_input: Task input with MCP settings.
            selected_servers: List of server names selected during planning.
            mcp_configs: Pre-configured MCP server configs (from CLI).

        Returns:
            Dict of server name -> MCPServerConfig ready for use.
        """
        servers: dict[str, MCPServerConfig] = {}

        # Add pre-configured servers
        if mcp_configs:
            servers.update(mcp_configs)

        # Add servers from task input
        if self.mcp_registry:
            for name in task_input.mcp_servers:
                if name not in servers:
                    template = self.mcp_registry.get(name)
                    if template:
                        # Create config without credentials (will fail if needed)
                        servers[name] = template.to_config()

            # Add servers selected during planning
            for name in selected_servers:
                if name not in servers:
                    template = self.mcp_registry.get(name)
                    if template:
                        servers[name] = template.to_config()

        self._active_mcp_servers = servers
        return servers

    async def run(
        self,
        input: TaskInput,
        callbacks: OrchestrationCallbacks | None = None,
        mcp_configs: dict[str, MCPServerConfig] | None = None,
    ) -> FinalResult:
        """
        Run the full pipeline:
        Intake -> Strategy -> VerificationInventory -> [MCP Selection] -> [Clarifications] ->
        Plan -> Conditions -> ApproveConditions -> ApprovePlan -> Delivery Loop ->
        [Quality] -> Finalize

        Args:
            input: Task input parameters
            callbacks: Callbacks for orchestration events.
            mcp_configs: Pre-configured MCP server configs to use.
        """
        logger.info(f"Starting task: {input.description}")

        # Extract callbacks from dataclass (with defaults if None)
        callbacks = callbacks or OrchestrationCallbacks()
        plan_approval_callback = callbacks.plan_approval
        plan_and_conditions_callback = callbacks.plan_and_conditions
        clarification_callback = callbacks.clarification
        mcp_selection_callback = callbacks.mcp_selection
        on_agent_message = callbacks.on_agent_message
        on_stage = callbacks.on_stage
        on_task_created = callbacks.on_task_created

        # Discover workspace repos
        await self._workspace_manager.discover_workspace(input.workspace_path)

        def stage_start(name: str) -> float:
            """Mark stage start and return start time."""
            if on_stage:
                on_stage(name, True, 0)
            return time.time()

        def stage_end(name: str, start_time: float) -> None:
            """Mark stage complete with duration."""
            if on_stage:
                on_stage(name, False, time.time() - start_time)

        # 1. Intake
        task = await self.intake.execute(input)
        logger.info(f"Task created: {task.id}")

        # Notify caller about task ID (for resume purposes)
        if on_task_created:
            on_task_created(task.id)

        # 2. Strategy
        strategy = await self.select_strategy.execute(task, input.baseline)
        logger.info(f"Strategy selected: {strategy.planning_depth}")

        # 3. Verification Inventory (MUST complete before any code changes)
        t = stage_start("inventory")
        await self.build_inventory.execute(task, strategy.include_baseline, on_agent_message)
        check_count = len(task.verification_inventory.checks) if task.verification_inventory else 0
        stage_end("inventory", t)
        logger.info(f"Inventory built: {check_count} checks")

        # 4. MCP Server Selection (if enabled and not auto_approve)
        selected_mcp_servers: list[str] = []
        if input.mcp_enabled and self.select_mcp and not input.auto_approve:
            t = stage_start("mcp_selection")
            suggestions = await self.select_mcp.analyze_and_suggest(task, on_agent_message)
            if suggestions and mcp_selection_callback:
                selected_mcp_servers = mcp_selection_callback(suggestions)
                logger.info(f"Selected MCP servers: {selected_mcp_servers}")
            stage_end("mcp_selection", t)

        # Setup MCP servers for delivery
        if input.mcp_enabled:
            self._setup_mcp_servers(input, selected_mcp_servers, mcp_configs)
            if self._active_mcp_servers:
                logger.info(f"Active MCP servers: {list(self._active_mcp_servers.keys())}")

        # 6. Clarifications (if callback provided and not auto_approve)
        clarifications: list[ClarificationAnswer] = []
        if clarification_callback and not input.auto_approve:
            t = stage_start("clarification")
            questions = await self.create_plan.ask_clarifications(task, on_agent_message)
            if questions:
                logger.info(f"Asking {len(questions)} clarification questions")
                clarifications = clarification_callback(questions)
                logger.info(f"Received {len(clarifications)} answers")
            stage_end("clarification", t)

        # 5. Plan (with user clarifications if provided)
        t = stage_start("planning")
        await self.create_plan.execute(
            task, clarifications=clarifications or None, on_message=on_agent_message
        )
        stage_end("planning", t)
        logger.info(f"Plan created: {task.plan.goal if task.plan else 'no plan'}")

        # 6. Conditions
        await self.define_conditions.execute(task, input.user_conditions)
        logger.info(f"Conditions defined: {len(task.conditions)}")

        # 7. Approve Conditions
        # Skip standalone approval if interactive callback will handle it
        if not (plan_and_conditions_callback or plan_approval_callback):
            approved = await self.approve_conditions.execute(task, input.auto_approve)
            if not approved:
                task.status = TaskStatus.BLOCKED
                await self.task_repo.save(task)
                return await self.finalize.execute(task)
        elif input.auto_approve:
            # Auto-approve conditions before plan approval
            await self.approve_conditions.execute(task, auto_approve=True)

        # 8. Approve Plan and Conditions (with optional refinement loop)
        if input.auto_approve:
            approved = await self.approve_plan.execute(task, auto_approve=True)
        elif plan_and_conditions_callback and task.plan:
            # Interactive approval with conditions editing
            approved = False
            while True:
                is_approved, feedback, modified_conditions = plan_and_conditions_callback(
                    task.plan, task.conditions
                )
                logger.debug(
                    f"Callback returned: is_approved={is_approved}, feedback={feedback is not None}, "
                    f"modified_conditions_count={len(modified_conditions)}"
                )

                # Update conditions if user modified them
                if modified_conditions != task.conditions:
                    task.conditions = modified_conditions
                    await self.task_repo.save(task)
                    logger.info(f"Conditions updated: {len(task.conditions)} total")

                if is_approved:
                    # Approve plan
                    task.plan.approve()
                    logger.info(f"User approved plan: {task.plan.goal}")

                    # Approve all conditions (user approved them along with plan)
                    for condition in task.conditions:
                        with contextlib.suppress(ValueError):
                            condition.approve()
                    await self.task_repo.save_conditions_approval(task.id, task.conditions)

                    task.transition_to(TaskStatus.APPROVAL_PLAN)
                    await self.task_repo.save_plan_approval(task.id, task.plan)
                    await self.task_repo.save(task)
                    approved = True
                    break
                elif feedback:
                    # Refine plan based on feedback (sanitize for logging)
                    safe_feedback = feedback.encode("utf-8", errors="replace").decode("utf-8")
                    logger.info(f"Refining plan with feedback: {safe_feedback[:100]}...")
                    await self.create_plan.refine(task, feedback, on_agent_message)
                    logger.info(f"Plan refined: {task.plan.goal}")
                    # Loop continues - show updated plan
                else:
                    # Rejected without feedback - exit
                    approved = False
                    break
        elif plan_approval_callback and task.plan:
            # DEPRECATED: Old callback without conditions
            approved = False
            while True:
                is_approved, feedback = plan_approval_callback(task.plan)
                if is_approved:
                    task.plan.approve()
                    logger.info(f"User approved plan: {task.plan.goal}")
                    task.transition_to(TaskStatus.APPROVAL_PLAN)
                    await self.task_repo.save_plan_approval(task.id, task.plan)
                    await self.task_repo.save(task)
                    approved = True
                    break
                elif feedback:
                    safe_feedback = feedback.encode("utf-8", errors="replace").decode("utf-8")
                    logger.info(f"Refining plan with feedback: {safe_feedback[:100]}...")
                    await self.create_plan.refine(task, feedback, on_agent_message)
                    logger.info(f"Plan refined: {task.plan.goal}")
                else:
                    approved = False
                    break
        else:
            approved = False

        if not approved:
            logger.info("Plan not approved, setting status to BLOCKED")
            task.status = TaskStatus.BLOCKED
            await self.task_repo.save(task)
            return await self.finalize.execute(task)

        logger.info("Plan approved, starting delivery")

        # 9. Delivery - single agent call for all steps
        t = stage_start("delivery")
        task.budget.start_tracking()  # Start wall time tracking
        logger.debug(
            f"Delivery check: can_mark_done={task.can_mark_done()}, "
            f"budget_exhausted={task.budget.is_exhausted()}, "
            f"blocking_conditions={len(task.get_blocking_conditions())}"
        )

        # Early exit if already done (no blocking conditions or all satisfied)
        if task.can_mark_done():
            logger.info("Task already satisfies completion conditions, skipping delivery")
        else:
            # ONE agent call for ALL steps
            iteration = await self.execute_delivery.execute(task, on_agent_message)
            logger.info(f"Delivery complete: {iteration.decision.value}")

            # Smart retry loop with Supervisor decision (contract 1.3, 1.11)
            # Loop until: task done, budget exhausted, or supervisor stops
            while not task.can_mark_done() and not task.budget.is_exhausted():
                iteration = await self._handle_retry(task, iteration, on_agent_message)
                # Check if supervisor decided to stop
                if iteration == self._last_iteration:
                    # _handle_retry returned same iteration = STOP decision
                    break
                self._last_iteration = iteration

        stage_end("delivery", t)
        logger.debug(
            f"Delivery ended: can_mark_done={task.can_mark_done()}, "
            f"budget_exhausted={task.budget.is_exhausted()}, "
            f"iterations={len(task.iterations)}"
        )

        # 10. Optional Quality Loop
        if task.can_mark_done() and strategy.include_quality_loop:
            await self.run_quality.execute(task, on_message=on_agent_message)

        # 11. Finalize
        result = await self.finalize.execute(task)
        logger.info(f"Task finalized: {result.status.value}")

        return result

    async def resume(
        self,
        task: Task,
        input: TaskInput,
        on_agent_message: MessageCallback | None = None,
    ) -> FinalResult:
        """Resume task from current status."""
        logger.info(f"Resuming task {task.id} from {task.status.value}")

        # Continue from current stage
        if task.status in {TaskStatus.INTAKE, TaskStatus.STRATEGY}:
            strategy = await self.select_strategy.execute(task, input.baseline)
            return await self._continue_from_inventory(task, strategy, input, on_agent_message)

        if task.status == TaskStatus.VERIFICATION_INVENTORY:
            # Inventory already done, need to create plan
            await self.create_plan.execute(task, on_message=on_agent_message)
            await self.define_conditions.execute(task, input.user_conditions)
            return await self._continue_from_approval(task, input, on_agent_message)

        if task.status == TaskStatus.PLANNING:
            await self.define_conditions.execute(task, input.user_conditions)
            return await self._continue_from_approval(task, input, on_agent_message)

        if task.status == TaskStatus.CONDITIONS:
            return await self._continue_from_approval(task, input, on_agent_message)

        if task.status in {TaskStatus.APPROVAL_CONDITIONS, TaskStatus.APPROVAL_PLAN}:
            return await self._continue_from_approval(task, input, on_agent_message)

        if task.status in {TaskStatus.EXECUTING, TaskStatus.QUALITY}:
            return await self._continue_from_delivery(task, input, on_agent_message)

        # Default: finalize
        return await self.finalize.execute(task)

    async def _continue_from_inventory(
        self,
        task: Task,
        strategy: object,
        input: TaskInput,
        on_agent_message: MessageCallback | None = None,
    ) -> FinalResult:
        """Continue pipeline from inventory stage."""
        include_baseline = getattr(strategy, "include_baseline", False)
        await self.build_inventory.execute(task, include_baseline, on_agent_message)
        await self.create_plan.execute(task, on_message=on_agent_message)
        await self.define_conditions.execute(task, input.user_conditions)
        return await self._continue_from_approval(task, input, on_agent_message)

    async def _continue_from_approval(
        self,
        task: Task,
        input: TaskInput,
        on_agent_message: MessageCallback | None = None,
    ) -> FinalResult:
        """Continue pipeline from approval stage."""
        approved = await self.approve_conditions.execute(task, input.auto_approve)
        if not approved:
            task.status = TaskStatus.BLOCKED
            await self.task_repo.save(task)
            return await self.finalize.execute(task)

        approved = await self.approve_plan.execute(task, input.auto_approve)
        if not approved:
            task.status = TaskStatus.BLOCKED
            await self.task_repo.save(task)
            return await self.finalize.execute(task)

        return await self._continue_from_delivery(task, input, on_agent_message)

    async def _continue_from_delivery(
        self,
        task: Task,
        input: TaskInput,  # noqa: ARG002
        on_agent_message: MessageCallback | None = None,
    ) -> FinalResult:
        """Continue pipeline from delivery stage."""
        if not task.can_mark_done() and not task.budget.is_exhausted():
            # Start wall time tracking if not already started (resume case)
            if task.budget.start_timestamp == 0:
                task.budget.start_tracking()
            # Single agent call for all steps
            iteration = await self.execute_delivery.execute(task, on_agent_message)
            logger.info(f"Delivery complete: {iteration.decision.value}")

            # Smart retry loop with Supervisor decision (contract 1.3, 1.11)
            while not task.can_mark_done() and not task.budget.is_exhausted():
                iteration = await self._handle_retry(task, iteration, on_agent_message)
                if iteration == self._last_iteration:
                    break
                self._last_iteration = iteration

        # Quality loop if applicable
        if task.can_mark_done():
            await self.run_quality.execute(task, on_message=on_agent_message)

        return await self.finalize.execute(task)

    async def _handle_retry(
        self,
        task: Task,
        previous_iteration: Iteration,
        on_agent_message: MessageCallback | None = None,
    ) -> Iteration:
        """Handle retry logic with Supervisor decision.

        Args:
            task: The task being executed
            previous_iteration: The iteration that just completed with failures
            on_agent_message: Optional callback for real-time display

        Returns:
            The new iteration after retry (or previous if no retry)
        """
        # Register error pattern with supervisor
        self.supervisor._check_loop(task, previous_iteration)

        # Decide retry strategy
        strategy, reason = self.supervisor.decide_retry_strategy(task, previous_iteration)
        failed_count = sum(1 for c in task.conditions if c.check_status != CheckStatus.PASS)
        logger.warning(
            f"Retry strategy: {strategy.value} ({failed_count} failed conditions) - {reason}"
        )

        if strategy == RetryStrategy.STOP:
            logger.error(f"Supervisor stopped retry: {reason}")
            return previous_iteration

        if strategy == RetryStrategy.ROLLBACK_AND_RETRY:
            # Stash changes in all repos and retry fresh
            logger.info("Rolling back changes with git stash (all repos)")
            stash_msg = f"proofloop: rollback iteration {previous_iteration.number}"
            await self._workspace_manager.rollback_all_repos(stash_msg)

            iteration = await self.execute_delivery.execute_fresh_retry(
                task,
                warning="Previous approach failed repeatedly. Try a different approach.",
                on_message=on_agent_message,
            )
            logger.info(f"Fresh retry complete: {iteration.decision.value}")
            return iteration

        # CONTINUE_WITH_CONTEXT: retry with feedback about failures
        iteration = await self.execute_delivery.execute_retry(
            task,
            previous_iteration=previous_iteration,
            on_message=on_agent_message,
        )
        logger.info(f"Retry with context complete: {iteration.decision.value}")
        return iteration

    async def run_research(
        self,
        input: "ResearchTaskInput",
        on_agent_message: MessageCallback | None = None,
        on_stage: StageCallback | None = None,
    ) -> "ResearchResult":
        """Run the research pipeline.

        This is a convenience method that delegates to ResearchOrchestrator.
        For the full research pipeline, use ResearchOrchestrator directly.

        Args:
            input: Research task input parameters
            on_agent_message: Optional callback for real-time tool action display
            on_stage: Optional callback for stage progress display
        """
        from src.application.research_orchestrator import ResearchOrchestrator

        research_orchestrator = ResearchOrchestrator(
            agent=self.agent,
            task_repo=self.task_repo,
            state_dir=self.state_dir,
        )
        return await research_orchestrator.run_research(input, on_agent_message, on_stage)


# Re-export ResearchTaskInput for backward compatibility
from src.application.research_orchestrator import ResearchTaskInput as ResearchTaskInput  # noqa: E402, F401, I001
from src.domain.entities.research_result import ResearchResult  # noqa: E402, F401, I001
