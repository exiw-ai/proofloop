from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from loguru import logger

from src.application.services.command_tracker import CommandTracker
from src.application.services.tool_gating import get_allowed_tools
from src.domain.entities.condition import Condition
from src.domain.entities.iteration import Iteration, IterationDecision
from src.domain.entities.task import Task
from src.domain.ports.agent_port import (
    AgentMessage,
    AgentPort,
    AgentResult,
    MessageCallback,
    SessionStallError,
)
from src.domain.ports.check_runner_port import CheckRunnerPort, CheckRunResult
from src.domain.ports.diff_port import DiffPort, DiffResult
from src.domain.ports.task_repo_port import TaskRepoPort
from src.domain.value_objects.condition_enums import CheckStatus
from src.domain.value_objects.evidence_types import EvidenceRef, EvidenceSummary
from src.domain.value_objects.task_status import TaskStatus
from src.infrastructure.persistence.evidence_store import EvidenceStore


class ExecuteDelivery:
    def __init__(
        self,
        agent: AgentPort,
        check_runner: CheckRunnerPort,
        diff_port: DiffPort,
        task_repo: TaskRepoPort,
        state_dir: Path,
    ):
        self.agent = agent
        self.check_runner = check_runner
        self.diff_port = diff_port
        self.task_repo = task_repo
        self.evidence_store = EvidenceStore(state_dir)
        self._command_tracker = CommandTracker()

    async def _safe_get_diff(self, workspace_path: str) -> DiffResult:
        """Get worktree diff, handling missing workspace gracefully."""
        if not Path(workspace_path).exists():
            logger.warning(f"Workspace no longer exists: {workspace_path}")
            return DiffResult(
                diff="",
                patch="",
                files_changed=[],
                insertions=0,
                deletions=0,
            )
        return await self.diff_port.get_worktree_diff(workspace_path)

    async def _execute_with_stall_retry(
        self,
        prompt: str,
        allowed_tools: list[str],
        cwd: str,
        on_message: MessageCallback | None = None,
        max_retries: int = 3,
    ) -> AgentResult:
        """Execute agent with automatic retry on session stall.

        SessionStallError indicates infrastructure failure (timeout),
        not agent logic error. We retry transparently without counting
        toward stagnation.
        """
        for attempt in range(max_retries):
            try:
                return await self.agent.execute(
                    prompt=prompt,
                    allowed_tools=allowed_tools,
                    cwd=cwd,
                    on_message=on_message,
                )
            except SessionStallError as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Agent session stalled (attempt {attempt + 1}/{max_retries}): {e}"
                    )
                else:
                    logger.error(f"Agent session stalled after {max_retries} attempts: {e}")
                    raise
        raise RuntimeError("Unreachable: max_retries exhausted")

    def _wrap_callback_with_tracker(self, on_message: MessageCallback | None) -> MessageCallback:
        """Wrap callback to also track commands."""

        def wrapped(msg: AgentMessage) -> None:
            self._command_tracker.on_message(msg)
            if on_message:
                on_message(msg)

        return wrapped

    async def execute(
        self,
        task: Task,
        on_message: MessageCallback | None = None,
    ) -> Iteration:
        """Execute ALL remaining plan steps in one agent call.

        New architecture: single agent call with all steps instead of
        per-step loop. Agent works until completion, SDK handles
        auto-compaction if needed.

        Args:
            task: The task to execute.
            on_message: Optional callback for real-time tool display.
        """
        task.transition_to(TaskStatus.EXECUTING)

        iteration_num = len(task.iterations) + 1
        steps_count = len(task.plan.steps) if task.plan else 0

        # Clear tracker for fresh execution
        self._command_tracker.clear()

        # Wrap callback to track commands
        tracking_callback = self._wrap_callback_with_tracker(on_message)

        # ONE agent call for ALL steps
        prompt = self._build_full_plan_prompt(task)
        await self._execute_with_stall_retry(
            prompt=prompt,
            allowed_tools=get_allowed_tools(task.status),
            cwd=task.sources[0],
            on_message=tracking_callback,
        )

        diff_result = await self._safe_get_diff(task.sources[0])

        # After agent completes, run ALL checks (with command context)
        check_results = await self._run_all_checks(task, iteration_num, on_message)

        # Create single iteration representing full delivery
        iteration = Iteration(
            number=iteration_num,
            goal=f"Complete {steps_count} plan steps",
            changes=diff_result.files_changed,
            check_results=check_results,
            decision=IterationDecision.DONE if task.can_mark_done() else IterationDecision.CONTINUE,
            decision_reason="All steps executed" if task.can_mark_done() else "Checks not passing",
            timestamp=datetime.now(UTC),
        )

        task.add_iteration(iteration)
        task.budget.record_iteration(bool(diff_result.files_changed))
        await self.task_repo.save(task)

        return iteration

    async def execute_retry(
        self,
        task: Task,
        previous_iteration: Iteration,
        on_message: MessageCallback | None = None,
    ) -> Iteration:
        """Execute retry with context about previous failures.

        Unlike execute(), this builds a prompt that includes:
        - Previous iteration summary (files changed, decision)
        - Failed conditions with their evidence (output_tail)
        """
        task.transition_to(TaskStatus.EXECUTING)

        iteration_num = len(task.iterations) + 1

        failed_conditions = self._get_failed_conditions_with_evidence(task)
        prompt = self._build_retry_prompt(task, previous_iteration, failed_conditions)

        await self._execute_with_stall_retry(
            prompt=prompt,
            allowed_tools=get_allowed_tools(task.status),
            cwd=task.sources[0],
            on_message=on_message,
        )

        diff_result = await self._safe_get_diff(task.sources[0])
        check_results = await self._run_all_checks(task, iteration_num, on_message)

        iteration = Iteration(
            number=iteration_num,
            goal="Fix failed checks from previous attempt",
            changes=diff_result.files_changed,
            check_results=check_results,
            decision=IterationDecision.DONE if task.can_mark_done() else IterationDecision.CONTINUE,
            decision_reason="All checks passing"
            if task.can_mark_done()
            else "Checks still failing",
            timestamp=datetime.now(UTC),
        )

        task.add_iteration(iteration)
        task.budget.record_iteration(bool(diff_result.files_changed))
        await self.task_repo.save(task)

        return iteration

    async def execute_fresh_retry(
        self,
        task: Task,
        warning: str,
        on_message: MessageCallback | None = None,
    ) -> Iteration:
        """Execute fresh retry after rollback with a warning message.

        The warning informs the agent to try a different approach.
        """
        task.transition_to(TaskStatus.EXECUTING)

        iteration_num = len(task.iterations) + 1
        base_prompt = self._build_full_plan_prompt(task)
        prompt = f"""⚠️ WARNING: {warning}

{base_prompt}"""

        await self._execute_with_stall_retry(
            prompt=prompt,
            allowed_tools=get_allowed_tools(task.status),
            cwd=task.sources[0],
            on_message=on_message,
        )

        diff_result = await self._safe_get_diff(task.sources[0])
        check_results = await self._run_all_checks(task, iteration_num, on_message)

        iteration = Iteration(
            number=iteration_num,
            goal="Fresh retry with different approach",
            changes=diff_result.files_changed,
            check_results=check_results,
            decision=IterationDecision.DONE if task.can_mark_done() else IterationDecision.CONTINUE,
            decision_reason="All checks passing"
            if task.can_mark_done()
            else "Checks still failing",
            timestamp=datetime.now(UTC),
        )

        task.add_iteration(iteration)
        task.budget.record_iteration(bool(diff_result.files_changed))
        await self.task_repo.save(task)

        return iteration

    def _get_failed_conditions_with_evidence(
        self,
        task: Task,
    ) -> list[tuple[Condition, EvidenceSummary | None]]:
        """Extract failed conditions with their evidence summaries."""
        failed = []
        for condition in task.get_blocking_conditions():
            if condition.check_status == CheckStatus.FAIL:
                failed.append((condition, condition.evidence_summary))
        return failed

    def _build_retry_prompt(
        self,
        task: Task,
        previous_iteration: Iteration,
        failed_conditions: list[tuple[Condition, EvidenceSummary | None]],
    ) -> str:
        """Build prompt with context about previous failures."""
        failures_text = []
        for condition, evidence in failed_conditions:
            if evidence:
                failures_text.append(f"""### {condition.description}
- Status: FAILED
- Exit code: {evidence.exit_code}
- Output:
```
{evidence.output_tail}
```""")
            else:
                failures_text.append(f"""### {condition.description}
- Status: FAILED
- No evidence available""")

        changes_str = (
            ", ".join(previous_iteration.changes) if previous_iteration.changes else "none"
        )

        workspace = task.sources[0]
        return f"""You are continuing work on a task. The previous attempt completed but some checks failed.

## CRITICAL: AUTONOMOUS EXECUTION
You MUST complete this task autonomously without asking questions.
- NEVER ask for confirmation or clarification
- Make reasonable decisions when information is ambiguous
- Just execute - do not wait for user input

## CRITICAL WORKSPACE RESTRICTION
You MUST only create, modify, or delete files within: {workspace}
- DO NOT run git restore, git checkout, or commands that affect files outside this directory
- DO NOT delete or move the workspace directory itself

## Task: {task.description}

## Previous Attempt Summary
- Files changed: {changes_str}
- Decision: {previous_iteration.decision.value}
- Reason: {previous_iteration.decision_reason}

## Failed Checks (MUST FIX)
{chr(10).join(failures_text)}

## Instructions
1. Analyze why each check failed based on the output above
2. Fix the issues - do NOT repeat the same mistakes
3. Run the checks again to verify fixes

Focus on fixing the failures, not re-implementing everything from scratch."""

    async def _run_all_checks(
        self,
        task: Task,
        iteration_num: int,
        on_message: MessageCallback | None = None,
    ) -> dict[UUID, CheckStatus]:
        """Run all blocking condition checks and record evidence."""
        check_results: dict[UUID, CheckStatus] = {}

        for condition in task.get_blocking_conditions():
            if condition.check_id and task.verification_inventory:
                # Automated check - run the command
                check = task.verification_inventory.get_check(condition.check_id)
                if check:
                    run_result = await self.check_runner.run_check(check, task.sources[0])
                    check_results[condition.id] = run_result.status

                    evidence_ref, evidence_summary = await self._record_evidence(
                        task, iteration_num, condition.id, run_result, check.command
                    )
                    condition.record_check_result(
                        status=run_result.status,
                        evidence_ref=evidence_ref,
                        evidence_summary=evidence_summary,
                    )
            elif condition.check_id is None and condition.check_status != CheckStatus.PASS:
                # Manual condition - verify via agent (re-check on every iteration until PASS)
                status, evidence_ref, evidence_summary = await self._verify_manual_condition(
                    task, iteration_num, condition, on_message
                )
                condition.record_check_result(
                    status=status,
                    evidence_ref=evidence_ref,
                    evidence_summary=evidence_summary,
                )
                check_results[condition.id] = status
                logger.info(f"Manual condition '{condition.description}': {status.value}")

        return check_results

    def _build_full_plan_prompt(self, task: Task) -> str:
        """Build prompt with ALL remaining plan steps for single agent
        execution."""
        if not task.plan:
            return f"Complete the following task: {task.description}"

        # All remaining steps (none completed yet in new architecture)
        steps_text = "\n".join(f"{s.number}. {s.description}" for s in task.plan.steps)

        constraints_text = ", ".join(task.constraints) if task.constraints else "None"

        # All blocking conditions
        blocking_conditions = task.get_blocking_conditions()
        if blocking_conditions:
            conditions_text = "\n".join(f"- {c.description}" for c in blocking_conditions)
        else:
            conditions_text = "None"

        workspace = task.sources[0]
        return f"""Complete the following task: {task.description}

## CRITICAL: AUTONOMOUS EXECUTION
You MUST complete this task autonomously without asking questions.
- NEVER ask for confirmation or clarification
- Make reasonable decisions when information is ambiguous
- If a file doesn't exist, create it. If a path is unclear, use best judgment
- Just execute - do not wait for user input

## CRITICAL WORKSPACE RESTRICTION
You MUST only create, modify, or delete files within: {workspace}
- DO NOT run git restore, git checkout, or commands that affect files outside this directory
- DO NOT delete or move the workspace directory itself
- Changes to files outside the workspace will cause task failure

## Steps to complete (in order):
{steps_text}

## Constraints:
{constraints_text}

## Blocking conditions (MUST be satisfied):
{conditions_text}

Work through each step systematically. After completing all steps,
verify that all blocking conditions are met by running appropriate checks.
If a check fails, fix the issue before concluding.

Report your progress as you work through each step."""

    async def _verify_manual_condition(
        self,
        task: Task,
        iteration_num: int,
        condition: Condition,
        on_message: MessageCallback | None = None,
    ) -> tuple[CheckStatus, EvidenceRef, EvidenceSummary]:
        """Verify a manual condition by asking the agent to check it.

        Returns (status, evidence_ref, evidence_summary) per contract
        1.2.
        """
        # Get command context from implementation phase
        command_context = self._command_tracker.format_for_verification()

        # Get files changed in current iteration
        latest_iteration = task.iterations[-1] if task.iterations else None
        files_context = ""
        if latest_iteration and latest_iteration.changes:
            files_context = f"""
## Files changed during implementation:
{chr(10).join(f"- {f}" for f in latest_iteration.changes)}
"""

        prompt = f"""You are an INDEPENDENT VERIFIER checking if a condition is satisfied.

## Condition to verify:
{condition.description}

## Task context:
{task.description}

## Working directory:
{task.sources[0]}
{files_context}
## Facts from implementation (use these to inform your verification):
{command_context}

## Instructions:
1. Analyze what the condition requires
2. Run appropriate commands to verify it
3. IMPORTANT: If similar commands were run during implementation, use the SAME commands
   (e.g., if `poetry run pytest` was used, use that instead of bare `pytest`)
4. Check the output against the condition's criteria

After verification, respond with EXACTLY one of these on a single line:
- CONDITION_PASS - if the condition is satisfied
- CONDITION_FAIL - if the condition is NOT satisfied

Include a brief explanation before the verdict."""

        start_time = datetime.now(UTC)
        result = await self._execute_with_stall_retry(
            prompt=prompt,
            allowed_tools=get_allowed_tools(task.status),
            cwd=task.sources[0],
            on_message=on_message,
        )
        end_time = datetime.now(UTC)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Sanitize response to handle potential encoding issues
        safe_response = result.final_response.encode("utf-8", errors="replace").decode("utf-8")
        response = safe_response.upper()
        status = CheckStatus.PASS if "CONDITION_PASS" in response else CheckStatus.FAIL

        # Create evidence for manual condition (contract 1.2)
        tools_used = ", ".join(result.tools_used) if result.tools_used else "none"
        result_dict = {
            "condition_id": str(condition.id),
            "status": status.value,
            "verification_type": "agent",
            "tools_used": result.tools_used,
            "duration_ms": duration_ms,
            "timestamp": end_time.isoformat(),
        }
        log_content = (
            f"VERIFICATION PROMPT:\n{prompt}\n\n"
            f"AGENT RESPONSE:\n{result.final_response}\n\n"
            f"TOOLS USED: {tools_used}\n"
            f"VERDICT: {status.value}"
        )

        artifact_path, log_path = await self.evidence_store.save_check_evidence(
            task_id=task.id,
            iteration_num=iteration_num,
            condition_id=condition.id,
            result=result_dict,
            log_content=log_content,
        )

        # Create summary with agent response tail
        response_tail = (
            result.final_response[-500:]
            if len(result.final_response) > 500
            else result.final_response
        )
        cwd = task.sources[0] if task.sources else "."

        evidence_ref = EvidenceRef(
            task_id=task.id,
            condition_id=condition.id,
            check_id=None,  # Manual condition has no check_id
            artifact_path_rel=artifact_path,
            log_path_rel=log_path,
        )
        evidence_summary = EvidenceSummary(
            command=f"[agent verification: {tools_used}]",
            cwd=cwd,
            exit_code=0 if status == CheckStatus.PASS else 1,
            duration_ms=duration_ms,
            output_tail=response_tail,
            timestamp=end_time,
        )

        return status, evidence_ref, evidence_summary

    async def _record_evidence(
        self,
        task: Task,
        iteration_num: int,
        condition_id: UUID,
        run_result: CheckRunResult,
        check_command: str,
    ) -> tuple[EvidenceRef, EvidenceSummary]:
        """Record check evidence and return refs/summary."""
        result_dict = {
            "check_id": str(run_result.check_id),
            "status": run_result.status.value,
            "exit_code": run_result.exit_code,
            "duration_ms": run_result.duration_ms,
            "timestamp": run_result.timestamp.isoformat(),
        }
        log_content = f"STDOUT:\n{run_result.stdout}\n\nSTDERR:\n{run_result.stderr}"

        artifact_path, log_path = await self.evidence_store.save_check_evidence(
            task_id=task.id,
            iteration_num=iteration_num,
            condition_id=condition_id,
            result=result_dict,
            log_content=log_content,
        )

        # Create tail summary (last ~500 chars of output)
        output = run_result.stdout or run_result.stderr
        tail = output[-500:] if len(output) > 500 else output
        cwd = task.sources[0] if task.sources else "."

        return (
            EvidenceRef(
                task_id=task.id,
                condition_id=condition_id,
                check_id=run_result.check_id,
                artifact_path_rel=artifact_path,
                log_path_rel=log_path,
            ),
            EvidenceSummary(
                command=check_command,
                cwd=cwd,
                exit_code=run_result.exit_code,
                duration_ms=run_result.duration_ms,
                output_tail=tail,
                timestamp=run_result.timestamp,
            ),
        )
