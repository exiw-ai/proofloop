from src.domain.entities.iteration import Iteration
from src.domain.entities.task import Task
from src.domain.value_objects.condition_enums import CheckStatus
from src.domain.value_objects.stagnation_action import StagnationAction


class StagnationDetector:
    def __init__(self, limit: int = 3):
        self.limit = limit

    def is_stagnating(self, iterations: list[Iteration]) -> bool:
        if len(iterations) < self.limit:
            return False

        recent = iterations[-self.limit :]
        for it in recent:
            if it.changes:
                return False
            if self._has_check_improvement(iterations, it):
                return False
        return True

    def get_stagnation_count(self, iterations: list[Iteration]) -> int:
        count = 0
        for it in reversed(iterations):
            if not it.changes and not self._has_any_pass(it):
                count += 1
            else:
                break
        return count

    def _has_check_improvement(self, all_iterations: list[Iteration], current: Iteration) -> bool:
        current_idx = next((i for i, it in enumerate(all_iterations) if it is current), -1)
        if current_idx <= 0:
            return False

        prev = all_iterations[current_idx - 1]
        for check_id, status in current.check_results.items():
            prev_status = prev.check_results.get(check_id)
            if prev_status == CheckStatus.FAIL and status == CheckStatus.PASS:
                return True
        return False

    def _has_any_pass(self, iteration: Iteration) -> bool:
        return any(status == CheckStatus.PASS for status in iteration.check_results.values())


def is_research_stagnant(iterations: list[Iteration], window: int = 5) -> bool:
    """Check if research pipeline is stagnating based on metrics growth."""
    if len(iterations) < window:
        return False

    recent = iterations[-window:]

    # Get metrics from first and last in window
    first_metrics = recent[0].metrics
    last_metrics = recent[-1].metrics

    if not first_metrics or not last_metrics:
        return False

    sources_first = first_metrics.get("sources_count", 0)
    sources_last = last_metrics.get("sources_count", 0)
    coverage_first = first_metrics.get("coverage", 0)
    coverage_last = last_metrics.get("coverage", 0)
    findings_first = first_metrics.get("findings_count", 0)
    findings_last = last_metrics.get("findings_count", 0)

    # Calculate growth rates
    sources_growth = (sources_last - sources_first) / max(sources_first, 1)
    coverage_growth = coverage_last - coverage_first
    findings_growth = (findings_last - findings_first) / max(findings_first, 1)

    # Stagnant if all growth rates are below thresholds
    return sources_growth < 0.1 and coverage_growth < 0.05 and findings_growth < 0.1


def handle_stagnation(task: Task, iterations: list[Iteration]) -> StagnationAction:
    """Determine appropriate action for research pipeline stagnation."""
    if not is_research_stagnant(iterations):
        return StagnationAction.CONTINUE

    if not iterations:
        return StagnationAction.CONTINUE

    current_metrics = iterations[-1].metrics
    current_coverage = current_metrics.get("coverage", 0)

    # Get required coverage from research inventory
    required_coverage = 0.8  # Default
    if task.research_inventory:
        from src.domain.value_objects import PRESET_PARAMS

        preset_params = PRESET_PARAMS.get(task.research_inventory.preset)
        if preset_params:
            required_coverage = preset_params.coverage

    # If we're close (within 10% of target), finalize with partial results
    if current_coverage >= required_coverage * 0.9:
        return StagnationAction.FINALIZE_PARTIAL

    # If we've already relaxed once, escalate to user
    if task.conditions_relaxed:
        return StagnationAction.ESCALATE_TO_USER

    # First stagnation: try relaxing conditions
    return StagnationAction.RELAX_CONDITIONS
