from dataclasses import dataclass

from loguru import logger

from src.domain.entities.task import Task
from src.domain.value_objects.task_status import TaskStatus


@dataclass
class Strategy:
    planning_depth: str  # "quick" | "phased"
    include_baseline: bool
    include_quality_loop: bool
    discovery_depth: str  # "standard" | "extended"
    rationale: str


class SelectStrategy:
    async def execute(self, task: Task, include_baseline: bool = False) -> Strategy:
        """Select execution strategy based on task characteristics.

        Transitions task to STRATEGY status.
        """
        is_large = len(task.goals) > 3 or "multi" in task.description.lower()
        planning_depth = "phased" if is_large else "quick"

        is_monorepo = len(task.sources) > 1
        discovery_depth = "extended" if is_monorepo else "standard"

        strategy = Strategy(
            planning_depth=planning_depth,
            include_baseline=include_baseline,
            include_quality_loop=True,
            discovery_depth=discovery_depth,
            rationale=f"Selected {planning_depth} planning for {'multi-goal' if is_large else 'focused'} task",
        )

        task.transition_to(TaskStatus.STRATEGY)
        logger.info(
            "Strategy selected for task {}: planning={}, discovery={}",
            task.id,
            planning_depth,
            discovery_depth,
        )

        return strategy
