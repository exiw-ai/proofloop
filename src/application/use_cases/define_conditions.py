from uuid import uuid4

from loguru import logger

from src.domain.entities.condition import Condition
from src.domain.entities.task import Task
from src.domain.ports.agent_port import AgentPort
from src.domain.ports.task_repo_port import TaskRepoPort
from src.domain.value_objects.check_types import CheckSpec
from src.domain.value_objects.condition_enums import ConditionRole
from src.domain.value_objects.task_status import TaskStatus
from src.infrastructure.utils.agent_json import parse_agent_json


class DefineConditions:
    def __init__(self, agent: AgentPort, task_repo: TaskRepoPort) -> None:
        self.agent = agent
        self.task_repo = task_repo

    async def execute(
        self, task: Task, user_conditions: list[str] | None = None
    ) -> list[Condition]:
        """Define conditions (DoD) from verification inventory, plan, and user
        input.

        Three sources of conditions:
        1. Automatic checks from verification_inventory (test, lint, etc.) - minimal
        2. Semantic conditions from plan - what the plan aims to achieve
        3. User-provided conditions - additional signals
        """
        if user_conditions is None:
            user_conditions = []

        conditions: list[Condition] = []

        # 1. Automatic checks from verification inventory (minimal)
        if task.verification_inventory and task.verification_inventory.checks:
            selected_checks = await self._select_automatic_checks(task)

            for check in task.verification_inventory.checks:
                if check.name in selected_checks:
                    condition = Condition(
                        id=uuid4(),
                        description=f"{check.name} passes",
                        role=ConditionRole.BLOCKING,
                        check_id=check.id,
                    )
                    conditions.append(condition)

        # 2. Semantic conditions from plan (NEW)
        semantic_conditions = await self._generate_semantic_conditions(task)
        for desc in semantic_conditions:
            condition = Condition(
                id=uuid4(),
                description=desc,
                role=ConditionRole.BLOCKING,
                check_id=None,  # Agent verifies during execution
            )
            conditions.append(condition)

        # 3. User conditions as SIGNAL
        for desc in user_conditions:
            condition = Condition(
                id=uuid4(),
                description=desc,
                role=ConditionRole.SIGNAL,
            )
            conditions.append(condition)

        task.conditions = conditions
        task.transition_to(TaskStatus.CONDITIONS)
        await self.task_repo.save(task)

        auto_count = len([c for c in conditions if c.check_id is not None])
        semantic_count = len(
            [c for c in conditions if c.check_id is None and c.role == ConditionRole.BLOCKING]
        )
        signal_count = len([c for c in conditions if c.role == ConditionRole.SIGNAL])

        logger.info(
            "Conditions defined for task {}: {} automatic, {} semantic, {} signal",
            task.id,
            auto_count,
            semantic_count,
            signal_count,
        )

        return conditions

    async def _select_automatic_checks(self, task: Task) -> list[str]:
        """Agent selects minimal automatic checks for this task.

        Limit to 1-2 most important checks.
        """
        assert task.verification_inventory is not None

        checks_info = [
            {"name": c.name, "kind": c.kind.value, "command": c.command}
            for c in task.verification_inventory.checks
        ]

        prompt = f"""Select the MINIMUM automatic verification checks needed for this task.

Task: {task.description}

Available checks:
{checks_info}

STRICT RULES:
- Documentation-only changes (README, docs/*) -> NO checks or just "lint"
- Config changes -> usually NO checks
- Code logic changes -> "test" is usually enough
- Add "typecheck" ONLY if task involves type annotations or API contracts
- Add "lint" ONLY if task involves code style or formatting
- Add "build" ONLY if explicitly building/compiling artifacts
- Prefer FEWER checks - 1 is often enough, max 2

If you select a test check, consider narrowing the scope to relevant tests.

Respond with JSON:
{{
    "selected_checks": [],
    "modified_commands": {{}},
    "reasoning": "Why these specific checks"
}}

IMPORTANT: selected_checks CAN be empty for simple tasks!"""

        result = await self.agent.execute(
            prompt=prompt,
            allowed_tools=[],
            cwd=".",
        )

        # Fallback to empty list, not all checks
        data = parse_agent_json(
            result.final_response,
            {"selected_checks": [], "reasoning": "Fallback: no checks"},
        )

        selected = list(data.get("selected_checks", []))
        raw_modified: object = data.get("modified_commands", {})
        modified_commands: dict[str, str] = (
            dict(raw_modified) if isinstance(raw_modified, dict) else {}
        )
        reasoning = str(data.get("reasoning", ""))

        # Limit to max 2 checks
        if len(selected) > 2:
            logger.warning("Agent selected {} checks, limiting to 2", len(selected))
            priority = ["test", "typecheck", "lint", "build"]
            selected = [c for c in priority if c in selected][:2]

        # Apply modified commands
        if modified_commands:
            self._apply_modified_commands(task, modified_commands)

        logger.info(
            "Agent selected automatic checks for task {}: {} (reason: {})",
            task.id,
            selected or "none",
            reasoning,
        )

        return selected

    async def _generate_semantic_conditions(self, task: Task) -> list[str]:
        """Generate semantic conditions based on the PLAN (not just task
        description).

        DefineConditions is called AFTER CreatePlan, so task.plan is
        available. The plan already accounts for what exists in the
        project.
        """
        if not task.plan:
            return []

        # Format plan steps
        steps_text = "\n".join(f"  {s.number}. {s.description}" for s in task.plan.steps)
        boundaries_text = ", ".join(task.plan.boundaries) if task.plan.boundaries else "none"

        prompt = f"""Based on this PLAN, propose 1-3 KEY acceptance conditions.

PLAN:
Goal: {task.plan.goal}
Steps:
{steps_text}
Boundaries (what we will NOT do): {boundaries_text}

Original task: {task.description}

IMPORTANT: Generate conditions based on the PLAN, not the original task.
The plan already accounts for what exists in the project.

Rules:
- Focus on the OUTCOME of the plan, not implementation details
- Each condition should be independently verifiable
- Maximum 3 conditions (ideally 1-2)
- DO NOT include generic checks like "tests pass" or "code compiles"
- DO include plan-specific outcomes like:
  - "User A cannot access User B's data" (if plan adds isolation)
  - "API returns correct pagination" (if plan adds pagination)
  - "All existing users have tenant_id set" (if plan migrates users)

If plan is simple (typo fix, docs update, config change) -> return empty list []

Respond with JSON:
{{
    "conditions": [],
    "reasoning": "How these conditions verify the plan's success"
}}"""

        result = await self.agent.execute(
            prompt=prompt,
            allowed_tools=[],
            cwd=".",
        )

        data = parse_agent_json(
            result.final_response,
            {"conditions": [], "reasoning": "No semantic conditions needed"},
        )

        conditions = list(data.get("conditions", []))[:3]  # Max 3
        reasoning = str(data.get("reasoning", ""))

        if conditions:
            logger.info(
                "Agent generated semantic conditions for task {}: {} (reason: {})",
                task.id,
                conditions,
                reasoning,
            )
        else:
            logger.debug("No semantic conditions generated for task {}", task.id)

        return conditions

    def _apply_modified_commands(self, task: Task, modified_commands: dict[str, str]) -> None:
        """Apply agent-suggested command modifications to checks."""
        assert task.verification_inventory is not None

        updated_checks: list[CheckSpec] = []
        for check in task.verification_inventory.checks:
            if check.name in modified_commands:
                new_command = modified_commands[check.name]
                updated_check = CheckSpec(
                    id=check.id,
                    name=check.name,
                    kind=check.kind,
                    command=new_command,
                    cwd=check.cwd,
                    env=check.env,
                    timeout_s=check.timeout_s,
                )
                updated_checks.append(updated_check)
                logger.info(
                    "Modified {} command: {} -> {}",
                    check.name,
                    check.command,
                    new_command,
                )
            else:
                updated_checks.append(check)

        task.verification_inventory.checks = updated_checks
