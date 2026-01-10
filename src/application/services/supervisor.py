import hashlib
from dataclasses import dataclass

from src.domain.entities.iteration import Iteration
from src.domain.entities.task import Task
from src.domain.value_objects.condition_enums import CheckStatus
from src.domain.value_objects.supervision_enums import (
    AnomalyType,
    RetryStrategy,
    SupervisionDecision,
)


@dataclass
class SupervisionResult:
    decision: SupervisionDecision
    anomaly: AnomalyType | None
    reason: str


class Supervisor:
    def __init__(
        self,
        stagnation_limit: int = 3,
        loop_limit: int = 5,
        flaky_retry_limit: int = 2,
        rollback_limit: int = 2,
    ):
        self.stagnation_limit = stagnation_limit
        self.loop_limit = loop_limit
        self.flaky_retry_limit = flaky_retry_limit
        self.rollback_limit = rollback_limit
        self._error_history: dict[str, int] = {}
        self._rollback_count: int = 0

    def analyze(self, task: Task, latest_iteration: Iteration) -> SupervisionResult:
        budget_result = self._check_budget_risk(task)
        if budget_result:
            return budget_result

        regression_result = self._check_regression(task.iterations)
        if regression_result:
            return regression_result

        loop_result = self._check_loop(task, latest_iteration)
        if loop_result:
            return loop_result

        stagnation_result = self._check_stagnation(task.iterations)
        if stagnation_result:
            return stagnation_result

        flaky_result = self._check_flaky(task.iterations)
        if flaky_result:
            return flaky_result

        return SupervisionResult(
            decision=SupervisionDecision.CONTINUE,
            anomaly=None,
            reason="Progress detected, continuing",
        )

    def _check_budget_risk(self, task: Task) -> SupervisionResult | None:
        budget = task.budget
        if budget.iteration_count >= budget.max_iterations * 0.8:
            return SupervisionResult(
                decision=SupervisionDecision.STOP,
                anomaly=AnomalyType.CONTRACT_RISK,
                reason=(
                    f"Budget nearly exhausted: "
                    f"{budget.iteration_count}/{budget.max_iterations} iterations"
                ),
            )
        return None

    def _check_stagnation(self, iterations: list[Iteration]) -> SupervisionResult | None:
        if len(iterations) < 2:
            return None

        stagnant_count = self._count_stagnant_iterations(iterations)

        if stagnant_count >= self.stagnation_limit:
            return SupervisionResult(
                decision=SupervisionDecision.REPLAN,
                anomaly=AnomalyType.STAGNATION,
                reason=f"No progress for {stagnant_count} iterations, replanning",
            )
        if stagnant_count >= 2:
            return SupervisionResult(
                decision=SupervisionDecision.DEEPEN_CONTEXT,
                anomaly=AnomalyType.STAGNATION,
                reason=f"No progress for {stagnant_count} iterations, deepening context",
            )
        return None

    def _count_stagnant_iterations(self, iterations: list[Iteration]) -> int:
        count = 0
        for it in reversed(iterations):
            if not it.changes:
                count += 1
            else:
                break
        return count

    def _check_loop(self, task: Task, iteration: Iteration) -> SupervisionResult | None:
        error_hash = self._compute_error_hash(task, iteration)
        if not error_hash:
            return None

        self._error_history[error_hash] = self._error_history.get(error_hash, 0) + 1
        count = self._error_history[error_hash]

        if count >= self.loop_limit:
            return SupervisionResult(
                decision=SupervisionDecision.STOP,
                anomaly=AnomalyType.LOOP_DETECTED,
                reason=f"Same error pattern repeated {count} times, stopping",
            )
        if count >= 3:
            return SupervisionResult(
                decision=SupervisionDecision.REPLAN,
                anomaly=AnomalyType.LOOP_DETECTED,
                reason=f"Same error pattern repeated {count} times, replanning",
            )
        return None

    def _compute_error_hash(self, task: Task, iteration: Iteration) -> str | None:
        # Collect failed conditions from BOTH sources:
        # 1. iteration.check_results (for this iteration's checks)
        # 2. task.conditions (for manual conditions that may not be in check_results)
        failed_checks: set[str] = set()

        # From iteration check_results
        for check_id, status in iteration.check_results.items():
            if status == CheckStatus.FAIL:
                failed_checks.add(str(check_id))

        # From task conditions (catches manual conditions not re-checked this iteration)
        for condition in task.conditions:
            if condition.check_status == CheckStatus.FAIL:
                failed_checks.add(str(condition.id))

        if not failed_checks:
            return None
        content = "|".join(sorted(failed_checks))
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _check_regression(self, iterations: list[Iteration]) -> SupervisionResult | None:
        if len(iterations) < 2:
            return None

        current = iterations[-1]
        prev = iterations[-2]

        for check_id, status in current.check_results.items():
            prev_status = prev.check_results.get(check_id)
            if prev_status == CheckStatus.PASS and status == CheckStatus.FAIL:
                return SupervisionResult(
                    decision=SupervisionDecision.REPLAN,
                    anomaly=AnomalyType.REGRESSION,
                    reason=f"Check {check_id} regressed from PASS to FAIL",
                )
        return None

    def _check_flaky(self, iterations: list[Iteration]) -> SupervisionResult | None:
        if len(iterations) < 3:
            return None

        recent = iterations[-3:]
        for check_id in recent[-1].check_results:
            statuses = [it.check_results.get(check_id) for it in recent]
            if self._is_flaky_pattern(statuses):
                return SupervisionResult(
                    decision=SupervisionDecision.BLOCK,
                    anomaly=AnomalyType.FLAKY_CHECK,
                    reason=f"Check {check_id} appears flaky: {statuses}",
                )
        return None

    def _is_flaky_pattern(self, statuses: list[CheckStatus | None]) -> bool:
        filtered = [s for s in statuses if s is not None]
        if len(filtered) < 3:
            return False
        return (
            filtered[0] == CheckStatus.PASS
            and filtered[1] == CheckStatus.FAIL
            and filtered[2] == CheckStatus.PASS
        ) or (
            filtered[0] == CheckStatus.FAIL
            and filtered[1] == CheckStatus.PASS
            and filtered[2] == CheckStatus.FAIL
        )

    def reset_error_history(self) -> None:
        self._error_history.clear()

    def reset_rollback_count(self) -> None:
        self._rollback_count = 0

    def decide_retry_strategy(
        self,
        task: Task,
        iteration: Iteration,
    ) -> tuple[RetryStrategy, str]:
        """Decide retry strategy based on iteration analysis."""
        error_hash = self._compute_error_hash(task, iteration)

        if error_hash:
            repeat_count = self._error_history.get(error_hash, 0)

            if repeat_count >= self.loop_limit:
                return RetryStrategy.STOP, f"Same error {repeat_count} times, stopping"

            if repeat_count >= 2 and self._rollback_count < self.rollback_limit:
                self._rollback_count += 1
                return RetryStrategy.ROLLBACK_AND_RETRY, "Same error repeated, trying fresh"

        if not iteration.changes:
            return RetryStrategy.STOP, "No changes made, stopping"

        return RetryStrategy.CONTINUE_WITH_CONTEXT, "Providing failure feedback"
